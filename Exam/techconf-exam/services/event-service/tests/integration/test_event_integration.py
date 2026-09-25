"""
Integration tests for event-service (own suite, T-14).

Starts a REAL user-service process on a free port and drives event-service
through its Flask test client, with USER_SERVICE_URL pointing at the real
user-service. Verifies:
    - positive case (valid organizer -> 201)
    - reference not found (organizer_id missing -> 422 REFERENCE_NOT_FOUND)
    - dependency down (user-service killed -> 503 DEPENDENCY_UNAVAILABLE)

Run:
    pytest services/event-service/tests/integration -v
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time

import pytest
import requests

SERVICE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
USER_SERVICE_DIR = os.path.abspath(
    os.path.join(SERVICE_ROOT, "..", "user-service")
)
sys.path.insert(0, SERVICE_ROOT)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_health(url: str, proc: subprocess.Popen, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"user-service exited early (code {proc.returncode})")
        try:
            if requests.get(url, timeout=1).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {url}")


@pytest.fixture
def user_service():
    """Launch a real user-service process; yield its base URL."""
    port = _free_port()
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["STORAGE_BACKEND"] = "memory"
    proc = subprocess.Popen(
        [sys.executable, "-m", "app"],
        cwd=USER_SERVICE_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_health(f"{base_url}/health", proc)
        yield base_url, proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _make_event_client(user_service_url: str):
    from app import create_app
    app = create_app(storage_backend="memory", user_service_url=user_service_url)
    app.config["TESTING"] = True
    return app.test_client()


@pytest.mark.req("REQ-EVT-B01")
def test_create_event_with_real_organizer_returns_201(user_service):
    base_url, _proc = user_service
    # Create an organizer in the real user-service
    resp = requests.post(
        f"{base_url}/api/v1/users",
        json={"first_name": "Ada", "last_name": "Lovelace",
              "email": "ada.integration@example.com", "role": "organizer"},
        timeout=2,
    )
    assert resp.status_code == 201
    organizer_id = resp.json()["id"]

    client = _make_event_client(base_url)
    rv = client.post(
        "/api/v1/events",
        data=json.dumps({
            "title": "Integration Conf",
            "organizer_id": organizer_id,
            "venue": "Main Hall",
            "city": "Milano",
            "start_date": "2026-11-01",
            "end_date": "2026-11-02",
            "capacity": 50,
            "price": 99.00,
        }),
        content_type="application/json",
    )
    assert rv.status_code == 201
    assert rv.get_json()["status"] == "draft"


@pytest.mark.req("REQ-EVT-B01")
def test_create_event_missing_organizer_returns_422(user_service):
    base_url, _proc = user_service
    client = _make_event_client(base_url)
    rv = client.post(
        "/api/v1/events",
        data=json.dumps({
            "title": "Ghost Conf",
            "organizer_id": "00000000-0000-0000-0000-000000000000",
            "venue": "Nowhere",
            "city": "Void",
            "start_date": "2026-11-01",
            "end_date": "2026-11-02",
            "capacity": 10,
            "price": 0.00,
        }),
        content_type="application/json",
    )
    assert rv.status_code == 422
    assert rv.get_json()["error"]["code"] == "REFERENCE_NOT_FOUND"


@pytest.mark.req("REQ-EVT-B05")
def test_create_event_user_service_down_returns_503(user_service):
    base_url, proc = user_service
    # Create organizer first while service is alive
    resp = requests.post(
        f"{base_url}/api/v1/users",
        json={"first_name": "Bob", "last_name": "Down",
              "email": "bob.down@example.com", "role": "organizer"},
        timeout=2,
    )
    organizer_id = resp.json()["id"]

    # Now kill user-service
    proc.terminate()
    proc.wait(timeout=5)

    client = _make_event_client(base_url)
    rv = client.post(
        "/api/v1/events",
        data=json.dumps({
            "title": "Doomed Conf",
            "organizer_id": organizer_id,
            "venue": "Hall",
            "city": "Roma",
            "start_date": "2026-11-01",
            "end_date": "2026-11-02",
            "capacity": 10,
            "price": 0.00,
        }),
        content_type="application/json",
    )
    assert rv.status_code == 503
    assert rv.get_json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
