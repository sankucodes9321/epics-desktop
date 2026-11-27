import logging

import cv2
import numpy as np

from .config import FaceSettings
from .errors import PipelineError, SampleRejected
from .memory import lock, wipe

logger = logging.getLogger(__name__)


def brightness_hint(mean, settings):
    if mean < settings.dark:
        return "too dark"
    if mean > settings.bright:
        return "too bright"
    return "no face in view"


def check_quality(frame: np.ndarray, area: dict, settings: FaceSettings):
    mean = float(frame.mean())
    if not settings.dark <= mean <= settings.bright:
        reject(brightness_hint(mean, settings), brightness=mean)
    height, width = frame.shape[:2]
    x, y, w, h = (area[key] for key in ("x", "y", "w", "h"))
    right, bottom = min(x + w, width), min(y + h, height)
    region = frame[max(y, 0):max(0, bottom), max(x, 0):max(0, right)]
    if not region.size:
        raise PipelineError("Face region outside frame.")
    dx = abs((x + w / 2) / width - .5)
    dy = abs((y + h / 2) / height - .5)
    if max(dx, dy) > settings.center:
        reject("off-center", x_offset=dx, y_offset=dy)
    gray = lock(cv2.cvtColor(region, cv2.COLOR_BGR2GRAY))
    try:
        edges = lock(cv2.Laplacian(gray, cv2.CV_32F))
        try:
            variance = float(cv2.meanStdDev(edges)[1].item() ** 2)
        finally:
            wipe(edges)
    finally:
        wipe(gray)
    metrics = dict(brightness=mean, laplacian_variance=variance, x_offset=dx, y_offset=dy)
    if not np.isfinite(variance) or variance < settings.blur:
        reject("blurry", **metrics)
    logger.debug("Quality accepted", extra={"metrics": metrics})


def reject(hint, **metrics):
    logger.warning(hint, extra={"metrics": metrics})
    raise SampleRejected(f"Frame rejected ({hint}).", hint.replace(" ", "_").replace("-", "_"))
