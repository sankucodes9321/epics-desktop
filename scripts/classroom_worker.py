"""One private request pipe per desktop. Model libraries cannot write to the reply pipe."""
import json
import os
import sys


def main():
    with os.fdopen(os.dup(1), "w", buffering=1) as replies, open(os.devnull, "w") as sink:
        os.dup2(sink.fileno(), 1)
        from privacy.runtime import startup
        from scripts.classroom import Classroom, message
        startup()
        app = Classroom(demo="--demo" in sys.argv)
        for line in sys.stdin:
            try:
                request = json.loads(line)
                reply = dict(ok=True, value=app.command(request["action"], request["args"]))
            except KeyboardInterrupt:
                reply = dict(ok=False, error="Cancelled. Refresh the register to check any committed operation.")
            except Exception as error:
                code = getattr(error, "code", "operational_error")
                reply = dict(ok=False, error=message(error), reason=code)
            replies.write(json.dumps(reply, ensure_ascii=True) + "\n")


if __name__ == "__main__":
    main()
