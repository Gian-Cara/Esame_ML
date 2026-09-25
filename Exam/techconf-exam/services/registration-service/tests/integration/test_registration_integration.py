"""
Integration tests for registration-service (T-13).

Starts REAL user-service AND event-service subprocesses, then drives
registration-service through its Flask test client. Verifies:
    - happy path (create user + organizer + published event + register -> 201)
    - missing reference (unknown user_id -> 422 REFERENCE_NOT_FOUND)
    - dependency down (services killed -> 503 DEPENDENCY_UNAVAILABLE)
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
SERVICES_DIR = os.path.abspath(os.path.join(SERVICE_ROOT, ".."))
USER_DIR = os.path.join(SERVICES_DIR, "user-service")
EVENT_DIR = os.path.join(SERVICES_DIR, "event-service")
sys.path.insert(0, SERVICE_ROOT)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_health(url: str, proc: subprocess.Popen, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"process exited early (code {proc.returncode})")
        try:
            if requests.get(url, timeout=1).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {url}")


def _launch(cwd: str, port: int, extra_env: dict | None = None) -> subprocess.Popen:
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["STORAGE_BACKEND"] = "memory"
    if extra_env:
        env.update(extra_env)
    proc = subprocess.Popen(
        [sys.executable, "-m", "app"],
        cwd=cwd, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    return proc


@pytest.fixture
def platform():
    """Launch real user-service and event-service; yield their URLs and procs."""
    user_port = _free_port()
    event_port = _free_port()
    user_url = f"http://127.0.0.1:{user_port}"
    event_url = f"http://127.0.0.1:{event_port}"

    user_proc = _launch(USER_DIR, user_port)
    event_proc = _launch(EVENT_DIR, event_port, {"USER_SERVICE_URL": user_url})
    procs = [user_proc, event_proc]
    try:
        _wait_health(f"{user_url}/health", user_proc)
        _wait_health(f"{event_url}/health", event_proc)
        yield {"user_url": user_url, "event_url": event_url, "procs": procs}
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()


def _reg_client(user_url: str, event_url: str):
    from app import create_app
    app = create_app(storage_backend="memory",
                     user_service_url=user_url, event_service_url=event_url)
    app.config["TESTING"] = True
    return app.test_client()


def _seed(user_url: str, event_url: str):
    """Create an organizer, an attendee, and a published event. Returns ids."""
    organizer = requests.post(f"{user_url}/api/v1/users",
                              json={"first_name": "Org", "last_name": "One",
                                    "email": "org.reg@example.com", "role": "organizer"},
                              timeout=2).json()
    attendee = requests.post(f"{user_url}/api/v1/users",
                             json={"first_name": "Att", "last_name": "One",
                                   "email": "att.reg@example.com", "role": "attendee"},
                             timeout=2).json()
    event = requests.post(f"{event_url}/api/v1/events",
                          json={"title": "Integration Conf", "organizer_id": organizer["id"],
                                "venue": "Hall", "city": "Roma",
                                "start_date": "2026-11-01", "end_date": "2026-11-02",
                                "capacity": 10, "price": 50.00},
                          timeout=2).json()
    # publish it
    requests.patch(f"{event_url}/api/v1/events/{event['id']}",
                   json={"status": "published"}, timeout=2)
    return attendee["id"], event["id"]


@pytest.mark.req("REQ-REG-B01")
def test_register_happy_path_201(platform):
    user_url, event_url = platform["user_url"], platform["event_url"]
    user_id, event_id = _seed(user_url, event_url)
    client = _reg_client(user_url, event_url)
    rv = client.post("/api/v1/registrations",
                     data=json.dumps({"user_id": user_id, "event_id": event_id}),
                     content_type="application/json")
    assert rv.status_code == 201
    data = rv.get_json()
    assert data["status"] == "confirmed"
    assert data["amount"] == 50.00


@pytest.mark.req("REQ-REG-B01")
def test_register_unknown_user_422(platform):
    user_url, event_url = platform["user_url"], platform["event_url"]
    _uid, event_id = _seed(user_url, event_url)
    client = _reg_client(user_url, event_url)
    rv = client.post("/api/v1/registrations",
                     data=json.dumps({"user_id": "00000000-0000-0000-0000-000000000000",
                                      "event_id": event_id}),
                     content_type="application/json")
    assert rv.status_code == 422
    assert rv.get_json()["error"]["code"] == "REFERENCE_NOT_FOUND"


@pytest.mark.req("REQ-REG-B09")
def test_register_dependency_down_503(platform):
    user_url, event_url = platform["user_url"], platform["event_url"]
    user_id, event_id = _seed(user_url, event_url)
    # Kill both dependencies
    for p in platform["procs"]:
        p.terminate()
        p.wait(timeout=5)
    client = _reg_client(user_url, event_url)
    rv = client.post("/api/v1/registrations",
                     data=json.dumps({"user_id": user_id, "event_id": event_id}),
                     content_type="application/json")
    assert rv.status_code == 503
    assert rv.get_json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
