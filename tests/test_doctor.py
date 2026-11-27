from unittest.mock import Mock
from scripts import doctor


def test_missing_install(monkeypatch, capsys):
    def missing(_):
        raise ImportError
    monkeypatch.setattr(doctor.importlib, "import_module", missing)
    monkeypatch.setattr(doctor, "check_key", lambda: False)
    monkeypatch.setattr(doctor, "present", lambda _: False)
    monkeypatch.setattr("privacy.config.redis_client", Mock(side_effect=ConnectionError))
    monkeypatch.setattr(doctor.subprocess, "run", Mock(side_effect=FileNotFoundError))
    assert doctor.main() == 1
    assert "FAIL\ttorch" in capsys.readouterr().out


def test_doctor_checks_effective_key(monkeypatch):
    import base64
    import pytest
    from privacy.errors import PipelineError
    monkeypatch.setenv("ZKAUTH_KEY_FILE", "/unused")
    monkeypatch.setattr("privacy.config.load_file_key", lambda *_: pytest.fail("read inactive file"))
    monkeypatch.setenv("ZKAUTH_KEY", base64.b64encode(bytes(32)).decode())
    assert doctor.check_key()
    monkeypatch.setenv("ZKAUTH_KEY", "broken")
    with pytest.raises(PipelineError):
        doctor.check_key()


def test_preflight_follows_configured_capture_and_models(monkeypatch, capsys):
    monkeypatch.setenv("ZKAUTH_FORCE_CPU", "0")
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    monkeypatch.setenv("ZKAUTH_DETECTOR", "opencv")
    monkeypatch.setenv("CAPTURE_BACKEND", "opencv")
    monkeypatch.setenv("ZKAUTH_ANTISPOOF", "0")
    monkeypatch.setattr(doctor, "check_key", lambda: True)
    monkeypatch.setattr(doctor, "present", lambda path: path.name == "facenet512_weights.h5")
    monkeypatch.setattr(doctor.importlib, "import_module", Mock())
    monkeypatch.setattr(doctor.shutil, "which", lambda _: None)
    monkeypatch.setattr(doctor.subprocess, "run", Mock(side_effect=FileNotFoundError))
    monkeypatch.setattr("privacy.config.redis_client", Mock())
    assert doctor.main() == 0
    assert "WARN\tretinaface.h5" in capsys.readouterr().out
    monkeypatch.setenv("ZKAUTH_DETECTOR", "invalid")
    assert doctor.main() == 1
