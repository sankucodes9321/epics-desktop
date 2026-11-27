"""Per-lecture attendance with recoverable private claims and signed public snapshots."""
import base64
import hmac
import json
import os
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from redis.exceptions import WatchError

from student_verifier import SCHEME, DEMO_PUBLIC, canonical, commitment, digest, inspect_document, make_path, tree
from .config import decode_key, load_key
from .errors import PipelineError
from .store import KEY_ID, timestamp, user_key

PREFIX = "zkauth:session:v1:"
MAX_STUDENTS = 1000


def text_field(value, limit):
    if not isinstance(value, str) or not value.strip() or not value.isprintable() or len(value) > limit:
        raise PipelineError(f"Enter printable text up to {limit} characters.")
    return value.strip()


def session_key(sid):
    if not re.fullmatch("[a-f0-9]{32}", sid):
        raise PipelineError("Select a valid session ID.")
    return PREFIX + sid


class Sessions:
    def __init__(self, db, seed, demo=False):
        self.db = db
        self.mode = "demo" if demo else "live"
        self.signer = Ed25519PrivateKey.from_private_bytes(seed)
        self.pin = base64.b64encode(self.signer.public_key().public_bytes_raw()).decode()
        if not demo and self.pin == DEMO_PUBLIC:
            raise PipelineError("The public demo identity cannot sign live sessions.")
        self.receipt_seed = hmac.digest(seed, b"zkauth/private-receipts/v1", "sha256")

    @classmethod
    def configured(cls, db):
        raw_seed = os.getenv("ZKAUTH_SIGNING_SEED")
        if not raw_seed:
            raise PipelineError("Provision ZKAUTH_SIGNING_SEED and ZKAUTH_SCHOOL_PUBLIC_KEY for live classes.")
        seed = decode_key(raw_seed)
        active_key = load_key()
        fingerprint = db.get(KEY_ID)
        if fingerprint is not None and not hmac.compare_digest(fingerprint, bytes.fromhex(digest(active_key))):
            raise PipelineError("Configured template key differs from the active gallery key.")
        if hmac.compare_digest(seed, active_key):
            raise PipelineError("Provision a signing seed independent of the template key.")
        service = cls(db, seed)
        if service.pin != os.getenv("ZKAUTH_SCHOOL_PUBLIC_KEY"):
            raise PipelineError("The school public key must match the independently provisioned signing seed.")
        return service

    def open(self, label):
        sid = os.urandom(16).hex()
        state = dict(id=sid, label=text_field(label, 100), mode=self.mode, signer=self.pin,
                     opened=timestamp(), marks={}, versions=[], corrections=[])
        if not self.db.set(session_key(sid), canonical(state), nx=True):
            raise PipelineError("Session ID collision. Retry.")
        return sid

    def read(self, sid, client=None):
        raw = (self.db if client is None else client).get(session_key(sid))
        if raw is None:
            raise PipelineError("Session unavailable. Refresh the session list.")
        return self.decode(sid, raw)

    def decode(self, sid, raw, *, own_only=False):
        try:
            state = json.loads(raw)
            if state["mode"] != self.mode or state["signer"] != self.pin:
                if own_only:
                    return None
                raise PipelineError("Session belongs to a different signing identity.")
            if state["id"] != sid or not isinstance(state["versions"], list):
                raise ValueError
            self.validate(state)
            return state
        except (AttributeError, IndexError, KeyError, TypeError, ValueError, RecursionError):
            raise PipelineError("Invalid classroom record. Check the stored session.") from None

    def validate(self, state):
        sid = state["id"]
        if any(mark["leaf"] != commitment(sid, self.token(state, uid, mark))
               for uid, mark in state["marks"].items()):
            raise PipelineError("Register entries differ from their original commitments or signed summary.")
        if state["versions"]:
            last = state["versions"][-1]
            previous = ""
            try:
                for revision, version in enumerate(state["versions"], start=1):
                    summary, _ = inspect_document(version, self.pin, self.mode == "demo")
                    if (summary["session"] != sid or summary["label"] != state["label"]
                            or summary["revision"] != revision or summary["previous"] != previous):
                        raise ValueError
                    previous = digest(canonical(version["document"]))
            except (InvalidSignature, ValueError, TypeError, KeyError):
                raise PipelineError("Invalid signed register history.") from None
            leaves = sorted(mark["leaf"] for mark in state["marks"].values())
            if leaves != last["commitments"] or self.correction_digest(state) != summary["corrections"]:
                raise PipelineError("Finalized register differs from its signed summary.")

    def list_sessions(self):
        rows = []
        for key in set(self.db.scan_iter(match=PREFIX + "*")):
            raw = self.db.get(key)
            if raw is None:
                continue
            state = self.decode(key.decode()[len(PREFIX):], raw, own_only=True)
            if state is not None:
                row = dict(id=state["id"], label=state["label"], closed=bool(state["versions"]),
                           count=len(state["marks"]))
                rows.append((state["opened"], row))
        return [row for opened, row in sorted(rows, key=lambda item: (item[0], item[1]["id"]), reverse=True)]

    def token(self, state, uid, mark):
        material = [state["id"], uid, mark["name"], mark["time"], mark["salt"]]
        return hmac.digest(self.receipt_seed, canonical(material), "sha256").hex()

    def correction_digest(self, state):
        return hmac.digest(self.receipt_seed, b"corrections/v1" + canonical(state["corrections"]), "sha256").hex()

    def add(self, state, uid, name):
        user_key(uid)
        if len(state["marks"]) >= MAX_STUDENTS:
            raise PipelineError("Session is full.")
        salt = os.urandom(32).hex()
        mark = dict(name=name, time=timestamp(), salt=salt)
        mark["leaf"] = commitment(state["id"], self.token(state, uid, mark))
        state["marks"][uid] = mark

    def stage_mark(self, pipe, sid, record):
        """Join the identification WATCH/EXEC transaction on its existing connection."""
        key = session_key(sid)
        pipe.watch(key)
        state = self.read(sid, pipe)
        if state["versions"]:
            raise PipelineError("This class session is closed.")
        fresh = record.uid not in state["marks"]
        if fresh:
            self.add(state, record.uid, record.name)
        return key, state, fresh

    def seal(self, state):
        leaves = sorted(mark["leaf"] for mark in state["marks"].values())
        levels = tree(leaves)
        versions = state["versions"]
        summary = dict(scheme=SCHEME, mode=self.mode, session=state["id"], label=state["label"],
                       revision=len(versions) + 1, count=len(leaves), root=levels[-1][0],
                       issued=timestamp(), corrections=self.correction_digest(state), previous=digest(canonical(versions[-1]["document"])) if versions else "")
        document = dict(summary=summary, signature=self.signer.sign(canonical(summary)).hex())
        versions.append(dict(document=document, commitments=leaves))

    def finalize(self, sid, change=None):
        key = session_key(sid)
        with self.db.pipeline() as pipe:
            try:
                pipe.watch(key)
                state = self.read(sid, pipe)
                if change is None and state["versions"]:
                    return state["versions"][-1]["document"]
                if change is not None:
                    if not state["versions"]:
                        raise PipelineError("Close the session before issuing a correction.")
                    uid, name, include, reason, expected = change
                    user_key(uid)
                    reason = text_field(reason, 240)
                    if expected != len(state["versions"]):
                        raise PipelineError("Revision changed. Refresh before correcting.")
                    if include == (uid in state["marks"]):
                        raise PipelineError("Correction would leave attendance unchanged.")
                    if include:
                        self.add(state, uid, text_field(name, 128))
                    elif include is False:
                        del state["marks"][uid]
                    state["corrections"].append(dict(uid=uid, included=uid in state["marks"],
                                                     upheld=include is None, reason=reason, time=timestamp()))
                self.seal(state)
                pipe.multi()
                pipe.set(key, canonical(state))
                pipe.execute()
                return state["versions"][-1]["document"]
            except WatchError:
                raise PipelineError("Session changed or commit is uncertain. Refresh before retrying.") from None

    def export(self, sid, uid=None):
        state = self.read(sid)
        if uid is None:
            if not state["versions"]:
                raise PipelineError("Close the session before publishing.")
            return state["versions"][-1]
        if uid not in state["marks"]:
            raise PipelineError("This user has no mark in the selected revision.")
        mark = state["marks"][uid]
        receipt = dict(session=sid, token=self.token(state, uid, mark))
        if state["versions"]:
            version = state["versions"][-1]
            levels = tree(version["commitments"])
            index = levels[0].index(commitment(sid, receipt["token"]))
            receipt.update(revision=version["document"]["summary"]["revision"], index=index, path=make_path(levels, index))
        return receipt
