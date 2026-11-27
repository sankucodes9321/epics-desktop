"""Redis hashes contain one authenticated, encrypted template matrix per user."""
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from zoneinfo import TZPATH, ZoneInfo, ZoneInfoNotFoundError
import json
import hashlib
import re

from redis import Redis
from redis.exceptions import WatchError

from .config import log_cap
from .errors import PipelineError, SampleRejected

PREFIX = "zkauth:user:"
ACCESS = "zkauth:access"
LIMIT = 5
MAX_ATTEMPTS = 8
REVISION = "zkauth:revision"
KEY_ID = "zkauth:key-id"


def attendance_zone():
    configured = os.getenv("ZKAUTH_TIMEZONE")
    if configured is not None:
        try:
            return ZoneInfo(configured)
        except (ValueError, ZoneInfoNotFoundError):
            raise PipelineError("ZKAUTH_TIMEZONE must be a valid IANA timezone name.") from None

    system = os.getenv("TZ")
    try:
        if system:
            system = system.removeprefix(":")
            if not os.path.isabs(system):
                return ZoneInfo(system)
            for root in TZPATH:
                path = Path(system)
                if path.is_relative_to(root):
                    return ZoneInfo(str(path.relative_to(root)))
            if system != "/etc/localtime":
                return ZoneInfo("Asia/Kolkata")
        with Path("/etc/localtime").open("rb") as handle:
            return ZoneInfo.from_file(handle)
    except (OSError, ValueError, ZoneInfoNotFoundError):
        return ZoneInfo("Asia/Kolkata")


def local_timestamp(utc_stamp, zone):
    return datetime.fromisoformat(utc_stamp).astimezone(zone).isoformat()


def attendance_entry(raw, uid):
    try:
        entry = json.loads(raw)
        stamp = datetime.fromisoformat(entry["timestamp"])
        if (entry["user_id"] != uid or not isinstance(entry["name"], str)
                or stamp.tzinfo != timezone.utc or entry["timestamp"] != stamp.isoformat()):
            raise ValueError
        return entry
    except (TypeError, KeyError, ValueError):
        raise PipelineError("Invalid attendance data. Check Redis integrity.") from None


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def user_key(uid: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", uid) or uid == "unknown":
        raise PipelineError("Invalid user ID (use 1 to 128 letters, digits, dots, underscores or hyphens; unknown is reserved).")
    return PREFIX + uid


@dataclass(frozen=True)
class Record:
    uid: str
    name: str
    enrolled_at: str
    count: int
    blob: bytes


class Store:
    def __init__(self, client: Redis):
        self.antispoof_off = False
        self.db = client
        self.log_cap = log_cap()

    def load(self, uid: str) -> Record | None:
        fields = self.db.hgetall(user_key(uid))
        if not fields:
            return None
        try:
            count = int(fields[b"count"])
            if (fields[b"model"] != b"Facenet512" or fields[b"dimension"] != b"512"
                    or not 1 <= count <= LIMIT):
                raise ValueError
            return Record(uid, fields[b"name"].decode(), fields[b"enrolled_at"].decode(),
                          count, fields[b"templates"])
        except (ValueError, KeyError):
            raise PipelineError("Invalid reference metadata in Redis.") from None

    def users(self) -> list[str]:
        return sorted({k[len(PREFIX):].decode() for k in self.db.scan_iter(match=PREFIX + "*")})

    def all_records(self):
        return [r for uid in self.users() if (r := self.load(uid)) is not None]

    def save(self, uid: str, name: str, blob: bytes, previous: Record | None, encryption_key: bytes) -> None:
        key = user_key(uid)
        count = previous.count + 1 if previous else 1
        if count > LIMIT:
            raise PipelineError("User already has five templates.")
        with self.db.pipeline() as pipe:
            try:
                pipe.watch(key, KEY_ID, REVISION)
                self.revision(pipe)
                active = pipe.get(KEY_ID)
                if active is not None and active != hashlib.sha256(encryption_key).digest():
                    raise PipelineError("Key has changed. Load the active key file.")
                if pipe.hget(key, "templates") != (previous.blob if previous else None):
                    raise PipelineError("Enrollment changed concurrently. Retry enrollment.")
                if active is None:
                    from .matching import references
                    for enrolled in self.users():
                        record = self.load(enrolled)
                        if record is None:
                            raise PipelineError("Enrollment changed concurrently. Retry enrollment.")
                        with references([record], encryption_key):
                            pass
                if self.antispoof_off:
                    self.watch_access(pipe)
                pipe.multi()
                if active is None:
                    pipe.set(KEY_ID, hashlib.sha256(encryption_key).digest())
                if self.antispoof_off:
                    self.append_event(pipe, uid, "enrolled", None)
                pipe.incr(REVISION)
                pipe.hset(key, mapping=dict(name=name, enrolled_at=previous.enrolled_at if previous else timestamp(),
                                            model="Facenet512", dimension=512, count=count, templates=blob))
                pipe.execute()
            except WatchError as error:
                self.retry_conflict(error, pipe)
                raise PipelineError("Enrollment changed concurrently. Retry enrollment.") from None

    def delete(self, uid: str, encryption_key: bytes) -> None:
        from .matching import references
        key = user_key(uid)
        with self.db.pipeline() as pipe:
            try:
                pipe.watch(key, REVISION)
                self.revision(pipe)
                record = self.load(uid)
                if record is None:
                    raise PipelineError("User not found.")
                with references([record], encryption_key):
                    pass
                pipe.multi()
                pipe.delete(key)
                pipe.delete("zkauth:fail:" + uid)
                pipe.incr(REVISION)
                pipe.execute()
            except WatchError as error:
                self.retry_conflict(error, pipe)
                raise PipelineError("Gallery changed. Check the user before retrying deletion.") from None

    def revision(self, client=None):
        raw = (self.db if client is None else client).get(REVISION)
        if raw is not None and (not re.fullmatch(rb"0|[1-9][0-9]{0,18}", raw)
                                or int(raw) >= 2**63 - 1):
            raise PipelineError("Invalid gallery revision. Check Redis integrity.")
        return raw

    @staticmethod
    def retry_conflict(error, pipe):
        if error.args != ("Watched variable changed.",):
            raise PipelineError("Redis transaction outcome uncertain. Check logs before retrying.") from None
        pipe.reset()

    @staticmethod
    def failure_count(client, counter):
        value = client.get(counter)
        if value is None:
            return 0
        if value not in (b"0", b"1", b"2", b"3", b"4", b"5"):
            raise PipelineError("Invalid lockout state. Check Redis integrity.")
        return int(value)

    def failures(self, uid: str) -> int:
        return self.failure_count(self.db, "zkauth:fail:" + uid)

    @staticmethod
    def watch_access(pipe):
        pipe.watch(ACCESS)
        if pipe.type(ACCESS) not in (b"none", b"stream"):
            raise PipelineError("Invalid access log type. Check Redis integrity.")

    def audit(self, uid: str, result: str, score: float | None = None) -> None:
        self.append_event(self.db, uid, result, score)

    def append_event(self, client, uid, result, score):
        client.xadd(ACCESS, self.event(uid, result, score), maxlen=self.log_cap, approximate=False)

    def recent(self, count=20):
        for _, fields in self.db.xrevrange(ACCESS, count=min(count, self.log_cap)):
            row = tuple(fields[k].decode() for k in (b"timestamp", b"user_id", b"score", b"result"))

            yield row + (("antispoof=off",) if b"antispoof" in fields else ())

    def event(self, uid: str, result: str, score: float | None) -> dict[str, str]:
        return dict(timestamp=timestamp(), user_id=uid, score="" if score is None else str(score),
                    result=result, **({"antispoof": "off"} if self.antispoof_off else {}))

    def finish_verify(self, record: Record, matched: bool, score: float) -> None:
        """Serialize decisions, counter changes and audit entries across clients."""
        key = user_key(record.uid)
        counter = "zkauth:fail:" + record.uid
        with self.db.pipeline() as pipe:
            for _ in range(MAX_ATTEMPTS):
                try:
                    self.watch_access(pipe)
                    pipe.watch(counter, key)
                    if pipe.hget(key, "templates") != record.blob:
                        raise PipelineError("Enrollment changed during verification. Retry.")
                    failures = self.failure_count(pipe, counter)
                    locked = failures >= 5
                    pipe.multi()
                    if locked:
                        result = "locked"
                    elif matched:
                        pipe.delete(counter)
                        result = "match"
                    else:
                        failures += 1
                        pipe.set(counter, failures, ex=60 if failures == 5 else None)
                        result = "reject"
                    self.append_event(pipe, record.uid, result, None if locked else score)
                    pipe.execute()
                    if locked:
                        raise SampleRejected("User locked. Retry after the 60-second lockout.", "locked")
                    return
                except WatchError as error:
                    self.retry_conflict(error, pipe)
        raise PipelineError("Redis is busy. Retry verification.")

    def finish_identify(self, record, score, attendance, revision, session=None):
        with self.db.pipeline() as pipe:
            for _ in range(MAX_ATTEMPTS):
                try:
                    self.watch_access(pipe)
                    pipe.watch(REVISION)
                    if pipe.get(REVISION) != revision:
                        raise PipelineError("Gallery changed during identification. Retry.")
                    if record is None:
                        pipe.multi()
                        self.append_event(pipe, "unknown", "unknown", score)
                        pipe.execute()
                        return "unknown"
                    key = user_key(record.uid)
                    counter = "zkauth:fail:" + record.uid
                    pipe.watch(key, counter)
                    if pipe.hget(key, "templates") != record.blob:
                        raise PipelineError("Enrollment changed during identification. Retry.")
                    locked = self.failure_count(pipe, counter) >= 5
                    if attendance and not locked:
                        now = timestamp()
                        entry = dict(user_id=record.uid, name=record.name, timestamp=now, score=score)
                        zone = attendance_zone()
                        day = local_timestamp(now, zone)[:10]
                        daily_key = "zkauth:attendance:" + day
                        pipe.watch(daily_key)
                        previous = pipe.hget(daily_key, record.uid)
                        stored = attendance_entry(previous, record.uid)["timestamp"] if previous is not None else now
                    mark = None
                    if session is not None and not locked:
                        ledger, sid = session
                        mark = ledger.stage_mark(pipe, sid, record)
                    pipe.multi()
                    if mark is not None and mark[2]:
                        pipe.set(mark[0], json.dumps(mark[1]))
                    if attendance and not locked:
                        pipe.hsetnx(daily_key, record.uid, json.dumps(entry))
                    self.append_event(pipe, record.uid, "locked" if locked else "identified", score)
                    result = pipe.execute()
                    if locked:
                        raise SampleRejected("User locked. Retry after the 60-second lockout.", "locked")
                    if mark is not None:
                        return dict(user_id=record.uid, status="marked" if mark[2] else "already marked")
                    if attendance:
                        status = "marked" if result[0] else "already marked today"
                        return f"{status}\ttimestamp_utc={stored}\ttimestamp_local={local_timestamp(stored, zone)}"
                    return record.uid
                except WatchError as error:
                    self.retry_conflict(error, pipe)
        raise PipelineError("Redis is busy. Retry identification.")

    def attendance_report(self, day=None):
        zone = attendance_zone()
        if day is None:
            day = local_timestamp(timestamp(), zone)[:10]
        records = self.db.hgetall("zkauth:attendance:" + day)
        for uid in sorted(records):
            entry = attendance_entry(records[uid], uid.decode())
            yield entry["user_id"], entry["name"], entry["timestamp"], local_timestamp(entry["timestamp"], zone)
