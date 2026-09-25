"""
Unit tests for event-service.
- All three backends (memory, json, sqlite)
- user-service mocked with responses library
- Contract validation via assert_matches_contract
- Coverage target: >= 80%

Run:
    pytest services/event-service/tests/unit --cov=app -v
"""
from __future__ import annotations

import json
import sys
import os
import pytest
import requests
import responses as resp_lib

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
)
sys.path.insert(0, REPO_ROOT)
from contracts.validator import assert_matches_contract

SERVICE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, SERVICE_ROOT)

from app import create_app
from app.clients import UserServiceClient, DependencyError
from app.repository import MemoryEventRepository, JsonEventRepository, SqliteEventRepository
from app.service import EventService, ValidationError, NotFoundError, InvalidStatusTransitionError

# ---------------------------------------------------------------------------
# Flask response adapter (same pattern as user-service tests)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

USER_SERVICE_URL = "http://mock-user-service"
ORGANIZER = {"id": "org-uuid", "role": "organizer", "first_name": "Ada", "last_name": "Lovelace",
              "email": "ada@example.com", "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}

VALID_EVENT = {
    "title": "TechConf 2026",
    "organizer_id": "org-uuid",
    "venue": "Auditorium Roma",
    "city": "Roma",
    "start_date": "2026-10-01",
    "end_date": "2026-10-02",
    "capacity": 100,
    "price": 149.00,
}


@pytest.fixture
def client(tmp_path):
    app = create_app(storage_backend="memory", user_service_url=USER_SERVICE_URL)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def client_json(tmp_path):
    app = create_app(storage_backend="json", data_dir=str(tmp_path), user_service_url=USER_SERVICE_URL)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def client_sqlite(tmp_path):
    app = create_app(storage_backend="sqlite", data_dir=str(tmp_path), user_service_url=USER_SERVICE_URL)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(params=["memory", "json", "sqlite"])
def repo(request, tmp_path):
    if request.param == "memory":
        return MemoryEventRepository()
    if request.param == "json":
        return JsonEventRepository(str(tmp_path))
    return SqliteEventRepository(str(tmp_path))


def _mock_organizer_ok():
    resp_lib.add(resp_lib.GET, f"{USER_SERVICE_URL}/api/v1/users/org-uuid",
                 json=ORGANIZER, status=200)


def _mock_organizer_404():
    resp_lib.add(resp_lib.GET, f"{USER_SERVICE_URL}/api/v1/users/org-uuid",
                 json={"error": {"code": "NOT_FOUND", "message": "not found"}}, status=404)


def _post_event(client, payload=None):
    return client.post(
        "/api/v1/events",
        data=json.dumps(payload or VALID_EVENT),
        content_type="application/json",
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-EVT-05")
def test_health(client):
    rv = client.get("/health")
    assert rv.status_code == 200
    assert rv.get_json()["service"] == "event-service"
    assert_matches_contract("event", "get", "/health", _adapt(rv))


# ---------------------------------------------------------------------------
# Create event
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-EVT-01")
@resp_lib.activate
def test_create_event_returns_201(client):
    _mock_organizer_ok()
    rv = _post_event(client)
    assert rv.status_code == 201
    assert "Location" in rv.headers
    data = rv.get_json()
    assert data["status"] == "draft"
    assert data["title"] == "TechConf 2026"
    assert_matches_contract("event", "post", "/api/v1/events", _adapt(rv))


@pytest.mark.req("REQ-EVT-01")
def test_create_event_malformed_json_returns_400(client):
    rv = client.post("/api/v1/events", data="not-json", content_type="application/json")
    assert rv.status_code == 400


@pytest.mark.req("REQ-EVT-03")
@resp_lib.activate
def test_create_event_missing_required_returns_422(client):
    _mock_organizer_ok()
    for field in ("title", "organizer_id", "venue", "city", "start_date", "end_date", "capacity", "price"):
        payload = {k: v for k, v in VALID_EVENT.items() if k != field}
        rv = _post_event(client, payload)
        assert rv.status_code == 422, f"Expected 422 for missing {field}"


@pytest.mark.req("REQ-EVT-B03")
@resp_lib.activate
def test_create_event_end_before_start_returns_422(client):
    _mock_organizer_ok()
    rv = _post_event(client, {**VALID_EVENT, "organizer_id": "org-uuid",
                               "start_date": "2026-10-05", "end_date": "2026-10-01"})
    assert rv.status_code == 422


@pytest.mark.req("REQ-EVT-B01")
@resp_lib.activate
def test_create_event_organizer_not_found_returns_422(client):
    _mock_organizer_404()
    rv = _post_event(client)
    assert rv.status_code == 422
    assert rv.get_json()["error"]["code"] == "REFERENCE_NOT_FOUND"


@pytest.mark.req("REQ-EVT-B02")
@resp_lib.activate
def test_create_event_organizer_wrong_role_returns_422(client):
    attendee = {**ORGANIZER, "role": "attendee"}
    resp_lib.add(resp_lib.GET, f"{USER_SERVICE_URL}/api/v1/users/org-uuid",
                 json=attendee, status=200)
    rv = _post_event(client)
    assert rv.status_code == 422
    assert rv.get_json()["error"]["code"] == "INVALID_ORGANIZER"


@pytest.mark.req("REQ-EVT-B05")
@resp_lib.activate
def test_create_event_user_service_down_returns_503(client):
    resp_lib.add(resp_lib.GET, f"{USER_SERVICE_URL}/api/v1/users/org-uuid",
                 body=requests.exceptions.ConnectionError("down"))
    rv = _post_event(client)
    assert rv.status_code == 503
    assert rv.get_json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Get event
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-EVT-04")
@resp_lib.activate
def test_get_event_returns_200(client):
    _mock_organizer_ok()
    created = _post_event(client).get_json()
    rv = client.get(f"/api/v1/events/{created['id']}")
    assert rv.status_code == 200
    assert_matches_contract("event", "get", "/api/v1/events/{id}", _adapt(rv))


@pytest.mark.req("REQ-EVT-04")
def test_get_event_not_found_returns_404(client):
    rv = client.get("/api/v1/events/00000000-0000-0000-0000-000000000000")
    assert rv.status_code == 404
    assert rv.get_json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# List events
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-EVT-B06")
@resp_lib.activate
def test_list_events_returns_200(client):
    _mock_organizer_ok()
    _post_event(client)
    rv = client.get("/api/v1/events")
    assert rv.status_code == 200
    data = rv.get_json()
    assert "items" in data
    assert_matches_contract("event", "get", "/api/v1/events", _adapt(rv))


@pytest.mark.req("REQ-EVT-B06")
@resp_lib.activate
def test_list_events_filter_by_status(client):
    _mock_organizer_ok()
    _mock_organizer_ok()
    _post_event(client)
    _post_event(client, {**VALID_EVENT, "title": "Other Event"})
    rv = client.get("/api/v1/events?status=draft")
    items = rv.get_json()["items"]
    assert all(e["status"] == "draft" for e in items)


@pytest.mark.req("REQ-EVT-B06")
@resp_lib.activate
def test_list_events_filter_by_city(client):
    _mock_organizer_ok()
    _post_event(client)
    rv = client.get("/api/v1/events?city=Roma")
    items = rv.get_json()["items"]
    assert all(e["city"].lower() == "roma" for e in items)


# ---------------------------------------------------------------------------
# Status transitions (PATCH)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-EVT-B04")
@resp_lib.activate
def test_patch_draft_to_published(client):
    _mock_organizer_ok()
    created = _post_event(client).get_json()
    rv = client.patch(
        f"/api/v1/events/{created['id']}",
        data=json.dumps({"status": "published"}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    assert rv.get_json()["status"] == "published"
    assert_matches_contract("event", "patch", "/api/v1/events/{id}", _adapt(rv))


@pytest.mark.req("REQ-EVT-B04")
@resp_lib.activate
def test_patch_published_to_draft_returns_422(client):
    _mock_organizer_ok()
    created = _post_event(client).get_json()
    client.patch(f"/api/v1/events/{created['id']}",
                 data=json.dumps({"status": "published"}), content_type="application/json")
    rv = client.patch(f"/api/v1/events/{created['id']}",
                      data=json.dumps({"status": "draft"}), content_type="application/json")
    assert rv.status_code == 422
    assert rv.get_json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


# ---------------------------------------------------------------------------
# PUT (replace)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-EVT-04")
@resp_lib.activate
def test_replace_event_returns_200(client):
    _mock_organizer_ok()
    _mock_organizer_ok()
    created = _post_event(client).get_json()
    rv = client.put(
        f"/api/v1/events/{created['id']}",
        data=json.dumps({**VALID_EVENT, "title": "Updated Title"}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    assert rv.get_json()["title"] == "Updated Title"
    assert_matches_contract("event", "put", "/api/v1/events/{id}", _adapt(rv))


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-EVT-04")
@resp_lib.activate
def test_delete_event_returns_204(client):
    _mock_organizer_ok()
    created = _post_event(client).get_json()
    rv = client.delete(f"/api/v1/events/{created['id']}")
    assert rv.status_code == 204
    assert_matches_contract("event", "delete", f"/api/v1/events/{created['id']}", _adapt(rv))
    rv2 = client.get(f"/api/v1/events/{created['id']}")
    assert rv2.status_code == 404


# ---------------------------------------------------------------------------
# All three backends
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-EVT-06")
def test_all_backends_create_and_get(repo):
    class FakeClient:
        def get_user(self, uid):
            return {**ORGANIZER, "id": uid}
    svc = EventService(repo, FakeClient())
    event = svc.create_event(VALID_EVENT)
    fetched = svc.get_event(event["id"])
    assert fetched["title"] == "TechConf 2026"


@pytest.mark.req("REQ-EVT-06")
def test_all_backends_delete(repo):
    class FakeClient:
        def get_user(self, uid):
            return {**ORGANIZER, "id": uid}
    svc = EventService(repo, FakeClient())
    event = svc.create_event(VALID_EVENT)
    svc.delete_event(event["id"])
    with pytest.raises(NotFoundError):
        svc.get_event(event["id"])


@pytest.mark.req("REQ-EVT-06")
def test_json_backend_persistence(tmp_path):
    class FakeClient:
        def get_user(self, uid):
            return {**ORGANIZER, "id": uid}
    repo1 = JsonEventRepository(str(tmp_path))
    svc1 = EventService(repo1, FakeClient())
    event = svc1.create_event(VALID_EVENT)
    eid = event["id"]
    repo2 = JsonEventRepository(str(tmp_path))
    svc2 = EventService(repo2, FakeClient())
    assert svc2.get_event(eid)["title"] == "TechConf 2026"


@pytest.mark.req("REQ-EVT-06")
def test_sqlite_backend_persistence(tmp_path):
    class FakeClient:
        def get_user(self, uid):
            return {**ORGANIZER, "id": uid}
    repo1 = SqliteEventRepository(str(tmp_path))
    svc1 = EventService(repo1, FakeClient())
    event = svc1.create_event(VALID_EVENT)
    eid = event["id"]
    repo2 = SqliteEventRepository(str(tmp_path))
    svc2 = EventService(repo2, FakeClient())
    assert svc2.get_event(eid)["title"] == "TechConf 2026"


@pytest.mark.req("REQ-EVT-06")
@resp_lib.activate
def test_json_backend_contract(client_json):
    _mock_organizer_ok()
    rv = _post_event(client_json)
    assert rv.status_code == 201
    assert_matches_contract("event", "post", "/api/v1/events", _adapt(rv))


@pytest.mark.req("REQ-EVT-06")
@resp_lib.activate
def test_sqlite_backend_contract(client_sqlite):
    _mock_organizer_ok()
    rv = _post_event(client_sqlite)
    assert rv.status_code == 201
    assert_matches_contract("event", "post", "/api/v1/events", _adapt(rv))


@pytest.mark.req("REQ-EVT-B03")
def test_create_event_impossible_date_returns_422(client):
    rv = _post_event(client, {**VALID_EVENT, "start_date": "2026-99-99"})
    assert rv.status_code == 422
    assert rv.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.req("REQ-EVT-B03")
@resp_lib.activate
def test_patch_single_date_cannot_invalidate_range(client):
    _mock_organizer_ok()
    created = _post_event(client).get_json()
    rv = client.patch(
        f"/api/v1/events/{created['id']}",
        data=json.dumps({"start_date": "2026-10-03"}),
        content_type="application/json",
    )
    assert rv.status_code == 422
    assert rv.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.req("REQ-EVT-03")
def test_create_event_unknown_field_returns_422(client):
    rv = _post_event(client, {**VALID_EVENT, "unexpected": True})
    assert rv.status_code == 422
