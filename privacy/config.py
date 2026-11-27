"""Configuration and permission-checked loading of persistent template keys."""
import base64
import binascii
import os
import math
from dataclasses import dataclass
from pathlib import Path
import stat

from redis import Redis

from .cpu import defaults
from .errors import PipelineError

defaults()

ROOT = Path(__file__).resolve().parents[1]


def key_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.resolve().is_relative_to(ROOT):
        raise PipelineError("Choose a key file outside the project.")
    return path


def load_key() -> bytes:
    encoded = os.getenv("ZKAUTH_KEY")
    if encoded is None:
        filename = os.getenv("ZKAUTH_KEY_FILE")
        if not filename:
            raise PipelineError("Set ZKAUTH_KEY or ZKAUTH_KEY_FILE.")
        return load_file_key(filename)
    return decode_key(encoded)


def load_file_key(filename):
    try:
        fd = os.open(key_path(filename), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                raise PipelineError("Key file must be a regular file with mode 0600.")
            encoded = handle.read(100).strip().decode("ascii")
            if handle.read(1):
                raise PipelineError("Key file is too long.")
    except (OSError, UnicodeError):
        raise PipelineError("Cannot read key file. Check its path and permissions.") from None
    return decode_key(encoded)


def decode_key(encoded):
    try:
        key = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise PipelineError("Invalid base64 in AES key.") from None
    if len(key) != 32:
        raise PipelineError("AES key must decode to 32 bytes.")
    return key


def threshold() -> float:
    try:
        value = float(os.getenv("ZKAUTH_THRESHOLD", "0.70"))
        if 0 < value <= 1:
            return value
    except ValueError:
        pass
    raise PipelineError("ZKAUTH_THRESHOLD must be greater than zero and at most 1.")


def redis_client() -> Redis:
    try:
        port = int(os.getenv("REDIS_PORT", "6379"))
        db = int(os.getenv("REDIS_DB", "0"))
        if not 1 <= port <= 65535 or db < 0:
            raise ValueError
    except ValueError:
        raise PipelineError("Invalid REDIS_PORT or REDIS_DB.") from None
    return Redis(host=os.getenv("REDIS_HOST", "localhost"), port=port, db=db,
                 password=os.getenv("REDIS_PASSWORD") or None,
                 socket_connect_timeout=3, socket_timeout=5)


def capture_backend() -> str:
    return os.getenv("CAPTURE_BACKEND", "gst-pipewire")


def number(name, default, lower, upper=None):
    try:
        value = type(default)(os.getenv(name, str(default)))
        if math.isfinite(value) and lower <= value and (upper is None or value <= upper):
            return value
    except (ValueError, OverflowError):
        pass
    raise PipelineError(f"Invalid setting {name}.")


def log_cap() -> int:
    return number("ZKAUTH_LOG_CAP", 1000, 1, 2**31 - 1)


@dataclass(frozen=True)
class FaceSettings:
    detector: str
    antispoof: bool
    confidence: float
    pixels: int
    dark: float
    bright: float
    blur: float
    center: float


def face_settings(detector=None, antispoof=None) -> FaceSettings:
    dark = number("ZKAUTH_MIN_BRIGHTNESS", 40., 0, 255)
    return FaceSettings(
        detector or os.getenv("ZKAUTH_DETECTOR", "retinaface"),
        bool(number("ZKAUTH_ANTISPOOF", 1, 0, 1)) if antispoof is None else antispoof,
        number("ZKAUTH_MIN_CONFIDENCE", .95, 0, 1),
        number("ZKAUTH_MIN_FACE_PX", 100, 1), dark,
        number("ZKAUTH_MAX_BRIGHTNESS", 215., dark, 255),
        number("ZKAUTH_MIN_LAPLACIAN_VAR", 50., 0),
        number("ZKAUTH_MAX_CENTER_OFFSET", .25, 0, .5),
    )


DUPLICATE_SCORE = .98
ENROLL_MIN_SCORE = .5
