"""Authenticated reference matrices and vectorized FaceNet512 comparisons."""
import logging
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

import numpy as np

from .capture import capture
from .timing import measure
from .config import DUPLICATE_SCORE, ENROLL_MIN_SCORE, load_key, redis_client, threshold
from .encryption import encrypt, open_into
from .errors import PipelineError
from .memory import lock, wipe
from .store import LIMIT, Record, Store

DIM = 512
ROW_BYTES = DIM * 4


def sample(camera: int, backend: str | None, detector: str | None = None, antispoof: bool | None = None) -> np.ndarray:
    from .embedding import extract

    vector = None
    try:
        with capture(camera, backend) as frame:
            vector = extract(frame, detector, antispoof)
        return vector
    except BaseException:
        if vector is not None:
            wipe(vector)
        raise


def normalize(vector: np.ndarray) -> bool:
    norm = np.linalg.norm(vector)
    if norm == 0 or not np.isfinite(norm):
        return False
    vector /= norm
    return bool(np.isclose(np.linalg.norm(vector), 1., rtol=1e-5))


@measure("match")
def cosine(unit_matrix: np.ndarray, unit_probe: np.ndarray) -> np.ndarray:
    """Score L2-normalized rows in one multiplication. Zero rows score zero."""
    return np.clip(unit_matrix @ unit_probe, -1, 1)


def aad(uid: str, count: int) -> bytes:
    return f"zkauth:v1:Facenet512:512:{uid}:{count}".encode()


@contextmanager
def references(records: Sequence[Record], key: bytes, extra: int = 0) -> Iterator[np.ndarray]:
    """Open each user's ciphertext directly into its rows of one shared matrix."""
    rows = sum(record.count for record in records) + extra
    storage = lock(np.empty(rows * ROW_BYTES + 15, dtype=np.uint8))
    try:
        offset = 0
        for record in records:
            end = offset + record.count * ROW_BYTES
            open_into(record.blob, key, aad(record.uid, record.count),
                      memoryview(storage)[offset:end + 15])
            opened = storage[offset:end].view("<f4").reshape(record.count, DIM)
            squared = np.einsum("ij,ij->i", opened, opened, dtype=np.float64)
            if not np.allclose(squared, 1., rtol=1e-4, atol=0):
                raise PipelineError("Invalid reference vector. Check enrollment integrity.")
            offset = end
        yield storage[:-15].view("<f4").reshape(rows, DIM)
    finally:
        wipe(storage)


@dataclass(frozen=True)
class Decision:
    match: bool
    score: float
    threshold: float


class Matcher:
    def __init__(self, store: Store, key: bytes, cutoff: float,
                 acquire: Callable[[], np.ndarray]):
        self.store = store
        self.key = key
        self.threshold = cutoff
        self.acquire = acquire

    @classmethod
    def configured(cls, camera: int = 0, backend: str | None = None,
                   detector: str | None = None, antispoof: bool | None = None) -> "Matcher":
        from .config import face_settings
        from .models import prepare
        settings = face_settings(detector, antispoof)
        enabled = settings.antispoof
        prepare(enabled, settings.detector)
        store = Store(redis_client())
        store.antispoof_off = not enabled
        return cls(store, load_key(), threshold(), lambda: sample(camera, backend, detector, antispoof))

    @contextmanager
    def probe(self) -> Iterator[np.ndarray]:
        vector = self.acquire()
        try:
            if vector.shape != (DIM,) or not normalize(vector):
                raise PipelineError("Invalid or zero embedding. Retry capture.")
            yield vector
        finally:
            wipe(vector)

    def enroll(self, user_id: str, name: str) -> None:
        if not name.strip() or len(name) > 128 or not name.isprintable():
            raise PipelineError("Name must contain 1 to 128 printable characters.")
        previous = self.store.load(user_id)
        if previous and previous.count >= LIMIT:
            raise PipelineError("User already has five templates.")
        with self.probe() as vector, references([previous] if previous else [], self.key, 1) as matrix:
            if previous:
                best = float(cosine(matrix[:-1], vector).max())
                if best < ENROLL_MIN_SCORE:
                    raise PipelineError("Enrollment rejected: low similarity to existing templates.")
                if best > DUPLICATE_SCORE:
                    logging.warning("Near-duplicate enrollment template", extra={"metrics": {"score": best}})
            matrix[-1] = vector
            blob = encrypt(matrix, self.key, aad(user_id, len(matrix)))
        self.store.save(user_id, name, blob, previous, self.key)

    def verify(self, user_id: str) -> Decision:
        record = self.store.load(user_id)
        if record is None:
            self.store.audit(user_id, "user_not_found")
            raise PipelineError("User not found.")
        if self.store.failures(user_id) >= 5:
            self.store.audit(user_id, "locked")
            raise PipelineError("User locked. Retry after the 60-second lockout.")
        try:
            with self.probe() as vector, references([record], self.key) as matrix:
                score = float(cosine(matrix, vector).max())
        except PipelineError:
            self.store.audit(user_id, "verification_error")
            raise
        decision = Decision(score >= self.threshold, score, self.threshold)
        self.store.finish_verify(record, decision.match, score)
        return decision

    def all_records(self) -> list[Record]:
        return self.store.all_records()

    def identify(self, attendance=False, *, session=None, observation=None) -> str | dict:
        if session is not None and (attendance or self.store.antispoof_off):
            raise PipelineError("Session marking requires a dedicated identification with liveness enabled.")
        revision = self.store.revision()
        records = self.all_records()
        score = None
        record = None
        if records:
            try:
                with self.probe() as vector, references(records, self.key) as matrix:
                    scores = cosine(matrix, vector)
                    starts = np.cumsum([0] + [r.count for r in records[:-1]])
                    per_user = np.maximum.reduceat(scores, starts)
                    score = float(per_user.max())
                    if observation is not None:
                        observation["best"] = score
                        if len(per_user) >= 2:
                            observation["gap"] = score - float(np.partition(per_user, -2)[-2])
                    winners = np.flatnonzero(per_user == score)
                    if score >= self.threshold and len(winners) == 1:
                        record = records[int(winners[0])]
            except PipelineError:
                self.store.audit("unknown", "identification_error")
                raise
        return self.store.finish_identify(record, score, attendance, revision, session=session)
