"""Command-line webcam authentication, attendance and reporting."""
import argparse
import csv
from datetime import date
import logging
import math
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from redis.exceptions import RedisError

from privacy.capture import BACKENDS, capture
from privacy.config import face_settings, load_key, redis_client
from privacy.cpu import threads
from privacy.encryption import encrypt
from privacy.errors import PipelineError, SampleRejected
from privacy.matching import Matcher
from privacy.memory import wipe
from privacy.models import prepare
from privacy.runtime import startup
from privacy.store import Store
from privacy.timing import collect, measure
from scripts.exports import new_export


def run(camera: int, key: bytes, backend: str | None = None,
        detector: str | None = None, antispoof: bool | None = None) -> bytes:
    """Encrypt one embedding only after relinquishing the camera frame."""
    from privacy.embedding import extract

    vector = None
    try:
        with capture(camera, backend) as frame:
            vector = extract(frame, detector, antispoof)
        return encrypt(vector, key)
    finally:
        if vector is not None:
            wipe(vector)


def main() -> int:
    options = argparse.ArgumentParser(add_help=False)
    options.add_argument("--camera", type=int, default=argparse.SUPPRESS)
    options.add_argument("--backend", choices=BACKENDS, default=argparse.SUPPRESS)
    options.add_argument("--detector", default=argparse.SUPPRESS,
                         help="DeepFace detector (default ZKAUTH_DETECTOR or retinaface)")
    options.add_argument("--no-antispoof", action="store_false", dest="antispoof", default=argparse.SUPPRESS)
    options.add_argument("--verbose", action="store_true", default=argparse.SUPPRESS)
    parser = argparse.ArgumentParser(parents=[options])
    commands = parser.add_subparsers(dest="command")
    for command in ("demo", "enroll", "verify", "identify", "attendance", "attendance-report", "list-users", "delete-user", "logs"):
        sub = commands.add_parser(command, parents=[options])
        if command == "attendance-report":
            sub.add_argument("--date", type=date.fromisoformat)
            sub.add_argument("--csv")
        if command in ("identify", "attendance"):
            sub.add_argument("--loop", action="store_true")
            sub.add_argument("--interval", type=float, default=1.)
        if command in ("enroll", "verify", "delete-user"):
            sub.add_argument("user_id")
        if command == "enroll":
            sub.add_argument("name")
    args = parser.parse_args()
    camera = getattr(args, "camera", 0)
    backend = getattr(args, "backend", None)
    detector = getattr(args, "detector", None)
    antispoof = getattr(args, "antispoof", None)
    startup(getattr(args, "verbose", False))
    verbose = getattr(args, "verbose", False)
    try:
        if args.command in (None, "enroll", "demo", "verify", "identify", "attendance"):
            settings = face_settings(detector, antispoof)
            enabled = settings.antispoof
            prepare(enabled, settings.detector)
            threads(enabled)
            if getattr(args, "loop", False) or verbose:
                warmup(detector, enabled)
        with collect() as timings:
            try:
                return dispatch(args, camera, backend, detector, antispoof, verbose)
            finally:
                if verbose and timings:
                    logging.info("stage_seconds", extra={"metrics": timings})
    except KeyboardInterrupt:
        return 130
    except RedisError:
        logging.error("Redis unavailable. Check host, port, database and password.")
    except PipelineError as error:
        logging.error("%s", error)
    except Exception as error:
        logging.error("Pipeline failed (%s).", type(error).__name__)
    return 1


def warmup(detector, enabled):
    from deepface import DeepFace
    DeepFace.build_model("Facenet512")
    DeepFace.build_model(face_settings(detector, enabled).detector, task="face_detector")
    if enabled:
        model = DeepFace.build_model("Fasnet", task="spoofing")
        if not getattr(model, "_timed", False):
            model.analyze = measure("antispoof")(model.analyze)
            model._timed = True


def repeat(action, loop, interval, verbose):
    if not math.isfinite(interval) or interval < 0:
        raise PipelineError("Interval must be finite and nonnegative.")
    while True:
        with collect() as timings:
            try:
                result = action()
                print(result, flush=True)
            except SampleRejected as error:
                if not loop:
                    raise
                logging.error("%s", error)
            finally:
                if verbose:
                    logging.info("stage_seconds", extra={"metrics": timings})
        if not loop:
            return 2 if result == "unknown" else 0
        time.sleep(interval)


def display_text(value):
    return "".join(char if char.isprintable() else f"\\u{ord(char):04x}" for char in value)


def spreadsheet_text(value):
    value = display_text(value)
    if value.lstrip().startswith(("=", "+", "-", "@", "＝", "＋", "－", "＠")):
        return "'" + value
    return value


def dispatch(args, camera, backend, detector, antispoof, verbose):
    if args.command in (None, "demo"):
        run(camera, AESGCM.generate_key(bit_length=256), backend, detector, antispoof)
        logging.info("Embedding encrypted. Demo ciphertext discarded.")
    elif args.command == "attendance-report":
        day = args.date.isoformat() if args.date else None
        rows = Store(redis_client()).attendance_report(day)
        header = ("user_id", "name", "timestamp_utc", "timestamp_local")
        if args.csv:
            try:
                with new_export(args.csv) as handle:
                    writer = csv.writer(handle)
                    writer.writerow(header)
                    writer.writerows(tuple(map(spreadsheet_text, row)) for row in rows)
            except FileExistsError:
                raise PipelineError("CSV path exists. Choose a fresh filename.") from None
            except OSError:
                raise PipelineError("CSV write failed. Check permissions, space and the output file.") from None
        else:
            print(*header, sep="\t")
            for row in rows:
                print(*map(display_text, row), sep="\t")
    elif args.command == "logs":
        print("timestamp", "user_id", "score", "result", sep="\t")
        for entry in Store(redis_client()).recent():
            print(*map(display_text, entry), sep="\t")
    elif args.command == "list-users":
        store = Store(redis_client())
        for uid in store.users():
            record = store.load(uid)
            if record:
                print(uid, display_text(record.name), record.count, display_text(record.enrolled_at), sep="\t")
    elif args.command == "delete-user":
        Store(redis_client()).delete(args.user_id, load_key())
        print("User deleted.")
    else:
        matcher = Matcher.configured(camera, backend, detector, antispoof)
        if args.command == "enroll":
            matcher.enroll(args.user_id, args.name)
            print("Enrollment saved.")
        elif args.command == "verify":
            decision = matcher.verify(args.user_id)
            print(f"match={decision.match} score={decision.score:.6f} threshold={decision.threshold:g}")
            return 0 if decision.match else 2
        else:
            return repeat(lambda: matcher.identify(attendance=args.command == "attendance"), args.loop, args.interval, verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
