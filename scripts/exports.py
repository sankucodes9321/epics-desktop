"""Publish complete private exports without overwriting an existing destination."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile


@contextmanager
def new_export(path):
    destination = Path(path)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=destination.parent, prefix=".attendance-",
                                         delete=False) as handle:
            staged = Path(handle.name)
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        os.link(staged, destination)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def save_json(path, document):
    with new_export(path) as handle:
        json.dump(document, handle, ensure_ascii=True, allow_nan=False)
        handle.write("\n")
