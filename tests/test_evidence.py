from privacy.timing import current
from scripts.benchmark import summarize
from scripts.audit_no_disk_writes import audit


def test_summary():
    def action():
        current.get().update(detect=2., antispoof=1., embed=.5)
    assert summarize(4, action)["detect"] == {"mean": 2., "median": 2., "p95": 2.}


def test_audit(tmp_path):
    file = tmp_path / "changed"
    file.write_bytes(b"before")
    def change():
        file.write_bytes(b"BM" + bytes(20))
        return 0
    assert audit([tmp_path], change) == 1
    assert audit([tmp_path], lambda: 0) == 0


def test_calibration_empty(monkeypatch, capsys):
    import sys
    import fakeredis
    from scripts import calibrate_threshold as calibration
    monkeypatch.setattr(calibration, "redis_client", fakeredis.FakeRedis)
    monkeypatch.setattr(calibration, "startup", lambda: None)
    monkeypatch.setattr(sys, "argv", ["calibrate"])
    assert calibration.main() == 0
    assert "at least two users" in capsys.readouterr().out


def test_calibration_exports(tmp_path, monkeypatch):
    import json
    import os
    import sys
    import fakeredis
    import numpy as np
    from privacy.matching import Matcher
    from privacy.store import Store
    from scripts import calibrate_threshold as calibration
    store = Store(fakeredis.FakeRedis())
    matcher = Matcher(store, os.urandom(32), .7, lambda: np.ones(512, "<f4"))
    matcher.enroll("a", "Alice")
    matcher.enroll("a", "Alice")
    matcher.acquire = lambda: -np.ones(512, "<f4")
    matcher.enroll("b", "Bob")
    monkeypatch.setattr(calibration, "redis_client", lambda: store.db)
    monkeypatch.setattr(calibration, "load_key", lambda: matcher.key)
    monkeypatch.setattr(calibration, "startup", lambda: None)
    output = tmp_path / "rates.json"
    csv_path = tmp_path / "rates.csv"
    monkeypatch.setattr(sys, "argv", ["calibrate", "--csv", str(csv_path), "--json", str(output)])
    assert calibration.main() == 0
    data = json.loads(output.read_text())
    assert data["eer"] == 0 and len(data["threshold_far_frr"]) == 66
    assert len(csv_path.read_text().splitlines()) == 67


def test_prefetch_retries_and_publishes_only_complete_file(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from scripts import prefetch_models as prefetch
    from pathlib import Path
    destination = tmp_path / "facenet512_weights.h5"
    attempts = []
    header = b"\x89HDF\r\n\x1a\n"

    def download(name, staged, url):
        assert not destination.exists()
        attempts.append(name)
        Path(staged).write_bytes(b"incomplete" if len(attempts) == 1 else header + bytes(32))

    monkeypatch.setitem(sys.modules, "deepface.commons.file_utils",
                        SimpleNamespace(download_external_file=download))
    pauses = []
    monkeypatch.setattr(prefetch.time, "sleep", pauses.append)
    prefetch.fetch(destination)
    assert len(attempts) == 2 and pauses == [1]
    assert destination.read_bytes().startswith(header)
    assert list(tmp_path.iterdir()) == [destination]


def test_prefetch_inventory_check_only(tmp_path, monkeypatch, capsys):
    import sys
    import pytest
    from scripts import prefetch_models as prefetch
    monkeypatch.setattr(prefetch, "directory", lambda: tmp_path)
    monkeypatch.setattr(prefetch, "fetch", lambda _: pytest.fail("unexpected download"))
    monkeypatch.setattr(sys, "argv", ["prefetch", "--check"])
    assert prefetch.main() == 1
    assert "Ready 0 of 4" in capsys.readouterr().out
    assert not list(tmp_path.iterdir())
