from collections.abc import Callable, Iterator
from contextlib import contextmanager
import logging
from .config import capture_backend
import os
import fcntl
import stat
import select
import shutil
import subprocess
import time
from typing import BinaryIO

import numpy as np

from .errors import PipelineError
from .timing import measure
from .memory import lock, wipe

BACKENDS = ("gst-pipewire", "opencv")
FRAME_SHAPE = (480, 640, 3)
FRAME_COUNT = 30
TIMEOUT = 20.0


def _last_frame(stream: BinaryIO, before_read: Callable[[], None]) -> np.ndarray:
    """Consume exactly 30 BGR frames, handling reads that split a pixel or row."""
    scratch = lock(np.zeros(FRAME_SHAPE, dtype=np.uint8))
    raw = memoryview(scratch).cast("B")
    try:
        for number in range(FRAME_COUNT):
            offset = 0
            while offset < len(raw):
                before_read()
                size = stream.readinto(raw[offset:])
                if not size:
                    raise PipelineError(f"GStreamer stopped during frame {number + 1}.")
                offset += size
            if number + 1 == FRAME_COUNT:
                return lock(scratch.copy())
    finally:
        raw.release()
        wipe(scratch)
    raise PipelineError("No frames requested.")


@measure("capture")
def _pipewire() -> np.ndarray:
    executable = shutil.which("gst-launch-1.0")
    if executable is None:
        raise PipelineError("gst-launch-1.0 is missing. Install gstreamer1.")
    command = [executable, "-q", "pipewiresrc", f"num-buffers={FRAME_COUNT}", "!",
               "videoconvert", "!", "videoscale", "!",
               "video/x-raw,format=BGR,width=640,height=480", "!", "fdsink", "fd=1"]
    deadline = time.monotonic() + TIMEOUT
    frame = None
    try:
        session_vars = ("HOME", "PATH", "LANG", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS",
                        "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "PIPEWIRE_REMOTE")
        environment = {name: os.environ[name] for name in session_vars if name in os.environ}
        with subprocess.Popen(command, stdout=subprocess.PIPE, bufsize=0, env=environment,
                              stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as process:
            assert process.stdout is not None
            stream = process.stdout

            def wait_readable() -> None:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([stream], [], [], remaining)[0]:
                    raise PipelineError("Timed out waiting for PipeWire camera frames.")

            try:
                frame = _last_frame(stream, wait_readable)
                if process.wait(timeout=max(0, deadline - time.monotonic())):
                    raise PipelineError("GStreamer failed. Check the PipeWire session and camera permissions.")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        return frame
    except BaseException as error:
        if frame is not None:
            wipe(frame)
        if isinstance(error, subprocess.TimeoutExpired):
            raise PipelineError("Timed out waiting for GStreamer to exit.") from None
        if isinstance(error, OSError):
            raise PipelineError("GStreamer pipe failed.") from None
        raise


@measure("capture")
def _opencv(index: int) -> np.ndarray:
    import cv2

    camera = cv2.VideoCapture(index)
    frame = None
    try:
        try:
            if not camera.isOpened():
                raise PipelineError("Cannot open webcam. Check its connection and permissions.")
            ok, frame = camera.read()
            if not ok or frame is None or not frame.size:
                raise PipelineError("Webcam did not deliver a frame.")
        finally:
            camera.release()
        return frame
    except BaseException:
        if frame is not None:
            wipe(frame)
        raise


@contextmanager
def camera_lease():
    path = f"/tmp/zkauth-camera-{os.getuid()}.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except OSError:
        raise PipelineError("Cannot open the camera lock. Check temporary directory permissions.") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise PipelineError("Invalid camera lock file.")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise PipelineError("Camera is in use by another attendance process.") from None
        yield
    finally:
        os.close(fd)


@contextmanager
def capture(index: int = 0, backend: str | None = None) -> Iterator[np.ndarray]:
    """Lend one writable BGR frame until context exit."""
    if type(index) is not int or index < 0:
        raise PipelineError("Camera index must be a nonnegative integer.")
    backend = backend if backend is not None else capture_backend()
    if backend not in BACKENDS:
        raise PipelineError("Capture backend must be gst-pipewire or opencv.")
    with camera_lease():
        frame = None
        try:
            if backend == "gst-pipewire":
                try:
                    frame = _pipewire()
                except PipelineError as error:
                    logging.warning("%s Trying OpenCV.", error)
            if frame is None:
                frame = _opencv(index)
            yield lock(frame)
        finally:
            if frame is not None:
                wipe(frame)
                logging.info("Captured image buffer wiped.")
