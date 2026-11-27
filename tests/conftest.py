"""Keep offline tests independent of the operator's session and hardware."""
import os
import socket
import subprocess
import sys

import cv2
import pytest


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path, request):
    for name in tuple(os.environ):
        if name.startswith(("ZKAUTH_", "REDIS_")) or name in ("CAPTURE_BACKEND", "DEEPFACE_BACKEND_ENGINE"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("DEEPFACE_HOME", str(tmp_path))
    if request.node.get_closest_marker("live"):
        return
    for name in ("torch", "deepface", "tensorflow", "retinaface"):
        monkeypatch.setitem(sys.modules, name, None)

    def forbidden(*args, **kwargs):
        pytest.fail("Offline test reached a live dependency")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(cv2, "VideoCapture", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr("privacy.config.load_file_key", forbidden)
