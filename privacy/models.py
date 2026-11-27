"""Local weight inventory for the pinned DeepFace stack."""
import logging
import os
from functools import cache
from pathlib import Path

from .errors import PipelineError

FAS = ("2.7_80x80_MiniFASNetV2.pth", "4_0_0_80x80_MiniFASNetV1SE.pth")
WEIGHTS = ("facenet512_weights.h5", "retinaface.h5", *FAS)
REPAIR = ("Run pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu "
          "then pip install -r requirements.txt and python -m scripts.prefetch_models")


def directory():
    return Path(os.getenv("DEEPFACE_HOME", Path.home())) / ".deepface" / "weights"


def present(path):
    if not path.is_file():
        return False
    with path.open("rb") as handle:
        header = handle.read(8)
    if path.suffix == ".h5":
        return header == b"\x89HDF\r\n\x1a\n"
    return path.suffix == ".pth" and header.startswith((b"PK\x03\x04", b"\x80"))


@cache
def warn_disabled():
    logging.warning("Anti-spoofing disabled for testing.")


def required_weights(detector, enabled):
    if detector not in ("retinaface", "mtcnn", "opencv"):
        raise PipelineError("Use a provisioned detector: retinaface, mtcnn or opencv.")
    if detector == "retinaface" and os.getenv("DEEPFACE_BACKEND_ENGINE", "tensorflow").lower() != "tensorflow":
        raise PipelineError("Set DEEPFACE_BACKEND_ENGINE=tensorflow for the provisioned RetinaFace weights.")
    required = WEIGHTS[:2] if detector == "retinaface" else WEIGHTS[:1]
    return (*required, *FAS) if enabled else required


def prepare(enabled, detector="retinaface"):
    for name in required_weights(detector, enabled):
        if not present(directory() / name):
            raise PipelineError(f"Missing or invalid {name}. Run python -m scripts.prefetch_models.")

    if not enabled:
        warn_disabled()
        return
    try:
        import torch
    except Exception:
        raise PipelineError("Anti-spoof dependency or weights unavailable. " + REPAIR) from None
