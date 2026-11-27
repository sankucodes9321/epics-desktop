import io
import unittest

import numpy as np

from privacy.capture import FRAME_COUNT, FRAME_SHAPE, _last_frame
from privacy.errors import PipelineError


class ShortReads(io.BytesIO):
    def readinto(self, target: memoryview) -> int:
        self.buffer = target.obj
        return super().readinto(target[:65533])


class FrameTests(unittest.TestCase):
    def test_selects_last_complete_frame(self):
        last = np.arange(np.prod(FRAME_SHAPE), dtype=np.uint8).reshape(FRAME_SHAPE)
        stream = ShortReads(bytes(last.size * (FRAME_COUNT - 1)) + last.tobytes())
        result = _last_frame(stream, lambda: None)
        self.assertTrue(np.array_equal(last, result))
        self.assertTrue(result.flags.owndata and result.flags.writeable)
        self.assertFalse(stream.buffer.any())

    def test_partial_frame_wiped(self):
        stream = ShortReads(b"partial")
        with self.assertRaises(PipelineError):
            _last_frame(stream, lambda: None)
        self.assertFalse(stream.buffer.any())


def test_interrupt_reaps_child(monkeypatch):
    from unittest.mock import MagicMock
    from privacy import capture
    import pytest
    child = MagicMock()
    child.__enter__.return_value = child
    child.poll.return_value = None
    monkeypatch.setattr(capture.shutil, "which", lambda _: "/mock/gst")
    monkeypatch.setattr(capture.subprocess, "Popen", lambda *a, **kw: child)
    monkeypatch.setattr(capture, "_last_frame", MagicMock(side_effect=KeyboardInterrupt))
    with pytest.raises(KeyboardInterrupt):
        capture._pipewire()
    child.kill.assert_called_once()
    child.wait.assert_called_once()


def test_opencv_release_interrupt_wipes_frame(monkeypatch):
    from unittest.mock import Mock
    import pytest
    from privacy.capture import _opencv
    camera = Mock()
    frame = np.ones((2, 2, 3), np.uint8)
    camera.read.return_value = True, frame
    camera.release.side_effect = KeyboardInterrupt
    monkeypatch.setattr("cv2.VideoCapture", lambda _: camera)
    with pytest.raises(KeyboardInterrupt):
        _opencv(0)
    assert not frame.any()


def test_capture_child_has_only_session_environment(monkeypatch):
    from unittest.mock import MagicMock
    from privacy import capture
    monkeypatch.setenv("ZKAUTH_KEY", "dummy")
    monkeypatch.setenv("GST_DEBUG_FILE", "/unused")
    monkeypatch.setenv("REDIS_PASSWORD", "dummy")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/mock/runtime")
    child = MagicMock()
    child.__enter__.return_value = child
    child.wait.return_value = 0
    popen = MagicMock(return_value=child)
    monkeypatch.setattr(capture.subprocess, "Popen", popen)
    monkeypatch.setattr(capture.shutil, "which", lambda _: "/mock/gst")
    monkeypatch.setattr(capture, "_last_frame", lambda *_: np.ones((2, 2), np.uint8))
    capture._pipewire()
    env = popen.call_args.kwargs["env"]
    assert env["XDG_RUNTIME_DIR"] == "/mock/runtime"
    assert not {"ZKAUTH_KEY", "GST_DEBUG_FILE", "REDIS_PASSWORD"}.intersection(env)
    assert popen.call_args.kwargs["stderr"] == capture.subprocess.DEVNULL
