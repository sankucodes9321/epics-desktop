"""Offline preflight. Run with python -m scripts.doctor."""
import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

from privacy.cpu import defaults, cpu_info, force_cpu
from privacy.config import capture_backend, face_settings, number, threshold
from privacy.capture import BACKENDS
from privacy.models import WEIGHTS, required_weights, directory, present


def check_key():
    from privacy.config import load_key
    return len(load_key()) == 32


def main():
    defaults()
    failed = False

    def check(label, operation, optional=False):
        nonlocal failed
        try:
            value = operation()
            success = bool(value)
        except Exception:
            value = success = False
        state = "PASS" if success else "WARN" if optional else "FAIL"
        failed |= state == "FAIL"
        print(state, label, "" if isinstance(value, bool) else value, sep="\t")

    pipewire = capture_backend() == "gst-pipewire"
    enabled = os.getenv("ZKAUTH_ANTISPOOF", "1") != "0"
    check("Python 3.11", lambda: sys.version_info[:2] == (3, 11))
    check("venv", lambda: sys.prefix != sys.base_prefix)
    for name in ("torch", "tensorflow", "tf_keras", "cv2", "cryptography", "redis", "deepface"):
        check(name, lambda: bool(importlib.import_module(name)), name == "torch" and not enabled)
    check("CPU torch wheel", lambda: importlib.import_module("torch").version.cuda is None, True)
    check("TF_USE_LEGACY_KERAS", lambda: os.getenv("TF_USE_LEGACY_KERAS") == "1")
    if os.getenv("ZKAUTH_FORCE_CPU", "1") != "0":
        check("CUDA_VISIBLE_DEVICES", lambda: os.getenv("CUDA_VISIBLE_DEVICES") == "-1")
    check("CPU model and physical cores", cpu_info)
    check("gst-launch-1.0", lambda: shutil.which("gst-launch-1.0"), optional=not pipewire)
    check("pipewiresrc", lambda: subprocess.run(["gst-inspect-1.0", "pipewiresrc"],
          capture_output=True, timeout=10).returncode == 0, optional=not pipewire)

    def ping():
        from privacy.config import redis_client
        return redis_client().ping()
    check("Redis ping", ping)
    required = set()
    def configuration():
        from privacy.store import attendance_zone
        force_cpu()
        settings = face_settings()
        required.update(required_weights(settings.detector, settings.antispoof))
        threshold()
        number("ZKAUTH_ANTISPOOF_MIN_SCORE", .8, 0, 1)
        number("ZKAUTH_CPU_THREADS", cpu_info()[1], 1)
        return bool(attendance_zone()) and capture_backend() in BACKENDS
    check("capture, detector, CPU threads, threshold and attendance timezone", configuration)
    check("active 32-byte key (external 0600 file or environment)", check_key)
    for name in WEIGHTS:
        check(name, lambda: present(directory() / name), name not in required)
    check("free disk bytes (home)", lambda: shutil.disk_usage(Path.home()).free)
    check("available RAM KiB", lambda: int(next(line for line in Path("/proc/meminfo").read_text()
          .splitlines() if line.startswith("MemAvailable:")).split()[1]))
    check("swap disabled", lambda: len(Path("/proc/swaps").read_text().splitlines()) == 1, True)
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
