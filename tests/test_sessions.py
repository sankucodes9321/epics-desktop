import base64
import json
import os
import stat

import cv2
import numpy as np
import pytest
from cryptography.exceptions import InvalidSignature

from privacy.errors import PipelineError
from privacy.sessions import Sessions, session_key
from scripts.classroom import Classroom
from student_verifier import DEMO_PUBLIC, canonical, check, verify


@pytest.fixture
def app():
    return Classroom(demo=True)


def enroll(app, uid):
    app.command("enroll", dict(uid=uid, name="Student " + uid))


def mark(app, sid, uid):
    return app.command("mark", dict(session=sid, subject=uid))


def test_lecture_scope_and_recovery(app):
    enroll(app, "a")
    first = app.ledger.open("Maths A")
    second = app.ledger.open("Physics A")
    assert mark(app, first, "a")["status"] == "marked"
    claim = app.ledger.export(first, "a")
    assert mark(app, first, "a")["status"] == "already marked"
    recovered = Sessions(app.db, bytes(32), demo=True)
    assert recovered.export(first, "a") == claim
    assert mark(app, second, "a")["status"] == "marked"
    assert app.ledger.export(second, "a") != claim
    signed = recovered.finalize(first)
    assert signed == recovered.finalize(first)
    assert verify(recovered.export(first), claim, DEMO_PUBLIC, True)["count"] == 1
    with pytest.raises(PipelineError, match="closed"):
        mark(app, first, "a")


def test_unknown_and_lockout_leave_no_mark(app):
    enroll(app, "a")
    sid = app.ledger.open("Class")
    assert mark(app, sid, "unregistered") == "unknown"
    app.db.set("zkauth:fail:a", 5)
    with pytest.raises(PipelineError, match="locked"):
        mark(app, sid, "a")
    assert not app.report(sid)["marks"]


@pytest.mark.parametrize("count", [1, 2, 3, 5, 8])
def test_independent_verification(app, count, tmp_path):
    sid = app.ledger.open("Class")
    for i in range(count):
        uid = f"private-student-{i}"
        enroll(app, uid)
        mark(app, sid, uid)
    doc = app.ledger.finalize(sid)
    bulletin = app.ledger.export(sid)
    assert b"private-student" not in canonical(bulletin)
    for i in range(count):
        receipt = app.ledger.export(sid, f"private-student-{i}")
        assert verify(doc, receipt, DEMO_PUBLIC, True)["session"] == sid
    summary_path, receipt_path = tmp_path/"public.json", tmp_path/"private.json"
    app.command("publish", dict(session=sid, path=summary_path))
    app.command("receipt", dict(session=sid, uid=uid, path=receipt_path))
    assert check(summary_path, receipt_path, None, True)["root"] == doc["summary"]["root"]
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        app.command("receipt", dict(session=sid, uid=uid, path=receipt_path))
    receipt["token"] = "ff"*32
    with pytest.raises(ValueError):
        verify(doc, receipt, DEMO_PUBLIC, True)
    bulletin["commitments"].pop()
    with pytest.raises(ValueError):
        verify(bulletin, receipt, DEMO_PUBLIC, True)
    with pytest.raises(InvalidSignature):
        verify(doc, receipt, base64.b64encode(os.urandom(32)), False)
    with pytest.raises(ValueError):
        verify(doc, receipt, DEMO_PUBLIC, False)


def test_signed_correction_history(app):
    enroll(app, "a")
    enroll(app, "b")
    sid = app.ledger.open("Class")
    mark(app, sid, "a")
    original = app.ledger.finalize(sid)
    claim = app.ledger.export(sid, "a")
    options = dict(session=sid, uid="b", decision="include", reason="Reviewed appeal", revision=1)
    second = app.command("correct", options)
    assert second["revision"] == 2 and second["count"] == 2 and second["previous"]
    with pytest.raises(PipelineError, match="Revision changed"):
        app.command("correct", options)
    app.command("correct", dict(options, uid="a", decision="remove", revision=2))
    assert verify(original, claim, DEMO_PUBLIC, True)["count"] == 1
    with pytest.raises(ValueError):
        verify(app.ledger.export(sid), claim, DEMO_PUBLIC, True)
    assert len(app.report(sid)["corrections"]) == 2


@pytest.mark.parametrize("field", ["name", "time"])
def test_signed_roster_tamper(app, field):
    enroll(app, "a")
    sid = app.ledger.open("Class")
    mark(app, sid, "a")
    app.ledger.finalize(sid)
    state = app.ledger.read(sid)
    state["marks"]["a"][field] = "changed"
    app.db.set(session_key(sid), canonical(state))
    with pytest.raises(PipelineError, match="signed summary"):
        app.report(sid)


def test_retention_preview_detects_change(app):
    sid = app.ledger.open("Class")
    opened = app.ledger.open("Other class")
    app.ledger.finalize(sid)
    args = dict(cutoff="2099-01-01")
    assert app.command("preview", args) == [session_key(sid)]
    enroll(app, "a")
    app.command("correct", dict(session=sid, uid="a", decision="include", reason="reviewed", revision=1))
    with pytest.raises(PipelineError, match="changed"):
        app.command("purge", args)
    app.command("preview", args)
    assert app.command("purge", args) == 1
    assert app.ledger.read(opened)
    assert app.command("verify", {"uid": "a"})["match"]


def test_trial_export_contains_aggregate_only(app, tmp_path):
    for uid in ("alpha", "beta"):
        enroll(app, uid)
    row = app.command("trial", dict(kind="genuine", uid="alpha", subject="alpha"))
    assert row["correct"] and row["gap"] > 0
    path = tmp_path/"metrics.json"
    app.command("metrics", dict(path=path))
    assert "alpha" not in path.read_text()
    assert json.loads(path.read_text())["trials"]["genuine"]["n"] == 1


def test_school_signer_configuration(app, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    aes = os.urandom(32)
    seed = os.urandom(32)
    monkeypatch.setenv("ZKAUTH_KEY", base64.b64encode(aes).decode())
    monkeypatch.setenv("ZKAUTH_SIGNING_SEED", base64.b64encode(aes).decode())
    with pytest.raises(PipelineError, match="independent"):
        Sessions.configured(app.db)
    monkeypatch.setenv("ZKAUTH_SIGNING_SEED", base64.b64encode(seed).decode())
    with pytest.raises(PipelineError, match="public key"):
        Sessions.configured(app.db)
    pin = base64.b64encode(Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()).decode()
    monkeypatch.setenv("ZKAUTH_SCHOOL_PUBLIC_KEY", pin)
    assert Sessions.configured(app.db).mode == "live"


def test_qr_encodes_only_signed_summary(app):
    sid = app.ledger.open("Class")
    doc = app.ledger.finalize(sid)
    matrix = app.command("qr", dict(session=sid))
    pixels = np.array([[0 if x == "1" else 255 for x in row] for row in matrix], np.uint8)
    image = cv2.resize(np.pad(pixels, 5, constant_values=255), None, fx=5, fy=5, interpolation=cv2.INTER_NEAREST)
    start, end = 25, len(image)-26
    corners = np.array([[[start,start], [end,start], [end,end], [start,end]]], np.float32)
    data, _ = cv2.QRCodeDetector().decode(image, corners)
    assert json.loads(data) == doc


def test_no_close_during_pending_mark(app, monkeypatch):
    enroll(app, "a")
    sid = app.ledger.open("Concurrency")
    original = app.matcher.acquire
    def delayed():
        app.ledger.finalize(sid)
        return original()
    app.matcher.acquire = delayed
    with pytest.raises(PipelineError, match="closed"):
        mark(app, sid, "a")
    assert not app.report(sid)["marks"]


def test_export_failure_publishes_no_partial_receipt(tmp_path):
    from scripts.classroom import save_json
    with pytest.raises(TypeError):
        save_json(tmp_path/"result.json", object())
    assert not list(tmp_path.iterdir())


def test_camera_ownership():
    from privacy.capture import camera_lease
    with camera_lease():
        with pytest.raises(PipelineError, match="in use"):
            with camera_lease():
                pytest.fail("two owners")
    with camera_lease():
        pass


def test_open_register_integrity_before_signing(app):
    sid = app.ledger.open("Class")
    enroll(app, "a")
    mark(app, sid, "a")
    state = app.ledger.read(sid)
    state["marks"]["a"]["time"] = "modified"
    app.db.set(session_key(sid), canonical(state))
    with pytest.raises(PipelineError, match="original commitments"):
        app.ledger.finalize(sid)


def test_disabled_antispoof_cannot_mark_class(app):
    enroll(app, "a")
    sid = app.ledger.open("Class")
    app.matcher.store.antispoof_off = True
    with pytest.raises(PipelineError, match="liveness"):
        mark(app, sid, "a")
    assert app.report(sid)["marks"] == []


def test_private_registers_require_matching_template_key(app, monkeypatch):
    enroll(app, "a")
    monkeypatch.setenv("ZKAUTH_KEY", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("ZKAUTH_SIGNING_SEED", base64.b64encode(os.urandom(32)).decode())
    with pytest.raises(PipelineError, match="gallery key"):
        Sessions.configured(app.db)

def test_teacher_can_uphold_register_after_appeal(app):
    enroll(app, "a")
    sid = app.ledger.open("Class")
    first = app.ledger.finalize(sid)["summary"]
    appeal = dict(session=sid, uid="a", decision="uphold", reason="Reviewed with student", revision=1)
    second = app.command("correct", appeal)
    assert first["root"] == second["root"] and second["revision"] == 2
    assert first["corrections"] != second["corrections"]
    assert app.report(sid)["corrections"][-1]["upheld"]


def test_live_signature_on_synthetic_data(app):
    enroll(app, "a")
    app.ledger = Sessions(app.db, os.urandom(32))
    sid = app.ledger.open("Synthetic integration test")
    mark(app, sid, "a")
    signed = app.ledger.finalize(sid)
    receipt = app.ledger.export(sid, "a")
    assert verify(signed, receipt, app.ledger.pin)["mode"] == "live"
    signed["summary"]["label"] = "changed"
    with pytest.raises(InvalidSignature):
        verify(signed, receipt, app.ledger.pin)


def test_close_competing_with_staged_mark(app, monkeypatch):
    enroll(app, "a")
    sid = app.ledger.open("Class")
    stage = app.ledger.stage_mark
    def competing_close(pipe, session, record):
        staged = stage(pipe, session, record)
        app.ledger.finalize(sid)
        return staged
    monkeypatch.setattr(app.ledger, "stage_mark", competing_close)
    with pytest.raises(PipelineError, match="closed"):
        mark(app, sid, "a")
    assert app.ledger.export(sid)["document"]["summary"]["count"] == 0
    assert not app.report(sid)["marks"]


def test_altered_prior_revision_detected(app):
    enroll(app, "a")
    sid = app.ledger.open("Class")
    app.ledger.finalize(sid)
    app.command("correct", dict(session=sid, uid="a", decision="include", reason="Appeal", revision=1))
    state = app.ledger.read(sid)
    state["versions"][0]["document"]["summary"]["count"] = 100
    app.db.set(session_key(sid), canonical(state))
    with pytest.raises(PipelineError, match="register history"):
        app.report(sid)


def test_mixed_signers_only_list_their_sessions(app, monkeypatch):
    mine = app.ledger.open("Class")
    other = Sessions(app.db, os.urandom(32))
    sid = other.open("Independent school")
    assert [row["id"] for row in app.ledger.list_sessions()] == [mine]
    with pytest.raises(PipelineError, match="different signing"):
        app.ledger.read(sid)
    keys = [session_key(mine).encode(), session_key(sid).encode(), session_key("f"*32).encode()]
    monkeypatch.setattr(app.db, "scan_iter", lambda **_: [*keys, *keys])
    assert [row["id"] for row in other.list_sessions()] == [sid]


def test_retention_authenticates_signed_date_before_preview(app):
    sid = app.ledger.open("Class")
    app.ledger.finalize(sid)
    args = dict(cutoff="2099-01-01")
    assert app.command("preview", args)
    state = app.ledger.read(sid)
    state["versions"][-1]["document"]["summary"]["issued"] = "2000-01-01T00:00:00+00:00"
    app.db.set(session_key(sid), canonical(state))
    with pytest.raises(PipelineError, match="signed register history"):
        app.command("preview", args)
    with pytest.raises(PipelineError, match="Preview the same cutoff"):
        app.command("purge", args)
    assert app.db.exists(session_key(sid))


def test_invalid_cutoff_drops_prior_preview(app):
    sid = app.ledger.open("Class")
    app.ledger.finalize(sid)
    args = dict(cutoff="2099-01-01")
    app.command("preview", args)
    with pytest.raises(PipelineError, match="YYYY-MM-DD"):
        app.command("preview", {"cutoff": "2099-02-30"})
    with pytest.raises(PipelineError, match="Preview"):
        app.command("purge", args)


@pytest.mark.parametrize("kind,reason,correct", [
    ("phone photo", "no_face", None), ("video replay", "locked", None),
    ("printed photo", "liveness_rejected", True), ("phone photo", "unknown", False),
    ("impostor", "unknown", True), ("impostor", "blurry", None),
])
def test_trial_measures_the_selected_outcome(app, tmp_path, monkeypatch, kind, reason, correct):
    from privacy.errors import SampleRejected
    enroll(app, "a")
    monkeypatch.setattr(app, "matcher", app.matcher)
    monkeypatch.setattr(app, "ledger", app.ledger)
    monkeypatch.setattr(app, "demo", False)
    def observation(**kwargs):
        if reason == "unknown":
            return "unknown"
        raise SampleRejected("Sample rejected.", reason)
    monkeypatch.setattr(app.matcher, "identify", observation)
    row = app.command("trial", {"kind": kind})
    assert row["correct"] is correct and row["reason"] == reason
    output = tmp_path / "metrics.json"
    app.command("metrics", {"path": output})
    group = json.loads(output.read_text())["trials"][kind]
    assert group["n"] == 1 and group["inconclusive"] == (correct is None)


def test_trial_requires_meaningful_gallery(app):
    with pytest.raises(PipelineError, match="Enroll"):
        app.command("trial", {"kind": "impostor"})
    enroll(app, "a")
    with pytest.raises(PipelineError, match="enrolled student"):
        app.command("trial", {"kind": "genuine", "uid": "missing"})
    assert not app.trials


@pytest.mark.parametrize("revision", [True, 1.0, "1"])
def test_receipt_requires_integer_revision(app, revision):
    enroll(app, "a")
    sid = app.ledger.open("Class")
    mark(app, sid, "a")
    doc = app.ledger.finalize(sid)
    receipt = app.ledger.export(sid, "a")
    with pytest.raises(ValueError, match="revision"):
        verify(doc, dict(receipt, revision=revision), DEMO_PUBLIC, True)


def test_verifier_explains_provisional_receipts(app, tmp_path):
    from student_verifier import verification_result
    enroll(app, "a")
    sid = app.ledger.open("Class")
    mark(app, sid, "a")
    claim = app.ledger.export(sid, "a")
    receipt = tmp_path / "claim.json"
    receipt.write_bytes(canonical(claim))
    signed = tmp_path / "signed.json"
    signed.write_bytes(canonical(app.ledger.finalize(sid)))
    ok, message = verification_result(signed, receipt, None, True)
    assert not ok and "exported public register" in message
    signed.write_bytes(canonical(app.ledger.export(sid)))
    assert verification_result(signed, receipt, None, True)[0]
    receipt.write_bytes(canonical(dict(claim, token="f" * 64)))
    ok, message = verification_result(signed, receipt, None, True)
    assert not ok and "absent" in message and "ffff" not in message


def test_verifier_rejects_non_regular_files(tmp_path):
    from student_verifier import read_document
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="regular document"):
        read_document(fifo)


def test_synthetic_presentation_has_no_liveness_evidence(app):
    enroll(app, "a")
    row = app.command("trial", {"kind": "phone photo", "subject": "a"})
    assert row["correct"] is None and row["reason"] == "synthetic_capture"


def test_blank_demo_subject_cannot_mark_default_student(app):
    enroll(app, "demo-student")
    sid = app.ledger.open("Class")
    with pytest.raises(PipelineError, match="Invalid user ID"):
        app.command("mark", dict(session=sid, subject=""))
    assert not app.report(sid)["marks"]
