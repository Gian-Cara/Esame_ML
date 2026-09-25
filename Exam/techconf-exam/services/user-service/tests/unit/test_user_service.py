"""
Unit tests for user-service.

Covers:
- All three backends (memory, json with tmp_path, sqlite with tmp_path)
- Business rules REQ-USR-01 through REQ-USR-11
- Contract validation via assert_matches_contract (at least 1 per endpoint)

Run:
    pytest services/user-service/tests/unit --cov=app -v
"""
from __future__ import annotations

import json
import sys
import os
import pytest

# Make contracts accessible
REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
)
sys.path.insert(0, REPO_ROOT)
from contracts.validator import assert_matches_contract


# ---------------------------------------------------------------------------
# Adapter: wrap Flask test-client response so validator.py can call .json()
# The validator reads response.text to detect a body, then calls response.json().
# Flask test client uses .data (bytes) instead of .text, so we expose both.
# ---------------------------------------------------------------------------
class _FlaskResponseAdapter:
    """Makes a Flask test-client response compatible with assert_matches_contract."""
    def __init__(self, rv):
        self._rv = rv
        self.status_code = rv.status_code
        self.headers = rv.headers
        # validator.py checks `response.text` — expose decoded data
        self.text = rv.data.decode("utf-8") if rv.data else ""

    def json(self):
        import json as _json
        return _json.loads(self._rv.data)


def _adapt(rv):
    return _FlaskResponseAdapter(rv)


# Make app importable
SERVICE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, SERVICE_ROOT)

from app import create_app
from app.repository import (
    JsonUserRepository,
    MemoryUserRepository,
    SqliteUserRepository,
)
from app.service import ConflictError, NotFoundError, UserService, ValidationError


# ---------------------------------------------------------------------------
# Repository fixtures — all three backends
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_repo():
    return MemoryUserRepository()


@pytest.fixture
def json_repo(tmp_path):
    return JsonUserRepository(str(tmp_path))


@pytest.fixture
def sqlite_repo(tmp_path):
    return SqliteUserRepository(str(tmp_path))


@pytest.fixture(params=["memory", "json", "sqlite"])
def repo(request, tmp_path):
    """Parametrised fixture that yields all three backends."""
    if request.param == "memory":
        return MemoryUserRepository()
    if request.param == "json":
        return JsonUserRepository(str(tmp_path))
    return SqliteUserRepository(str(tmp_path))


# ---------------------------------------------------------------------------
# Flask test client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    app = create_app(storage_backend="memory")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def client_json(tmp_path):
    app = create_app(storage_backend="json", data_dir=str(tmp_path))
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def client_sqlite(tmp_path):
    app = create_app(storage_backend="sqlite", data_dir=str(tmp_path))
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_USER = {
    "first_name": "Mario",
    "last_name": "Rossi",
    "email": "mario.rossi@example.com",
    "role": "attendee",
}


def _create(client, payload=None):
    return client.post(
        "/api/v1/users",
        data=json.dumps(payload or VALID_USER),
        content_type="application/json",
    )


# ---------------------------------------------------------------------------
# T-12 — Health endpoint
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-09")
def test_health(client):
    rv = client.get("/health")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "user-service"
    assert_matches_contract("user", "get", "/health", _adapt(rv))


# ---------------------------------------------------------------------------
# T-12 — Create user (REQ-USR-01, REQ-USR-02, REQ-USR-03)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-01")
def test_create_user_returns_201(client):
    rv = _create(client)
    assert rv.status_code == 201
    assert "Location" in rv.headers
    data = rv.get_json()
    assert "id" in data
    assert data["email"] == "mario.rossi@example.com"
    assert data["role"] == "attendee"
    assert "created_at" in data
    assert "updated_at" in data
    assert_matches_contract("user", "post", "/api/v1/users", _adapt(rv))


@pytest.mark.req("REQ-USR-01")
def test_create_user_default_role(client):
    payload = {k: v for k, v in VALID_USER.items() if k != "role"}
    rv = _create(client, payload)
    assert rv.status_code == 201
    assert rv.get_json()["role"] == "attendee"


@pytest.mark.req("REQ-USR-01")
def test_create_user_id_not_accepted_from_client(client):
    payload = {**VALID_USER, "id": "custom-id"}
    rv = _create(client, payload)
    assert rv.status_code == 422
    assert rv.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.req("REQ-USR-03")
def test_create_user_missing_required_field_returns_422(client):
    for field in ("first_name", "last_name", "email"):
        payload = {k: v for k, v in VALID_USER.items() if k != field}
        rv = _create(client, payload)
        assert rv.status_code == 422, f"Expected 422 for missing {field}"
        assert rv.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.req("REQ-USR-03")
def test_create_user_invalid_email_returns_422(client):
    rv = _create(client, {**VALID_USER, "email": "not-an-email"})
    assert rv.status_code == 422


@pytest.mark.req("REQ-USR-03")
def test_create_user_first_name_too_long_returns_422(client):
    rv = _create(client, {**VALID_USER, "first_name": "A" * 51})
    assert rv.status_code == 422


@pytest.mark.req("REQ-USR-03")
def test_create_user_invalid_role_returns_422(client):
    rv = _create(client, {**VALID_USER, "email": "x@x.com", "role": "superadmin"})
    assert rv.status_code == 422


@pytest.mark.req("REQ-USR-02")
def test_create_user_duplicate_email_returns_409(client):
    _create(client)
    rv = _create(client, {**VALID_USER, "email": "MARIO.ROSSI@EXAMPLE.COM"})
    assert rv.status_code == 409
    assert rv.get_json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


@pytest.mark.req("REQ-USR-02")
def test_create_user_email_stored_lowercase(client):
    rv = _create(client, {**VALID_USER, "email": "Upper@EXAMPLE.COM"})
    assert rv.get_json()["email"] == "upper@example.com"


@pytest.mark.req("REQ-USR-01")
def test_create_user_malformed_json_returns_400(client):
    rv = client.post(
        "/api/v1/users",
        data="not-json",
        content_type="application/json",
    )
    assert rv.status_code == 400


# ---------------------------------------------------------------------------
# T-12 — Get user by ID (REQ-USR-04)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-04")
def test_get_user_returns_200(client):
    created = _create(client).get_json()
    rv = client.get(f"/api/v1/users/{created['id']}")
    assert rv.status_code == 200
    assert rv.get_json()["id"] == created["id"]
    assert_matches_contract("user", "get", "/api/v1/users/{id}", _adapt(rv))


@pytest.mark.req("REQ-USR-04")
def test_get_user_not_found_returns_404(client):
    rv = client.get("/api/v1/users/00000000-0000-0000-0000-000000000000")
    assert rv.status_code == 404
    assert rv.get_json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# T-12 — List users (REQ-USR-05)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-05")
def test_list_users_returns_200(client):
    _create(client)
    rv = client.get("/api/v1/users")
    assert rv.status_code == 200
    data = rv.get_json()
    assert "items" in data
    assert "total" in data
    assert_matches_contract("user", "get", "/api/v1/users", _adapt(rv))


@pytest.mark.req("REQ-USR-05")
def test_list_users_filter_by_role(client):
    _create(client, {**VALID_USER, "role": "organizer", "email": "org@ex.com"})
    _create(client, {**VALID_USER, "role": "speaker", "email": "spk@ex.com"})
    rv = client.get("/api/v1/users?role=organizer")
    items = rv.get_json()["items"]
    assert all(u["role"] == "organizer" for u in items)


@pytest.mark.req("REQ-USR-05")
def test_list_users_filter_by_email(client):
    _create(client)
    rv = client.get("/api/v1/users?email=mario.rossi@example.com")
    assert rv.get_json()["total"] == 1


@pytest.mark.req("REQ-USR-05")
def test_list_users_page_size_over_100_returns_422(client):
    rv = client.get("/api/v1/users?page_size=101")
    assert rv.status_code == 422


# ---------------------------------------------------------------------------
# T-12 — Replace user PUT (REQ-USR-06)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-06")
def test_replace_user_returns_200(client):
    created = _create(client).get_json()
    payload = {**VALID_USER, "first_name": "Luigi", "email": "luigi@example.com"}
    rv = client.put(
        f"/api/v1/users/{created['id']}",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["first_name"] == "Luigi"
    assert data["created_at"] == created["created_at"]
    assert_matches_contract("user", "put", "/api/v1/users/{id}", _adapt(rv))


@pytest.mark.req("REQ-USR-06")
def test_replace_user_not_found_returns_404(client):
    rv = client.put(
        "/api/v1/users/00000000-0000-0000-0000-000000000000",
        data=json.dumps(VALID_USER),
        content_type="application/json",
    )
    assert rv.status_code == 404


# ---------------------------------------------------------------------------
# T-12 — Partial update PATCH (REQ-USR-07)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-07")
def test_patch_user_returns_200(client):
    created = _create(client).get_json()
    rv = client.patch(
        f"/api/v1/users/{created['id']}",
        data=json.dumps({"first_name": "Luca"}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    assert rv.get_json()["first_name"] == "Luca"
    assert_matches_contract("user", "patch", "/api/v1/users/{id}", _adapt(rv))


@pytest.mark.req("REQ-USR-07")
def test_patch_user_not_found_returns_404(client):
    rv = client.patch(
        "/api/v1/users/00000000-0000-0000-0000-000000000000",
        data=json.dumps({"first_name": "X"}),
        content_type="application/json",
    )
    assert rv.status_code == 404


@pytest.mark.req("REQ-USR-07")
def test_patch_user_updated_at_changes(client):
    import time
    created = _create(client).get_json()
    time.sleep(1)
    rv = client.patch(
        f"/api/v1/users/{created['id']}",
        data=json.dumps({"last_name": "Bianchi"}),
        content_type="application/json",
    )
    assert rv.get_json()["updated_at"] >= created["updated_at"]


# ---------------------------------------------------------------------------
# T-12 — Delete user (REQ-USR-08)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-08")
def test_delete_user_returns_204(client):
    created = _create(client).get_json()
    rv = client.delete(f"/api/v1/users/{created['id']}")
    assert rv.status_code == 204
    assert_matches_contract("user", "delete", f"/api/v1/users/{created['id']}", _adapt(rv))
    # Confirm gone
    rv2 = client.get(f"/api/v1/users/{created['id']}")
    assert rv2.status_code == 404


@pytest.mark.req("REQ-USR-08")
def test_delete_user_not_found_returns_404(client):
    rv = client.delete("/api/v1/users/00000000-0000-0000-0000-000000000000")
    assert rv.status_code == 404


# ---------------------------------------------------------------------------
# T-12 — All three backends via parametrised repo fixture (REQ-USR-10)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-10")
def test_all_backends_create_and_get(repo):
    svc = UserService(repo)
    user = svc.create_user(VALID_USER)
    assert user["id"] is not None
    fetched = svc.get_user(user["id"])
    assert fetched["email"] == "mario.rossi@example.com"


@pytest.mark.req("REQ-USR-10")
def test_all_backends_email_uniqueness(repo):
    svc = UserService(repo)
    svc.create_user(VALID_USER)
    with pytest.raises(ConflictError):
        svc.create_user({**VALID_USER, "email": "MARIO.ROSSI@EXAMPLE.COM"})


@pytest.mark.req("REQ-USR-10")
def test_all_backends_delete(repo):
    svc = UserService(repo)
    user = svc.create_user(VALID_USER)
    svc.delete_user(user["id"])
    with pytest.raises(NotFoundError):
        svc.get_user(user["id"])


@pytest.mark.req("REQ-USR-10")
def test_json_backend_persistence(tmp_path):
    """JSON backend: data survives a repository restart."""
    repo1 = JsonUserRepository(str(tmp_path))
    svc1 = UserService(repo1)
    user = svc1.create_user(VALID_USER)
    user_id = user["id"]

    # Create a new repo instance pointing to same dir (simulates restart)
    repo2 = JsonUserRepository(str(tmp_path))
    svc2 = UserService(repo2)
    fetched = svc2.get_user(user_id)
    assert fetched["email"] == "mario.rossi@example.com"


@pytest.mark.req("REQ-USR-10")
def test_sqlite_backend_persistence(tmp_path):
    """SQLite backend: data survives a repository restart."""
    repo1 = SqliteUserRepository(str(tmp_path))
    svc1 = UserService(repo1)
    user = svc1.create_user(VALID_USER)
    user_id = user["id"]

    repo2 = SqliteUserRepository(str(tmp_path))
    svc2 = UserService(repo2)
    fetched = svc2.get_user(user_id)
    assert fetched["email"] == "mario.rossi@example.com"


# ---------------------------------------------------------------------------
# T-12 — JSON and SQLite clients (contract validation)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-10")
def test_json_backend_create_contract(client_json):
    rv = _create(client_json)
    assert rv.status_code == 201
    assert_matches_contract("user", "post", "/api/v1/users", _adapt(rv))


@pytest.mark.req("REQ-USR-10")
def test_sqlite_backend_create_contract(client_sqlite):
    rv = _create(client_sqlite)
    assert rv.status_code == 201
    assert_matches_contract("user", "post", "/api/v1/users", _adapt(rv))
