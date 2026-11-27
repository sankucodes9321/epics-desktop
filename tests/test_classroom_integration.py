"""Opt-in storage and CLI integration using a private, disposable server."""
import base64
from concurrent.futures import ThreadPoolExecutor
import csv
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time

import numpy as np
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from redis.exceptions import ConnectionError as RedisConnectionError

from privacy.config import redis_client
from privacy.matching import Matcher
from privacy.store import Store
from scripts.classroom import Classroom

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def private_server(tmp_path, monkeypatch):
    executable = shutil.which("redis-server") or shutil.which("valkey-server")
    if not executable:
        pytest.skip("Install Redis or Valkey for the service integration test.")
    with socket.socket() as port_selector:
        port_selector.bind(("127.0.0.1", 0))
        port = port_selector.getsockname()[1]
    password = secrets.token_urlsafe(32)
    for key, value in {"REDIS_PORT": str(port), "REDIS_HOST": "127.0.0.1",
                       "REDIS_DB": "0", "REDIS_PASSWORD": password}.items():
        monkeypatch.setenv(key, value)
    proc = subprocess.Popen([executable, "--bind", "127.0.0.1", "--port", str(port),
                             "--requirepass", password, "--save", "", "--appendonly", "no",
                             "--dir", str(tmp_path)], stdout=subprocess.DEVNULL)
    db = redis_client()
    try:
        for _ in range(100):
            if proc.poll() is not None:
                pytest.fail("The disposable database could not start.")
            try:
                if db.ping():
                    break
            except RedisConnectionError:
                time.sleep(.05)
        else:
            pytest.fail("The disposable database did not respond.")
        yield db
    finally:
        db.close()
        proc.terminate()
        proc.wait(timeout=10)


@pytest.mark.live
def test_private_server_and_cli(private_server, tmp_path, monkeypatch):
    def cli(*args):
        return subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, capture_output=True,
                              check=True, text=True, timeout=30).stdout

    def encoded(raw):
        return base64.b64encode(raw).decode()

    key, seed, replacement = (os.urandom(32) for _ in range(3))
    pin = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()
    for name, value in (("ZKAUTH_KEY", key), ("ZKAUTH_SIGNING_SEED", seed), ("ZKAUTH_SCHOOL_PUBLIC_KEY", pin)):
        monkeypatch.setenv(name, encoded(value))
    monkeypatch.setenv("ZKAUTH_TIMEZONE", "UTC")
    service = Matcher(Store(private_server), key, .7, lambda: np.ones(512, dtype="<f4"))
    service.enroll("student", "Test student")
    assert service.verify("student").match
    assert "student\tTest student" in cli("main.py", "list-users")
    open_class = ("-m", "scripts.classroom")
    sid = json.loads(cli(*open_class, "open", "Integration class"))
    assert json.loads(cli(*open_class, "list"))[0]["id"] == sid
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.identify(session=(Classroom().ledger, sid)), range(2)))
    assert sorted(row["status"] for row in results) == ["already marked", "marked"]
    assert service.identify(attendance=True).startswith("marked")
    assert service.identify(attendance=True).startswith("already marked today")
    attendance = tmp_path / "daily.csv"
    cli("main.py", "attendance-report", "--csv", attendance)
    with attendance.open(newline="") as handle:
        assert [row["user_id"] for row in csv.DictReader(handle)] == ["student"]
    assert "identified" in cli("main.py", "logs")

    receipt, register = tmp_path / "receipt.json", tmp_path / "register.json"
    cli(*open_class, "receipt", sid, "student", receipt)
    assert json.loads(cli(*open_class, "close", sid))["count"] == 1
    cli(*open_class, "publish", sid, register)
    assert "LIVE: Included in Integration class" in cli("student_verifier.py", "--summary", register, "--receipt", receipt)
    monkeypatch.setenv("ZKAUTH_NEXT_KEY", encoded(replacement))
    assert "Rotated 1 records" in cli("-m", "scripts.rotate_key")
    monkeypatch.setenv("ZKAUTH_KEY", encoded(replacement))
    cli("main.py", "delete-user", "student")
    assert cli("main.py", "list-users") == ""
    assert json.loads(cli(*open_class, "report", sid))["marks"][0]["user_id"] == "student"
