import os
import sys
from types import ModuleType
from unittest.mock import patch

import fakeredis
import numpy as np
import pytest

from privacy import matching
from privacy.errors import PipelineError
from privacy.matching import Matcher, cosine, normalize, references
from privacy.store import ACCESS, Store


def axis(index):
    vector = np.zeros(512, dtype="<f4")
    vector[index] = 4
    return vector


@pytest.fixture
def service():
    return Matcher(Store(fakeredis.FakeRedis()), os.urandom(32), 0.70, lambda: axis(0))


def test_cosine():
    probe = axis(0)
    assert normalize(probe)
    rows = np.stack([axis(0), axis(1), -axis(0), np.zeros_like(probe)])
    assert [normalize(row) for row in rows] == [True, True, True, False]
    assert np.allclose(cosine(rows, probe), [1, 0, -1, 0])


def test_roundtrip_wipes_and_authenticates(service):
    service.enroll("alice", "Alice")
    record = service.store.load("alice")
    with references([record], service.key) as matrix:
        assert matrix[0, 0] == 1
        assert np.count_nonzero(matrix) == 1
    assert not matrix.any()
    with patch.object(matching, "wipe", wraps=matching.wipe) as observed:
        with pytest.raises(PipelineError, match="authentication"):
            with references([record], os.urandom(32)):
                pytest.fail("Unauthenticated matrix exposed")
        assert not observed.call_args.args[0].any()


def test_matching_pipeline(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for _ in range(5):
        service.enroll("alice", "Alice")
    with pytest.raises(PipelineError, match="five"):
        service.enroll("alice", "Alice")
    service.acquire = lambda: axis(1)
    service.enroll("bob", "Bob")
    assert service.identify() == "bob"
    decision = service.verify("bob")
    assert decision.match and decision.score == 1 and decision.threshold == .70
    service.acquire = lambda: axis(2)
    assert service.identify() == "unknown"
    assert not service.verify("alice").match
    service.store.delete("bob", service.key)
    with pytest.raises(PipelineError, match="not found"):
        service.verify("bob")
    assert list(tmp_path.iterdir()) == []
    for _, fields in service.store.db.xrange(ACCESS):
        assert set(fields) == {b"timestamp", b"user_id", b"result", b"score"}


def test_lockout(service):
    service.enroll("alice", "Alice")
    service.acquire = lambda: axis(1)
    for _ in range(5):
        assert not service.verify("alice").match
    assert 0 < service.store.db.ttl("zkauth:fail:alice") <= 60
    service.acquire = lambda: pytest.fail("Locked user triggered capture")
    with pytest.raises(PipelineError, match="locked"):
        service.verify("alice")
    service.store.db.pexpire("zkauth:fail:alice", 0)
    service.acquire = lambda: axis(0)
    assert service.verify("alice").match


def test_capture_scope_precedes_storage(service, monkeypatch, tmp_path):
    embedding = ModuleType("privacy.embedding")
    monkeypatch.setitem(sys.modules, "privacy.embedding", embedding)

    frame = np.ones((4, 4, 3), dtype=np.uint8)

    def extract(image, detector=None, antispoof=None):
        assert image is frame and image.all()
        return axis(0)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("privacy.capture._pipewire", lambda: frame)
    monkeypatch.setattr(embedding, "extract", extract, raising=False)
    service.acquire = lambda: matching.sample(0, "gst-pipewire")
    service.enroll("alice", "Alice")
    assert not frame.any()
    assert not list(tmp_path.iterdir())


def test_attendance(service, monkeypatch):
    monkeypatch.setenv("ZKAUTH_TIMEZONE", "Asia/Kolkata")
    service.enroll("alice", "Alice")
    assert service.identify(True).startswith("marked\t")
    assert service.identify(True).startswith("already marked today\t")
    row, = service.store.attendance_report()
    assert len(row) == 4 and row[:2] == ("alice", "Alice")
    service.store.db.set("zkauth:fail:alice", 5)
    with pytest.raises(PipelineError, match="locked"):
        service.identify(True)
    service.acquire = lambda: axis(1)
    assert service.identify(True) == "unknown"
    assert list(service.store.attendance_report()) == [row]


def test_foreign_key_cannot_insert_new_user(service):
    service.enroll("alice", "Alice")
    service.key = os.urandom(32)
    with pytest.raises(PipelineError, match="Key has changed"):
        service.enroll("bob", "Bob")
    assert service.store.users() == ["alice"]


def test_attendance_midnights_and_reports(service, monkeypatch, tmp_path, capsys):
    import csv
    import json
    import main

    monkeypatch.setenv("ZKAUTH_TIMEZONE", "Asia/Kolkata")
    service.enroll("alice", "Alice")
    first = "2026-11-19T18:29:00+00:00"
    second = "2026-11-19T18:31:00+00:00"
    for instant, expected, original, local in (
        (first, "marked", first, "2026-11-19T23:59:00+05:30"),
        (second, "marked", second, "2026-11-20T00:01:00+05:30"),
        ("2026-11-19T23:59:00+00:00", "already marked today", second, "2026-11-20T00:01:00+05:30"),
        ("2026-11-20T00:00:00+00:00", "already marked today", second, "2026-11-20T00:01:00+05:30"),
        ("2026-11-20T00:01:00+00:00", "already marked today", second, "2026-11-20T00:01:00+05:30"),
    ):
        monkeypatch.setattr("privacy.store.timestamp", lambda: instant)
        assert service.identify(True) == f"{expected}\ttimestamp_utc={original}\ttimestamp_local={local}"
        stored, = service.store.db.hvals("zkauth:attendance:" + local[:10])
        assert json.loads(stored)["timestamp"] == original
    assert len(list(service.store.db.scan_iter("zkauth:attendance:*"))) == 2

    monkeypatch.setattr("privacy.store.timestamp", lambda: second)
    monkeypatch.setattr(main, "redis_client", lambda: service.store.db)
    monkeypatch.setattr(main, "startup", lambda _: None)
    monkeypatch.setattr(sys, "argv", ["main.py", "attendance-report"])
    assert main.main() == 0
    header, row = capsys.readouterr().out.splitlines()
    assert row.split("\t") == ["alice", "Alice", second, "2026-11-20T00:01:00+05:30"]

    path = tmp_path / "attendance.csv"
    monkeypatch.setattr(sys, "argv", ["main.py", "attendance-report", "--date", "2026-11-19",
                                      "--csv", str(path)])
    assert main.main() == 0
    with path.open(newline="") as handle:
        assert list(csv.reader(handle)) == [
            header.split("\t"), ["alice", "Alice", first, "2026-11-19T23:59:00+05:30"]]


def test_attendance_zone_selection(monkeypatch):
    from privacy.store import attendance_zone
    monkeypatch.delenv("ZKAUTH_TIMEZONE", raising=False)
    monkeypatch.setenv("TZ", "Europe/Paris")
    assert attendance_zone().key == "Europe/Paris"
    monkeypatch.setenv("TZ", "Missing/Zone")
    assert attendance_zone().key == "Asia/Kolkata"
    monkeypatch.setenv("ZKAUTH_TIMEZONE", "Missing/Zone")
    with pytest.raises(PipelineError, match="IANA"):
        attendance_zone()


@pytest.mark.parametrize("attendance", [True, False])
def test_identification_tie_is_unknown(service, attendance):
    for uid in ("alice", "bob"):
        service.enroll(uid, uid)
    assert service.identify(attendance) == "unknown"
    assert not list(service.store.attendance_report())


@pytest.mark.parametrize("winner", [True, False])
def test_gallery_change_invalidates_decision(service, winner):
    service.enroll("alice", "Alice")
    other = Matcher(service.store, service.key, .7, lambda: axis(1))

    def concurrent_sample():
        other.enroll("bob", "Bob")
        return axis(0 if winner else 1)

    service.acquire = concurrent_sample
    with pytest.raises(PipelineError, match="Gallery changed"):
        service.identify(True)
    assert not list(service.store.attendance_report())


@pytest.mark.parametrize("value", [float("nan"), 0., 4.])
def test_invalid_authenticated_row_denied(service, value):
    from privacy.encryption import encrypt
    from privacy.store import user_key
    service.enroll("alice", "Alice")
    row = np.zeros(512, "<f4")
    row[0] = value
    blob = encrypt(row, service.key, matching.aad("alice", 1))
    service.store.db.hset(user_key("alice"), "templates", blob)
    with pytest.raises(PipelineError, match="Invalid reference vector"):
        service.enroll("alice", "Alice")
    with pytest.raises(PipelineError, match="Invalid reference vector"):
        service.verify("alice")


@pytest.mark.parametrize("value", [b"-1", b"", b"garbled"])
def test_invalid_lockout_state(service, value):
    service.enroll("alice", "Alice")
    service.store.db.set("zkauth:fail:alice", value)
    with pytest.raises(PipelineError, match="Invalid lockout"):
        service.verify("alice")
    with pytest.raises(PipelineError, match="Invalid lockout"):
        service.identify(True)
    assert not list(service.store.attendance_report())


def test_access_stream_error_preserves_attendance_and_counter(service):
    service.enroll("alice", "Alice")
    service.store.db.set(ACCESS, "wrong-type")
    service.store.db.set("zkauth:fail:alice", 2)
    for action in (lambda: service.identify(True), lambda: service.verify("alice")):
        with pytest.raises(PipelineError, match="access log"):
            action()
    assert not list(service.store.attendance_report())
    assert service.store.failures("alice") == 2


def test_persistent_contention_stops(service, monkeypatch):
    from redis.exceptions import WatchError
    from unittest.mock import Mock
    service.enroll("alice", "Alice")
    pipe_class = type(service.store.db.pipeline())
    execute = Mock(side_effect=WatchError("Watched variable changed."))
    monkeypatch.setattr(pipe_class, "execute", execute)
    with pytest.raises(PipelineError, match="busy"):
        service.verify("alice")
    assert 1 <= execute.call_count <= 8


def test_uncertain_commit_never_retried(service, monkeypatch):
    from redis.exceptions import WatchError
    from unittest.mock import Mock
    service.enroll("alice", "Alice")
    execute = Mock(side_effect=WatchError("connection lost"))
    monkeypatch.setattr(type(service.store.db.pipeline()), "execute", execute)
    with pytest.raises(PipelineError, match="outcome"):
        service.verify("alice")
    execute.assert_called_once()


def test_bad_revision_preserves_records(service):
    from privacy.store import REVISION
    service.enroll("alice", "Alice")
    before = service.store.load("alice")
    service.store.db.set(REVISION, "invalid")
    for action in (lambda: service.enroll("alice", "Alice"), lambda: service.store.delete("alice", service.key)):
        with pytest.raises(PipelineError, match="revision"):
            action()
        assert service.store.load("alice") == before


@pytest.mark.parametrize("name", ["Alice\nBob", "A\x1b", "a" * 129])
def test_invalid_name_rejected_before_capture(service, name):
    service.acquire = lambda: pytest.fail("unexpected capture")
    with pytest.raises(PipelineError, match="Name"):
        service.enroll("alice", name)


def test_export_protects_legacy_names_and_formula_like_ids(service, monkeypatch, tmp_path, capsys):
    import csv
    import stat
    import main
    from privacy.store import user_key
    service.enroll("-alice", "Alice")
    service.store.db.hset(user_key("-alice"), "name", "  =legacy\nlabel")
    assert service.verify("-alice").match
    service.identify(True)
    monkeypatch.setattr(main, "redis_client", lambda: service.store.db)
    monkeypatch.setattr(main, "startup", lambda _: None)
    monkeypatch.setattr(sys, "argv", ["main.py", "attendance-report"])
    assert main.main() == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2 and "\\u000a" in lines[1]
    output = tmp_path / "report.csv"
    monkeypatch.setattr(sys, "argv", ["main.py", "attendance-report", "--csv", str(output)])
    assert main.main() == 0
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with output.open(newline="") as handle:
        _, row = csv.reader(handle)
        assert row[:2] == ["'-alice", "'  =legacy\\u000alabel"]
    assert main.main() == 1


def test_open_into_clears_destination_on_tag_error(service):
    from privacy.encryption import open_into
    service.enroll("alice", "Alice")
    record = service.store.load("alice")
    scratch = bytearray(matching.ROW_BYTES + 15)
    with pytest.raises(PipelineError, match="authentication"):
        open_into(record.blob, service.key, matching.aad("bob", 1), memoryview(scratch))
    assert not any(scratch)


@pytest.mark.parametrize("length", [16, 24])
def test_encrypt_requires_256_bits(length):
    from privacy.encryption import encrypt
    with pytest.raises(PipelineError, match="32 bytes"):
        encrypt(axis(0), bytes(length))


def test_delete_requires_matching_key_and_preserves_history(service):
    service.enroll("alice", "Alice")
    service.identify(True)
    service.store.db.set("zkauth:fail:alice", 3)
    with pytest.raises(PipelineError, match="authentication"):
        service.store.delete("alice", os.urandom(32))
    assert service.store.load("alice") and service.store.failures("alice") == 3
    service.store.delete("alice", service.key)
    assert service.store.load("alice") is None and service.store.failures("alice") == 0
    assert len(list(service.store.attendance_report())) == 1


def test_legacy_gallery_validated_before_binding(service):
    from privacy.store import KEY_ID, user_key
    for uid in ("a", "b"):
        service.enroll(uid, uid)
    service.store.db.delete(KEY_ID)
    assert service.verify("a").match
    service.store.db.hset(user_key("b"), "templates", b"invalid")
    with pytest.raises(PipelineError, match="length"):
        service.enroll("c", "C")
    assert not service.store.db.exists(KEY_ID)
    assert service.store.load("c") is None


def test_duplicate_attendance_corrupt_timestamp_denied(service, monkeypatch):
    import json
    monkeypatch.setenv("ZKAUTH_TIMEZONE", "Asia/Kolkata")
    monkeypatch.setattr("privacy.store.timestamp", lambda: "2026-11-20T00:00:00+00:00")
    service.enroll("alice", "Alice")
    service.identify(True)
    key = "zkauth:attendance:2026-11-20"
    entry = json.loads(service.store.db.hget(key, "alice"))
    entry["timestamp"] = "2026-11-20"
    service.store.db.hset(key, "alice", json.dumps(entry))
    before = list(service.store.recent())
    with pytest.raises(PipelineError, match="attendance"):
        service.identify(True)
    assert list(service.store.recent()) == before
    with pytest.raises(PipelineError, match="attendance"):
        list(service.store.attendance_report())


def test_failed_attendance_export_can_retry_without_partial_file(service, monkeypatch, tmp_path):
    import main
    from unittest.mock import patch
    destination = tmp_path / "attendance.csv"
    service.enroll("alice", "Alice")
    service.identify(attendance=True)
    monkeypatch.setattr(main, "redis_client", lambda: service.store.db)
    monkeypatch.setattr(main, "startup", lambda *_: None)
    monkeypatch.setattr(sys, "argv", ["main.py", "attendance-report", "--csv", str(destination)])
    with patch("scripts.exports.os.fsync", side_effect=OSError("disk full")):
        assert main.main() == 1
    assert not list(tmp_path.iterdir())
    assert main.main() == 0
    assert "alice,Alice" in destination.read_text()
