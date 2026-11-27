import logging

import numpy as np

from .timing import measure
from .models import prepare, REPAIR
from .config import face_settings, number
from .quality import brightness_hint, check_quality
from .errors import PipelineError, SampleRejected
from .memory import lock, wipe


def extract(frame: np.ndarray, detector: str | None = None,
            antispoof: bool | None = None) -> np.ndarray:
    """Represent the single qualifying face as 512 little-endian float32 values."""

    settings = face_settings(detector, antispoof)
    prepare(settings.antispoof, settings.detector)
    from deepface import DeepFace

    try:
        with measure("detect"):
            faces = DeepFace.extract_faces(
                img_path=frame, detector_backend=settings.detector,
                enforce_detection=False, anti_spoofing=settings.antispoof,
            )
    except Exception:
        raise PipelineError("Detection or anti-spoof model failed. " + REPAIR) from None
    if not isinstance(faces, list):
        raise PipelineError("Invalid detector response.")
    try:
        accepted = []
        for face in faces:
            crop = face.get("face") if isinstance(face, dict) else None
            if not isinstance(crop, np.ndarray) or not crop.flags.writeable or crop.ndim != 3 or crop.shape[2] != 3 or not crop.size:
                raise PipelineError("Invalid detector crop.")
            lock(crop)
            confidence = face.get("confidence")
            if (isinstance(confidence, bool) or not isinstance(confidence, (float, int, np.floating))
                    or not 0 <= confidence <= 1):
                raise PipelineError("Invalid detector confidence.")
            area = face.get("facial_area")
            if not isinstance(area, dict) or not all(
                isinstance(area.get(k), (int, np.integer)) and not isinstance(area[k], bool)
                for k in ("x", "y", "w", "h")
            ):
                raise PipelineError("Invalid detector dimensions.")
            width, height = area["w"], area["h"]
            if confidence > 0 and confidence >= settings.confidence and min(width, height) >= settings.pixels:
                accepted.append(face)
            else:
                logging.info("Rejected candidate confidence=%g width=%d height=%d",
                             confidence, width, height)
        if not accepted:
            brightness = float(frame.mean())
            hint = brightness_hint(brightness, settings)
            logging.info("Frame mean brightness=%.2f (%s)", brightness, hint)
            raise SampleRejected(f"No face detected ({hint}).", "no_face")
        if len(accepted) > 1:
            raise SampleRejected(f"Detected {len(accepted)} qualifying faces. Exactly one face is required.", "multiple_faces")

        face = accepted[0]
        if settings.antispoof:
            for candidate in faces:
                require_real(candidate)
        check_quality(frame, face["facial_area"], settings)

        try:
            with measure("embed"):
                result = DeepFace.represent(img_path=face["face"], model_name="Facenet512",
                                            detector_backend="skip")
        except Exception:
            raise PipelineError("Facenet512 representation failed.") from None
        vector = None
        try:
            if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict):
                raise PipelineError("Expected exactly one embedding for the accepted crop.")
            values = result[0].get("embedding")
            try:
                vector = lock(np.array(values, dtype="<f4"))
            except (TypeError, ValueError, OverflowError):
                raise PipelineError("Model returned an invalid embedding.") from None
            if vector.shape != (512,) or not np.isfinite(vector).all():
                raise PipelineError("Model returned an invalid embedding.")
            return vector
        except BaseException:
            if vector is not None:
                wipe(vector)
            raise
        finally:
            if isinstance(result, list):
                for item in result:
                    values = item.get("embedding") if isinstance(item, dict) else None
                    if isinstance(values, list):
                        values[:] = [0.] * len(values)
                    elif isinstance(values, np.ndarray) and values.flags.writeable:
                        wipe(values)
    finally:
        for face in faces:
            crop = face.get("face") if isinstance(face, dict) else None
            if isinstance(crop, np.ndarray) and crop.flags.writeable:
                wipe(crop)


def require_real(face):
    score = face.get("antispoof_score")
    if not isinstance(score, (float, int, np.floating)) or not 0 <= score <= 1:
        raise PipelineError("Missing or invalid anti-spoof score.")
    logging.info("Anti-spoof score", extra={"metrics": {"score": float(score)}})
    if (face.get("is_real") is not True or isinstance(score, bool)
            or score < number("ZKAUTH_ANTISPOOF_MIN_SCORE", .8, 0, 1)):
        raise SampleRejected("Face rejected by anti-spoof check.", "liveness_rejected")
