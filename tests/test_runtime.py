import sys
from unittest.mock import Mock

import pytest
from main import repeat
from privacy.cpu import defaults, threads
from privacy.models import prepare, warn_disabled
from privacy.store import Store
import fakeredis


def test_disabled_marker(caplog, monkeypatch):
    monkeypatch.setattr("privacy.models.present", lambda _: True)
    warn_disabled.cache_clear()
    prepare(False)
    prepare(False)
    assert caplog.text.count("disabled for testing") == 1
    store = Store(fakeredis.FakeRedis())
    store.audit("a", "match")
    store.antispoof_off = True
    store.audit("a", "match")
    marked, old = store.recent()
    assert marked[-1] == "antispoof=off" and len(old) == 4


def test_cpu(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    defaults()
    import os
    assert os.environ["CUDA_VISIBLE_DEVICES"] == "-1"
    tf, torch = Mock(), Mock()
    torch.cuda.is_available.return_value = False
    monkeypatch.setitem(sys.modules, "tensorflow", tf)
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setenv("ZKAUTH_CPU_THREADS", "3")
    threads.cache_clear()
    threads(True)
    torch.set_num_threads.assert_called_once_with(3)
    tf.config.threading.set_intra_op_parallelism_threads.assert_called_once_with(3)
    threads.cache_clear()


def test_loop_interrupt(monkeypatch):
    import numpy as np
    from privacy.capture import capture
    frame = np.ones((2, 2), dtype=np.uint8)
    monkeypatch.setattr("privacy.capture._opencv", lambda _: frame)
    def action():
        with capture(0, "opencv"):
            raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        repeat(action, True, 0, False)
    assert not frame.any()


@pytest.mark.parametrize("filename", ["facenet512_weights.h5", "retinaface.h5"])
def test_cli_missing_weight_precedes_capture(monkeypatch, filename, caplog):
    import main
    monkeypatch.setattr("privacy.models.present", lambda path: path.name != filename)
    monkeypatch.setattr(main, "run", lambda *_: pytest.fail("unexpected capture"))
    monkeypatch.setattr(main, "threads", lambda *_: pytest.fail("unexpected model setup"))
    monkeypatch.setattr(main, "startup", lambda _: None)
    monkeypatch.setattr(sys, "argv", ["main.py", "demo", "--no-antispoof"])
    assert main.main() == 1
    assert filename in caplog.text and "prefetch_models" in caplog.text


def test_cached_weight_check_validates_header(tmp_path):
    from privacy.models import present
    weight = tmp_path / "retinaface.h5"
    weight.write_bytes(b"download failed")
    assert not present(weight)
    weight.write_bytes(b"\x89HDF\r\n\x1a\n" + bytes(128))
    assert present(weight)


def test_unknown_one_shot_status(capsys):
    assert repeat(lambda: "unknown", False, 1, False) == 2
    assert capsys.readouterr().out.strip() == "unknown"


def test_loop_stops_on_operational_failure(monkeypatch):
    from privacy.errors import PipelineError
    monkeypatch.setattr("main.time.sleep", lambda _: pytest.fail("retried fatal error"))
    with pytest.raises(PipelineError, match="authentication failed"):
        repeat(Mock(side_effect=PipelineError("Template authentication failed.")), True, 1, False)


def test_invalid_cpu_flag_fails_closed(monkeypatch):
    from privacy.errors import PipelineError
    monkeypatch.setenv("ZKAUTH_FORCE_CPU", "typo")
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    defaults()
    import os
    assert os.environ["CUDA_VISIBLE_DEVICES"] == "-1"
    threads.cache_clear()
    with pytest.raises(PipelineError, match="ZKAUTH_FORCE_CPU"):
        threads(False)


def test_rejected_sample_loop_recovers(capsys):
    from privacy.errors import SampleRejected
    action = Mock(side_effect=[SampleRejected("No face detected."), "alice", KeyboardInterrupt])
    with pytest.raises(KeyboardInterrupt):
        repeat(action, True, 0, False)
    assert capsys.readouterr().out.strip() == "alice"
