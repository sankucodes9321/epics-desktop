"""Compare regular files around one command. File contents never reach stdout."""
import argparse
import os
from pathlib import Path
import stat
import shutil
import tempfile
import subprocess
import sys


def snapshot(roots):
    listing = {}
    errors = []

    def failed(error):
        errors.append(error.filename)
    for root in roots:
        if not root.exists():
            continue
        for parent, dirs, files in os.walk(root, onerror=failed):
            for name in files:
                path = Path(parent) / name
                try:
                    info = path.lstat()
                    if stat.S_ISREG(info.st_mode):
                        listing[path] = (info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                except FileNotFoundError:
                    continue
                except OSError:
                    errors.append(path)
    return listing, errors


def image_magic(path):
    with open(path, "rb", opener=lambda p, flags: os.open(p, flags | os.O_NOFOLLOW | os.O_NONBLOCK)) as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise OSError
        header = handle.read(12)
    return (header.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"BM"))
            or header[:4] == b"RIFF" and header[8:12] == b"WEBP")


def audit(roots, action):
    before, errors = snapshot(roots)
    status = action()
    after, later = snapshot(roots)
    failed = bool(status or errors or later)
    for path in sorted(after):
        if before.get(path) == after[path]:
            continue
        try:
            image = image_magic(path)
            print("IMAGE" if image else "changed", path)
            failed |= image
        except OSError:
            print("unreadable", path)
            failed = True
    for path in set(errors + later):
        print("incomplete", path)
    print("FAIL" if failed else "PASS")
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strace", action="store_true", help="also list write-mode opens")
    parser.add_argument("--user-id", default="alice")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    command = command or [sys.executable, "main.py", "verify", args.user_id]
    home = Path.home()
    roots = [Path.cwd(), Path("/tmp"), Path("/var/tmp"), home / ".cache", home / ".local/share"]
    def action():
        if not args.strace:
            return subprocess.run(command).returncode
        if not shutil.which("strace"):
            print("strace unavailable")
            return 1
        with tempfile.TemporaryDirectory() as work:
            trace = Path(work) / "opens"
            status = subprocess.run(["strace", "-f", "-e", "trace=open,openat,openat2,creat",
                                     "-o", str(trace), "--", *command]).returncode
            with trace.open() as handle:
                for line in handle:
                    if any(flag in line for flag in ("O_WRONLY", "O_RDWR", "creat(")):
                        print(line.rstrip())
            return status
    return audit(roots, action)


if __name__ == "__main__":
    raise SystemExit(main())
