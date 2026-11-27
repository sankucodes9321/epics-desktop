"""Provision the pinned DeepFace weight files using its download helper."""
import argparse
from pathlib import Path
import tempfile
import time

from privacy.models import directory, present, WEIGHTS, FAS

RELEASE = "https://github.com/serengil/deepface_models/releases/download/v1.0/"
SILENT = ("https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/raw/master/"
          "resources/anti_spoof_models/")


def fetch(path):
    from deepface.commons.file_utils import download_external_file
    urls = [(SILENT if path.name in FAS else RELEASE) + path.name]
    if path.name == "retinaface.h5":
        urls.append("https://huggingface.co/serengil/deepface/resolve/main/retinaface.h5")
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        for url in urls:
            with tempfile.TemporaryDirectory(dir=path.parent) as work:
                staged = Path(work) / path.name
                try:
                    download_external_file(path.name, str(staged), url)
                    if not present(staged):
                        raise ValueError
                    staged.replace(path)
                    return
                except Exception:
                    pass
        if attempt < 2:
            time.sleep(2 ** attempt)
    raise ValueError("Weight download failed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    ready = 0
    for name in WEIGHTS:
        path = directory() / name
        try:
            if not present(path) and not args.check:
                fetch(path)
            if present(path):
                print(name, path.stat().st_size)
                ready += 1
            else:
                print(name, "missing")
        except Exception:
            print(name, "failed")
    print("Ready", ready, "of", len(WEIGHTS))
    return int(ready != len(WEIGHTS))


if __name__ == "__main__":
    raise SystemExit(main())
