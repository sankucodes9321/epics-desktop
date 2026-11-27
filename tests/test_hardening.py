import base64
import os

import fakeredis
import numpy as np
import pytest

from privacy.config import FaceSettings, capture_backend, face_settings, log_cap, threshold
from privacy.errors import PipelineError
from privacy.matching import Matcher
from privacy.quality import check_quality
from privacy.store import ACCESS, Store, user_key
from scripts.rotate_key import rotate


def test_defaults(monkeypatch):
    for key in list(os.environ):
        if key.startswith("ZKAUTH_") or key == "CAPTURE_BACKEND":
            monkeypatch.delenv(key)
    assert face_settings() == FaceSettings("retinaface", True, .95, 100, 40, 215, 50, .25)
    assert (capture_backend(), threshold(), log_cap()) == ("gst-pipewire", .7, 1000)


@pytest.mark.parametrize("brightness,x,hint", [(39, 25, "too dark"), (216, 25, "too bright"),
                                               (128, 25, "blurry"), (128, 0, "off-center")])
def test_quality(brightness, x, hint, monkeypatch):
    frame = np.full((100, 100, 3), brightness, np.uint8)
    area = dict(x=x, y=25, w=40, h=50)
    with pytest.raises(PipelineError, match=hint):
        check_quality(frame, area, face_settings())
    monkeypatch.setenv("ZKAUTH_MIN_LAPLACIAN_VAR", "0")
    check_quality(np.full_like(frame, 128), dict(area, x=25), face_settings())


@pytest.fixture
def matcher():
    return Matcher(Store(fakeredis.FakeRedis()), os.urandom(32), .7, lambda: np.ones(512, "<f4"))


def test_enrollment_quality(matcher, caplog):
    matcher.enroll("alice", "Alice")
    matcher.enroll("alice", "Alice")
    assert "Near-duplicate" in caplog.text
    before = matcher.store.load("alice")
    matcher.acquire = lambda: -np.ones(512, "<f4")
    with pytest.raises(PipelineError, match="low similarity"):
        matcher.enroll("alice", "Alice")
    assert matcher.store.load("alice") == before


def test_rotation(matcher):
    for uid in ("alice", "bob", "alice"):
        matcher.enroll(uid, uid)
    replacement = os.urandom(32)
    assert rotate(matcher.store, matcher.key, replacement) == 2
    with pytest.raises(PipelineError, match="authentication"):
        matcher.verify("alice")
    with pytest.raises(PipelineError, match="Key has changed"):
        matcher.enroll("new", "New")
    matcher.key = replacement
    assert matcher.verify("alice").match and matcher.verify("bob").match
    with pytest.raises(PipelineError, match="different"):
        rotate(matcher.store, matcher.key, replacement)
    assert matcher.verify("alice").match


def test_corrupt_last_record_aborts(matcher):
    for uid in ("a", "b"):
        matcher.enroll(uid, uid)
    original = matcher.store.load("a")
    matcher.store.db.hset(user_key("b"), "templates", b"invalid")
    with pytest.raises(PipelineError, match="length"):
        rotate(matcher.store, matcher.key, os.urandom(32))
    assert matcher.store.load("a") == original


def test_log_cap(monkeypatch):
    monkeypatch.setenv("ZKAUTH_LOG_CAP", "2")
    store = Store(fakeredis.FakeRedis())
    matcher = Matcher(store, os.urandom(32), .7, lambda: np.ones(512, "<f4"))
    matcher.enroll("alice", "Alice")
    for _ in range(3):
        matcher.verify("alice")
    assert store.db.xlen(ACCESS) == 2
    store.audit("unknown", "unknown")
    assert [row[3] for row in store.recent()] == ["unknown", "match"]


def test_rotation_concurrent_enrollment(matcher, monkeypatch):
    matcher.enroll("alice", "Alice")
    original = matcher.store.load("alice")
    users = matcher.store.users

    def enroll_during_scan():
        before = users()
        matcher.enroll("bob", "Bob")
        return before

    monkeypatch.setattr(matcher.store, "users", enroll_during_scan)
    with pytest.raises(PipelineError, match="Concurrent"):
        rotate(matcher.store, matcher.key, os.urandom(32))
    assert matcher.store.load("alice") == original
    assert matcher.verify("bob").match


@pytest.mark.parametrize("length", [0, 16, 24, 33])
def test_rotation_requires_aes256(matcher, length):
    matcher.enroll("alice", "Alice")
    with pytest.raises(PipelineError, match="32 bytes"):
        rotate(matcher.store, matcher.key, bytes(length))
    assert matcher.verify("alice").match


@pytest.mark.parametrize("cutoff", ["-1", "0", "nan"])
def test_cutoff_requires_positive_evidence(monkeypatch, cutoff):
    monkeypatch.setenv("ZKAUTH_THRESHOLD", cutoff)
    with pytest.raises(PipelineError, match="ZKAUTH_THRESHOLD"):
        threshold()


def test_legacy_binding_valid_gallery(matcher):
    from privacy.store import KEY_ID
    matcher.enroll("a", "Alice")
    matcher.store.db.delete(KEY_ID)
    matcher.enroll("b", "Bob")
    assert matcher.verify("a").match and matcher.verify("b").match
    assert matcher.store.db.exists(KEY_ID)


def test_genuine_verify_racing_fifth_reject(matcher, monkeypatch):
    matcher.enroll("a", "Alice")
    original = matcher.store.finish_verify

    def finish_after_lock(record, matched, score):
        matcher.store.db.set("zkauth:fail:a", 5, ex=60)
        original(record, matched, score)

    monkeypatch.setattr(matcher.store, "finish_verify", finish_after_lock)
    with pytest.raises(PipelineError, match="locked"):
        matcher.verify("a")
    assert matcher.store.failures("a") == 5
    assert next(matcher.store.recent())[3] == "locked"


def test_empty_fingerprint_is_corruption(matcher):
    from privacy.store import KEY_ID
    matcher.enroll("a", "Alice")
    matcher.store.db.set(KEY_ID, b"")
    with pytest.raises(PipelineError, match="Key has changed"):
        matcher.enroll("b", "Bob")
    with pytest.raises(PipelineError, match="active key"):
        rotate(matcher.store, matcher.key, os.urandom(32))
    assert matcher.store.users() == ["a"]
