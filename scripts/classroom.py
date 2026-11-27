"""Teacher application services and session CLI."""
import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
import json
import os
import subprocess
import sys
import time

from redis.exceptions import RedisError, WatchError
from privacy.config import face_settings, redis_client
from privacy.cpu import defaults, threads
from privacy.errors import PipelineError, SampleRejected
from privacy.matching import Matcher
from privacy.runtime import startup
from privacy.sessions import PREFIX, Sessions
from privacy.store import Store, attendance_zone, local_timestamp, user_key
from student_verifier import canonical, digest
from scripts.exports import save_json

TRIALS = ("genuine", "impostor", "phone photo", "printed photo", "video replay")


@dataclass
class TrialTotals:
    n: int = 0
    correct: int = 0
    inconclusive: int = 0
    seconds: float = 0
    gap_sum: float = 0
    gap_count: int = 0
    reasons: Counter = field(default_factory=Counter)

    def add(self, row):
        self.n += 1
        self.correct += row["correct"] is True
        self.inconclusive += row["correct"] is None
        self.reasons[row["reason"]] += 1
        self.seconds += row["seconds"]
        if "gap" in row:
            self.gap_sum += row["gap"]
            self.gap_count += 1

    def summary(self):
        result = dict(n=self.n, correct=self.correct, inconclusive=self.inconclusive,
                      reasons=dict(self.reasons), mean_seconds=self.seconds / self.n)
        if self.gap_count:
            result["mean_top_two_gap"] = self.gap_sum / self.gap_count
        return result


class Classroom:
    def __init__(self, demo=False):
        self.demo = demo
        self.trials = defaultdict(TrialTotals)
        self.preview = None

    @cached_property
    def db(self):
        if self.demo:
            import fakeredis
            return fakeredis.FakeRedis()
        return redis_client()

    @cached_property
    def ledger(self):
        return Sessions(self.db, bytes(32), demo=True) if self.demo else Sessions.configured(self.db)

    @cached_property
    def matcher(self):
        if self.demo:
            return Matcher(Store(self.db), os.urandom(32), .70, self.synthetic)
        from main import warmup
        settings = face_settings()
        if not settings.antispoof:
            raise PipelineError("Teacher capture requires liveness. Enable ZKAUTH_ANTISPOOF or use synthetic demo.")
        service = Matcher.configured(antispoof=True)
        threads(True)
        warmup(settings.detector, True)
        return service

    def synthetic(self):
        import numpy as np
        seed = int(digest(self.subject.encode())[:16], 16)
        return np.random.default_rng(seed).standard_normal(512).astype("<f4")

    def report(self, sid):
        state = self.ledger.read(sid)
        zone = attendance_zone()
        return dict(label=state["label"], revision=len(state["versions"]),
                    marks=[dict(user_id=uid, name=m["name"], utc=m["time"],
                                local=local_timestamp(m["time"], zone))
                           for uid, m in sorted(state["marks"].items())], corrections=state["corrections"])

    def inventory(self, cutoff, client=None, keys=None):
        db = self.db if client is None else client
        if keys is None:
            keys = sorted(set(self.db.scan_iter(match=PREFIX + "*")) |
                          set(self.db.scan_iter(match="zkauth:attendance:????-??-??")))
        selected = {}
        for key in keys:
            name = key.decode()
            if name.startswith(PREFIX):
                raw = db.get(key)
                if raw:
                    state = self.ledger.decode(name[len(PREFIX):], raw, own_only=True)
                    if state and state["versions"]:
                        issued = state["versions"][-1]["document"]["summary"]["issued"]
                        if local_timestamp(issued, attendance_zone())[:10] < cutoff:
                            selected[name] = digest(raw)
            elif date.fromisoformat(name[-10:]).isoformat() < cutoff:
                rows = db.hgetall(key)
                if rows:
                    selected[name] = digest(canonical(sorted((k.hex(), v.hex()) for k, v in rows.items())))
        return selected

    def retention(self, cutoff, confirm):
        if not confirm:
            self.preview = None
        try:
            cutoff = date.fromisoformat(cutoff).isoformat()
        except (TypeError, ValueError):
            raise PipelineError("Enter a cutoff date in YYYY-MM-DD format.") from None
        self.ledger
        if not confirm:
            self.preview = cutoff, self.inventory(cutoff)
            return sorted(self.preview[1])
        if self.preview is None or self.preview[0] != cutoff:
            raise PipelineError("Preview the same cutoff before deletion.")
        _, selected = self.preview
        self.preview = None
        if selected:
            keys = [k.encode() for k in selected]
            with self.db.pipeline() as pipe:
                pipe.watch(*keys)
                if self.inventory(cutoff, pipe, keys) != selected:
                    raise PipelineError("Records changed. Preview again.")
                pipe.multi()
                pipe.delete(*keys)
                pipe.execute()
        return len(selected)

    def trial(self, kind, expected):
        if kind not in TRIALS:
            raise PipelineError("Select a trial type.")
        if kind == "genuine":
            user_key(expected)
        if not self.matcher.store.users():
            raise PipelineError("Enroll a student before running an evaluation.")
        if kind == "genuine" and self.matcher.store.load(expected) is None:
            raise PipelineError("Choose an enrolled student for a genuine trial.")
        start = time.monotonic()
        metrics = {}
        reason = "accepted"
        try:
            winner = self.matcher.identify(observation=metrics)
            if winner == "unknown":
                reason = "unknown"
        except SampleRejected as error:
            winner = None
            reason = error.code
        if kind == "genuine":
            correct = winner == expected
        elif kind == "impostor":
            correct = winner == "unknown" if winner is not None else None
        elif self.demo:
            correct = None
            reason = "synthetic_capture"
        elif reason == "liveness_rejected":
            correct = True
        else:
            correct = False if winner is not None else None
        row = dict(kind=kind, reason=reason, correct=correct, seconds=time.monotonic()-start, **metrics)
        self.trials[kind].add(row)
        return row

    def command(self, action, args):
        sid = args.get("session", "")
        uid = args.get("uid", "")
        if self.demo and action in ("enroll", "verify", "mark", "trial"):
            self.subject = args.get("subject", uid or "demo-student")
            user_key(self.subject)
        if action == "check":
            if self.demo:
                return "Synthetic demo. Camera, models and real Redis are unused."
            process = subprocess.run([sys.executable, "-m", "scripts.doctor"], capture_output=True,
                                     text=True, timeout=120)
            rows = [line for line in process.stdout.splitlines() if line.startswith(("PASS\t", "FAIL\t", "WARN\t"))]
            if process.returncode and not any(line.startswith("FAIL\t") for line in rows):
                rows.append("FAIL\tDoctor did not complete.")
            try:
                self.ledger
                signing = "PASS"
            except (PipelineError, RedisError):
                signing = "FAIL"
            return "\n".join([*rows, signing + "\tSchool signing identity"])
        if action == "list":
            return self.ledger.list_sessions()
        if action == "open":
            return self.ledger.open(args["label"])
        if action == "enroll":
            self.matcher.enroll(uid, args["name"])
            return "Enrollment saved."
        if action == "verify":
            decision = self.matcher.verify(uid)
            return dict(match=decision.match, score=decision.score)
        if action == "mark":
            if self.ledger.read(sid)["versions"]:
                raise PipelineError("Session is closed.")
            return self.matcher.identify(session=(self.ledger, sid))
        if action == "report":
            return self.report(sid)
        if action == "close":
            return self.ledger.finalize(sid)["summary"]
        if action == "correct":
            if args["decision"] not in ("include", "remove", "uphold"):
                raise PipelineError("Choose include, remove or uphold.")
            include = {"include": True, "remove": False, "uphold": None}[args["decision"]]
            record = Store(self.db).load(uid) if include else None
            if include and record is None:
                raise PipelineError("Enroll this user before recording a manual correction.")
            change = uid, record.name if record else "", include, args["reason"], int(args["revision"])
            return self.ledger.finalize(sid, change)["summary"]
        if action in ("receipt", "publish"):
            if action == "receipt":
                user_key(uid)
            save_json(args["path"], self.ledger.export(sid, uid if action == "receipt" else None))
            return "Export saved."
        if action == "qr":
            from scripts.public_qr import matrix
            return matrix(canonical(self.ledger.export(sid)["document"]))
        if action == "trial":
            return self.trial(args["kind"], uid)
        if action == "metrics":
            groups = {kind: totals.summary() for kind, totals in self.trials.items()}
            save_json(args["path"], dict(mode=self.ledger.mode, trials=groups))
            return "Aggregate results saved."
        if action in ("preview", "purge"):
            return self.retention(args["cutoff"], action == "purge")
        raise PipelineError("Unknown classroom operation.")


def message(error):
    if isinstance(error, FileExistsError):
        return "Choose a new output filename."
    if isinstance(error, WatchError):
        return "Transaction changed or outcome uncertain. Refresh before retrying."
    if isinstance(error, RedisError):
        return "Redis unavailable or invalid. Check connection, credentials and session state."
    if isinstance(error, PipelineError):
        return str(error)
    if isinstance(error, OSError):
        return "File or device unavailable. Check permissions and available space."
    return "Invalid input or unexpected dependency error. Check setup and selected session."


def main():
    defaults()
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action, args in {"check": (), "list": (), "open": ("label",), "mark": ("session",),
                         "close": ("session",), "report": ("session",),
                         "publish": ("session", "path"), "receipt": ("session", "uid", "path")}.items():
        sub = commands.add_parser(action)
        for name in args:
            sub.add_argument(name)
    args = vars(parser.parse_args())
    startup()
    try:
        result = Classroom().command(args.pop("action"), args)
        print(json.dumps(result, ensure_ascii=True))
        return 2 if result == "unknown" else 0
    except Exception as error:
        print(message(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
