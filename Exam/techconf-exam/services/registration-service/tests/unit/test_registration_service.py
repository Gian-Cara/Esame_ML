"""
Unit tests for registration-service (T-12).
- All three backends
- user-service AND event-service mocked with responses
- Contract validation
- Covers capacity, duplicate, not-published, transition, stats, 503
"""
from __future__ import annotations

import json
import os
import sys

import pytest
import requests
import responses as resp_lib

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
sys.path.insert(0, REPO_ROOT)
from contracts.validator import assert_matches_contract

SERVICE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, SERVICE_ROOT)

from app import create_app
from app.repository import (
    MemoryRegistrationRepository,
    JsonRegistrationRepository,
    SqliteRegistrationRepository,
)
from app.service import RegistrationService, NotFoundError


USER_URL = "http://mock-user"
EVENT_URL = "http://mock-event"

USER = {"id": "user-1", "role": "attendee", "first_name": "A", "last_name": "B",
        "email": "a@b.com", "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}

EVENT_PUBLISHED = {
    "id": "event-1", "title": "Conf", "organizer_id": "org-1",
    "venue": "Hall", "city": "Roma", "start_date": "2026-10-01", "end_date": "2026-10-02",
    "capacity": 2, "price": 149.00, "status": "published",
    "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
}


class _Adapter:
    def __init__(self, rv):
        self.status_code = rv.status_code
        self.headers = rv.headers
        self.text = rv.data.decode("utf-8") if rv.data else ""
        self._data = rv.data

    def json(self):
        return json.loads(self._data)


def _adapt(rv):
    return _Adapter(rv)


@pytest.fixture
def client(tmp_path):
    app = create_app(storage_backend="memory",
                     user_service_url=USER_URL, event_service_url=EVENT_URL)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def client_json(tmp_path):
    app = create_app(storage_backend="json", data_dir=str(tmp_path),
                     user_service_url=USER_URL, event_service_url=EVENT_URL)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def client_sqlite(tmp_path):
    app = create_app(storage_backend="sqlite", data_dir=str(tmp_path),
                     user_service_url=USER_URL, event_service_url=EVENT_URL)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(params=["memory", "json", "sqlite"])
def repo(request, tmp_path):
    if request.param == "memory":
        return MemoryRegistrationRepository()
    if request.param == "json":
        return JsonRegistrationRepository(str(tmp_path))
    return SqliteRegistrationRepository(str(tmp_path))


def _mock_user_ok(uid="user-1"):
    resp_lib.add(resp_lib.GET, f"{USER_URL}/api/v1/users/{uid}", json={**USER, "id": uid}, status=200)


def _mock_user_404(uid="user-1"):
    resp_lib.add(resp_lib.GET, f"{USER_URL}/api/v1/users/{uid}",
                 json={"error": {"code": "NOT_FOUND", "message": "x"}}, status=404)


def _mock_event(event=None, eid="event-1"):
    resp_lib.add(resp_lib.GET, f"{EVENT_URL}/api/v1/events/{eid}",
                 json=event or EVENT_PUBLISHED, status=200)


def _mock_event_404(eid="event-1"):
    resp_lib.add(resp_lib.GET, f"{EVENT_URL}/api/v1/events/{eid}",
                 json={"error": {"code": "NOT_FOUND", "message": "x"}}, status=404)


def _post(client, user_id="user-1", event_id="event-1"):
    return client.post("/api/v1/registrations",
                       data=json.dumps({"user_id": user_id, "event_id": event_id}),
                       content_type="application/json")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-REG-03")
def test_health(client):
    rv = client.get("/health")
    assert rv.status_code == 200
    assert rv.get_json()["service"] == "registration-service"
    assert_matches_contract("registration", "get", "/health", _adapt(rv))


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-REG-01")
@resp_lib.activate
def test_create_registration_201(client):
    _mock_user_ok()
    _mock_event()
    rv = _post(client)
    assert rv.status_code == 201
    assert "Location" in rv.headers
    data = rv.get_json()
    assert data["status"] == "confirmed"
    assert data["amount"] == 149.00
    assert_matches_contract("registration", "post", "/api/v1/registrations", _adapt(rv))


@pytest.mark.req("REQ-REG-01")
def test_create_malformed_json_400(client):
    rv = client.post("/api/v1/registrations", data="xx", content_type="application/json")
    assert rv.status_code == 400


@pytest.mark.req("REQ-REG-01")
def test_create_missing_field_422(client):
    rv = client.post("/api/v1/registrations", data=json.dumps({"user_id": "u"}),
                     content_type="application/json")
    assert rv.status_code == 422


@pytest.mark.req("REQ-REG-B01")
@resp_lib.activate
def test_create_user_not_found_422(client):
    _mock_user_404()
    rv = _post(client)
    assert rv.status_code == 422
    assert rv.get_json()["error"]["code"] == "REFERENCE_NOT_FOUND"


@pytest.mark.req("REQ-REG-B02")
@resp_lib.activate
def test_create_event_not_found_422(client):
    _mock_user_ok()
    _mock_event_404()
    rv = _post(client)
    assert rv.status_code == 422
    assert rv.get_json()["error"]["code"] == "REFERENCE_NOT_FOUND"


@pytest.mark.req("REQ-REG-B03")
@resp_lib.activate
def test_create_event_not_published_422(client):
    _mock_user_ok()
    _mock_event({**EVENT_PUBLISHED, "status": "draft"})
    rv = _post(client)
    assert rv.status_code == 422
    assert rv.get_json()["error"]["code"] == "EVENT_NOT_OPEN"


@pytest.mark.req("REQ-REG-B04")
@resp_lib.activate
def test_create_duplicate_409(client):
    for _ in range(4):
        _mock_user_ok()
        _mock_event()
    _post(client)
    rv = _post(client)
    assert rv.status_code == 409
    assert rv.get_json()["error"]["code"] == "ALREADY_REGISTERED"


@pytest.mark.req("REQ-REG-B05")
@resp_lib.activate
def test_create_event_full_409(client):
    # capacity is 2
    for _ in range(6):
        _mock_user_ok("user-1")
        _mock_user_ok("user-2")
        _mock_user_ok("user-3")
        _mock_event()
    _post(client, user_id="user-1")
    _post(client, user_id="user-2")
    rv = _post(client, user_id="user-3")
    assert rv.status_code == 409
    assert rv.get_json()["error"]["code"] == "EVENT_FULL"


@pytest.mark.req("REQ-REG-B09")
@resp_lib.activate
def test_create_dependency_down_503(client):
    resp_lib.add(resp_lib.GET, f"{USER_URL}/api/v1/users/user-1",
                 body=requests.exceptions.ConnectionError("down"))
    rv = _post(client)
    assert rv.status_code == 503
    assert rv.get_json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Get / list
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-REG-02")
@resp_lib.activate
def test_get_registration_200(client):
    _mock_user_ok()
    _mock_event()
    created = _post(client).get_json()
    rv = client.get(f"/api/v1/registrations/{created['id']}")
    assert rv.status_code == 200
    assert_matches_contract("registration", "get", "/api/v1/registrations/{id}", _adapt(rv))


@pytest.mark.req("REQ-REG-02")
def test_get_registration_404(client):
    rv = client.get("/api/v1/registrations/00000000-0000-0000-0000-000000000000")
    assert rv.status_code == 404


@pytest.mark.req("REQ-REG-02")
@resp_lib.activate
def test_list_registrations_200(client):
    _mock_user_ok()
    _mock_event()
    _post(client)
    rv = client.get("/api/v1/registrations")
    assert rv.status_code == 200
    assert_matches_contract("registration", "get", "/api/v1/registrations", _adapt(rv))


# ---------------------------------------------------------------------------
# PATCH transitions
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-REG-B07")
@resp_lib.activate
def test_patch_confirmed_to_cancelled_200(client):
    _mock_user_ok()
    _mock_event()
    created = _post(client).get_json()
    rv = client.patch(f"/api/v1/registrations/{created['id']}",
                      data=json.dumps({"status": "cancelled"}), content_type="application/json")
    assert rv.status_code == 200
    assert rv.get_json()["status"] == "cancelled"
    assert_matches_contract("registration", "patch", "/api/v1/registrations/{id}", _adapt(rv))


@pytest.mark.req("REQ-REG-B07")
@resp_lib.activate
def test_patch_cancelled_to_confirmed_422(client):
    _mock_user_ok()
    _mock_event()
    created = _post(client).get_json()
    client.patch(f"/api/v1/registrations/{created['id']}",
                 data=json.dumps({"status": "cancelled"}), content_type="application/json")
    rv = client.patch(f"/api/v1/registrations/{created['id']}",
                      data=json.dumps({"status": "confirmed"}), content_type="application/json")
    assert rv.status_code == 422
    assert rv.get_json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


@pytest.mark.req("REQ-REG-B05")
@resp_lib.activate
def test_cancel_frees_seat(client):
    # capacity 2: register 2, cancel 1, register 3rd should succeed
    for _ in range(8):
        _mock_user_ok("user-1")
        _mock_user_ok("user-2")
        _mock_user_ok("user-3")
        _mock_event()
    r1 = _post(client, user_id="user-1").get_json()
    _post(client, user_id="user-2")
    # third fails (full)
    rv_full = _post(client, user_id="user-3")
    assert rv_full.status_code == 409
    # cancel first
    client.patch(f"/api/v1/registrations/{r1['id']}",
                 data=json.dumps({"status": "cancelled"}), content_type="application/json")
    # now third succeeds
    rv_ok = _post(client, user_id="user-3")
    assert rv_ok.status_code == 201


# ---------------------------------------------------------------------------
# DELETE + PUT 405
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-REG-02")
@resp_lib.activate
def test_delete_registration_204(client):
    _mock_user_ok()
    _mock_event()
    created = _post(client).get_json()
    rv = client.delete(f"/api/v1/registrations/{created['id']}")
    assert rv.status_code == 204
    assert_matches_contract(
        "registration", "delete", f"/api/v1/registrations/{created['id']}", _adapt(rv)
    )


@pytest.mark.req("REQ-REG-B10")
def test_put_not_allowed_405(client):
    rv = client.put("/api/v1/registrations/some-id",
                    data=json.dumps({}), content_type="application/json")
    assert rv.status_code == 405
    assert_matches_contract(
        "registration", "put", "/api/v1/registrations/some-id", _adapt(rv)
    )


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-REG-B08")
@resp_lib.activate
def test_stats_200(client):
    for _ in range(4):
        _mock_user_ok()
        _mock_event()
    _post(client)
    rv = client.get("/api/v1/registrations/stats?event_id=event-1")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["capacity"] == 2
    assert data["confirmed"] == 1
    assert data["available"] == 1
    assert_matches_contract("registration", "get", "/api/v1/registrations/stats", _adapt(rv))


@pytest.mark.req("REQ-REG-B08")
@resp_lib.activate
def test_stats_event_not_found_404(client):
    _mock_event_404()
    rv = client.get("/api/v1/registrations/stats?event_id=event-1")
    assert rv.status_code == 404


# ---------------------------------------------------------------------------
# All backends
# ---------------------------------------------------------------------------

class _FakeUsers:
    def get_user(self, uid):
        return {**USER, "id": uid}

class _FakeEvents:
    def get_event(self, eid):
        return {**EVENT_PUBLISHED, "id": eid}


@pytest.mark.req("REQ-REG-03")
def test_all_backends_create_and_get(repo):
    svc = RegistrationService(repo, _FakeUsers(), _FakeEvents())
    reg = svc.create_registration({"user_id": "u1", "event_id": "e1"})
    assert svc.get_registration(reg["id"])["amount"] == 149.00


@pytest.mark.req("REQ-REG-03")
def test_all_backends_delete(repo):
    svc = RegistrationService(repo, _FakeUsers(), _FakeEvents())
    reg = svc.create_registration({"user_id": "u1", "event_id": "e1"})
    svc.delete_registration(reg["id"])
    with pytest.raises(NotFoundError):
        svc.get_registration(reg["id"])


@pytest.mark.req("REQ-REG-03")
def test_json_backend_persistence(tmp_path):
    repo1 = JsonRegistrationRepository(str(tmp_path))
    svc1 = RegistrationService(repo1, _FakeUsers(), _FakeEvents())
    reg = svc1.create_registration({"user_id": "u1", "event_id": "e1"})
    repo2 = JsonRegistrationRepository(str(tmp_path))
    svc2 = RegistrationService(repo2, _FakeUsers(), _FakeEvents())
    assert svc2.get_registration(reg["id"])["amount"] == 149.00


@pytest.mark.req("REQ-REG-03")
def test_sqlite_backend_persistence(tmp_path):
    repo1 = SqliteRegistrationRepository(str(tmp_path))
    svc1 = RegistrationService(repo1, _FakeUsers(), _FakeEvents())
    reg = svc1.create_registration({"user_id": "u1", "event_id": "e1"})
    repo2 = SqliteRegistrationRepository(str(tmp_path))
    svc2 = RegistrationService(repo2, _FakeUsers(), _FakeEvents())
    assert svc2.get_registration(reg["id"])["amount"] == 149.00


@pytest.mark.req("REQ-REG-03")
@resp_lib.activate
def test_json_backend_contract(client_json):
    _mock_user_ok()
    _mock_event()
    rv = _post(client_json)
    assert rv.status_code == 201
    assert_matches_contract("registration", "post", "/api/v1/registrations", _adapt(rv))


@pytest.mark.req("REQ-REG-03")
@resp_lib.activate
def test_sqlite_backend_contract(client_sqlite):
    _mock_user_ok()
    _mock_event()
    rv = _post(client_sqlite)
    assert rv.status_code == 201
    assert_matches_contract("registration", "post", "/api/v1/registrations", _adapt(rv))


@pytest.mark.req("REQ-REG-01")
def test_create_registration_unknown_field_returns_422(client):
    rv = client.post(
        "/api/v1/registrations",
        data=json.dumps({"user_id": "user-1", "event_id": "event-1", "amount": 1}),
        content_type="application/json",
    )
    assert rv.status_code == 422
    assert rv.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.req("REQ-REG-B07")
@resp_lib.activate
def test_patch_same_status_is_invalid_transition(client):
    _mock_user_ok()
    _mock_event()
    created = _post(client).get_json()
    rv = client.patch(
        f"/api/v1/registrations/{created['id']}",
        data=json.dumps({"status": "confirmed"}),
        content_type="application/json",
    )
    assert rv.status_code == 422
    assert rv.get_json()["error"]["code"] == "INVALID_STATUS_TRANSITION"
