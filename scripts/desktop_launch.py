"""Start the installed live GNOME apps with this desktop's signing identity."""
import argparse
import base64
import os
from pathlib import Path
import resource
import subprocess
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
APPS = {"teacher": "teacher_app.py", "verifier": "student_verifier.py"}
KEYRING_APP = "in.epics.AttendanceTeacher"


def public_key_path():
    config = os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(config) / "epics-attendance" / "school-public-key"


def launch_environment(role):
    pin = public_key_path().read_text(encoding="ascii").strip()
    if len(base64.b64decode(pin, validate=True)) != 32:
        raise ValueError("Invalid public key.")
    env = os.environ.copy()
    env["ZKAUTH_SCHOOL_PUBLIC_KEY"] = pin
    if role == "teacher":
        lookup = subprocess.run(
            ["/usr/bin/secret-tool", "lookup", "application", KEYRING_APP, "public-key", pin],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True, timeout=90,
        )
        seed = lookup.stdout.strip()
        signer = Ed25519PrivateKey.from_private_bytes(base64.b64decode(seed, validate=True))
        if base64.b64encode(signer.public_key().public_bytes_raw()).decode("ascii") != pin:
            raise ValueError("Signing identity mismatch.")
        env["ZKAUTH_SIGNING_SEED"] = seed.decode("ascii")
    else:
        for name in ("ZKAUTH_SIGNING_SEED", "ZKAUTH_KEY", "ZKAUTH_KEY_FILE", "ZKAUTH_NEXT_KEY", "REDIS_PASSWORD"):
            env.pop(name, None)
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=APPS)
    role = parser.parse_args().role
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        env = launch_environment(role)
    except (OSError, ValueError, subprocess.SubprocessError):
        if role == "teacher":
            message = "Unlock your GNOME login keyring and check that its EPICS signing identity matches the saved school public key."
        else:
            message = "Check the saved school public key for the EPICS Student Verifier."
        print(message, file=sys.stderr)
        if Path("/usr/bin/zenity").is_file():
            subprocess.run(["/usr/bin/zenity", "--error", "--title=EPICS Attendance", "--text", message])
        return 1
    os.execve(sys.executable, [sys.executable, str(ROOT / APPS[role])], env)


if __name__ == "__main__":
    raise SystemExit(main())
