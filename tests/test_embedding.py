import logging
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from privacy.embedding import extract
from privacy.errors import PipelineError


def candidate(confidence=.95, width=100, height=100):
    return {"confidence": confidence, "facial_area": {"x": 40, "y": 40, "w": width, "h": height},
            "is_real": True, "antispoof_score": .9,
            "face": np.ones((height, width, 3), dtype=float)}


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", Mock())
    monkeypatch.setattr("privacy.models.present", lambda path: True)
    api = Mock()
    monkeypatch.setitem(sys.modules, "deepface", SimpleNamespace(DeepFace=api))
    for key in ("ZKAUTH_DETECTOR", "ZKAUTH_MIN_CONFIDENCE", "ZKAUTH_MIN_FACE_PX"):
        monkeypatch.delenv(key, raising=False)
    return api


def test_embed_only_accepted_crop(model, monkeypatch):
    monkeypatch.setenv("ZKAUTH_DETECTOR", "mtcnn")
    frame = np.random.default_rng(2).integers(0, 256, (180, 180, 3), dtype=np.uint8)
    rejected, accepted = candidate(.4), candidate()
    model.extract_faces.return_value = [rejected, accepted]

    def represent(img_path, detector_backend, model_name):
        assert img_path is accepted["face"] and img_path.all()
        assert detector_backend == "skip" and model_name == "Facenet512"
        return [{"embedding": [1.] * 512}]

    model.represent.side_effect = represent
    assert extract(frame, "retinaface").shape == (512,)
    model.extract_faces.assert_called_once_with(img_path=frame, detector_backend="retinaface",
                                               enforce_detection=False, anti_spoofing=True)
    assert all(not f["face"].any() for f in [rejected, accepted])


@pytest.mark.parametrize("specs,brightness,message", [
    ([(.94, 120, 120)], 230, "too bright"),
    ([(.99, 99, 150)], 20, "too dark"),
    ([(.99, 150, 99)], 128, "no face in view"),
    ([(.95, 100, 100)] * 2, 128, "2 qualifying faces"),
    ([], 128, "no face in view"),
])
def test_reject_frame(model, caplog, specs, brightness, message):
    faces = [candidate(*spec) for spec in specs]
    model.extract_faces.return_value = faces
    frame = np.full((180, 180, 3), brightness, dtype=np.uint8)
    with caplog.at_level(logging.INFO), pytest.raises(PipelineError, match=message):
        extract(frame)
    model.represent.assert_not_called()
    assert model.extract_faces.call_args.kwargs["detector_backend"] == "retinaface"
    assert all(not f["face"].any() for f in faces)
    if len(specs) < 2:
        assert f"brightness={brightness:.2f} ({message})" in caplog.text
        for spec in specs:
            assert "confidence=%g width=%d height=%d" % spec in caplog.text


def test_full_frame_fallback(model, monkeypatch):
    monkeypatch.setenv("ZKAUTH_MIN_CONFIDENCE", "0")
    monkeypatch.setenv("ZKAUTH_DETECTOR", "mtcnn")
    model.extract_faces.return_value = [candidate(0)]
    with pytest.raises(PipelineError, match="No face detected"):
        extract(np.zeros((100, 100, 3), dtype=np.uint8))
    assert model.extract_faces.call_args.kwargs["detector_backend"] == "mtcnn"
    model.represent.assert_not_called()


@pytest.mark.parametrize("real", [False, None])
def test_spoof_fails_closed(model, real):
    face = candidate()
    face["is_real"] = real
    model.extract_faces.return_value = [face]
    with pytest.raises(PipelineError, match="anti-spoof"):
        extract(np.full((180, 180, 3), 128, np.uint8))
    model.represent.assert_not_called()
    assert not face["face"].any()


def test_antispoof_override(model):
    model.extract_faces.return_value = []
    with pytest.raises(PipelineError, match="No face"):
        extract(np.zeros((180, 180, 3), np.uint8), antispoof=False)
    assert model.extract_faces.call_args.kwargs["anti_spoofing"] is False


def test_flagged_candidate_rejects_frame(model):
    small = candidate(width=60)
    small["is_real"] = False
    model.extract_faces.return_value = [candidate(), small]
    with pytest.raises(PipelineError, match="anti-spoof"):
        extract(np.full((180, 180, 3), 128, np.uint8))
    model.represent.assert_not_called()

def test_missing_weights(model, monkeypatch):
    monkeypatch.setattr("privacy.models.present", lambda path: path.suffix != ".pth")
    with pytest.raises(PipelineError, match="python -m scripts.prefetch_models"):
        extract(np.zeros((1, 1, 3)))
    model.extract_faces.assert_not_called()


def test_model_exception(model):
    model.extract_faces.side_effect = RuntimeError("private diagnostic")
    with pytest.raises(PipelineError, match="anti-spoof model failed"):
        extract(np.zeros((1, 1, 3)))


def test_low_score(model):
    face = candidate()
    face["antispoof_score"] = .79
    model.extract_faces.return_value = [face]
    with pytest.raises(PipelineError, match="anti-spoof"):
        extract(np.zeros((180, 180, 3)))


def test_missing_verdict_on_small_candidate(model):
    small = candidate(width=60)
    del small["is_real"]
    model.extract_faces.return_value = [candidate(), small]
    with pytest.raises(PipelineError, match="anti-spoof"):
        extract(np.zeros((180, 180, 3)))


def test_invalid_vector_cleared(model, monkeypatch):
    model.extract_faces.return_value = [candidate()]
    monkeypatch.setattr("privacy.embedding.check_quality", lambda *_: None)
    values = [float("nan")] * 512
    model.represent.return_value = [{"embedding": values}]
    with pytest.raises(PipelineError, match="invalid embedding"):
        extract(np.zeros((180, 180, 3)))
    assert values == [0.] * 512


def test_missing_torch(model, monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(PipelineError, match="pip install torch==2.6.0"):
        extract(np.zeros((1, 1, 3)))
    model.extract_faces.assert_not_called()


@pytest.mark.parametrize("confidence", [True, 1.1, float("inf")])
def test_malformed_confidence_rejected(model, confidence):
    face = candidate(confidence)
    model.extract_faces.return_value = [face]
    with pytest.raises(PipelineError, match="Invalid detector confidence"):
        extract(np.zeros((180, 180, 3), dtype=np.uint8))
    model.represent.assert_not_called()
    assert not face["face"].any()


def test_extra_representation_rejected_and_cleared(model, monkeypatch):
    model.extract_faces.return_value = [candidate()]
    monkeypatch.setattr("privacy.embedding.check_quality", lambda *_: None)
    first = [1.] * 512
    second = np.ones(512, dtype="<f4")
    model.represent.return_value = [{"embedding": first}, {"embedding": second}]
    with pytest.raises(PipelineError, match="one embedding"):
        extract(np.zeros((180, 180, 3), np.uint8))
    assert not any(first) and not second.any()


@pytest.mark.parametrize("bad", [None, {"face": []}, {"face": np.ones(4)}])
def test_invalid_detection_cleans_other_crops(model, bad):
    valid = candidate()
    model.extract_faces.return_value = [bad, valid]
    with pytest.raises(PipelineError, match="detector crop"):
        extract(np.zeros((180, 180, 3), np.uint8))
    assert not valid["face"].any()
    model.represent.assert_not_called()


def test_invalid_coordinates_report_operational_error(model):
    face = candidate()
    face["facial_area"]["x"] = None
    model.extract_faces.return_value = [face]
    with pytest.raises(PipelineError, match="detector dimensions"):
        extract(np.zeros((180, 180, 3), np.uint8))
    assert not face["face"].any()


def test_face_entirely_left_of_frame(model):
    face = candidate()
    face["facial_area"]["x"] = -110
    model.extract_faces.return_value = [face]
    with pytest.raises(PipelineError, match="outside frame"):
        extract(np.full((180, 180, 3), 128, np.uint8))
    model.represent.assert_not_called()
