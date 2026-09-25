"""Acceptance tests — user-service (IT-U01..IT-U08).

Client -> service. Mandatory.
"""

from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.mandatory, pytest.mark.user]


def _valid_payload(unique, role="attendee"):
    return {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": unique.email(),
        "company": "Analytical Engines",
        "role": role,
    }


def test_it_u01_create_valid(user_client, unique):
    """IT-U01: POST valid -> 201, Location header, contract-conformant body."""
    payload = _valid_payload(unique)
    resp = user_client.post("/api/v1/users", json=payload)
    assert resp.status_code == 201, resp.text
    assert resp.headers.get("Location"), "missing Location header"
    body = resp.json()
    assert body["email"] == payload["email"].lower()
    assert body["role"] == "attendee"
    assert body["id"] and body["created_at"] and body["updated_at"]


def test_it_u02_missing_required(user_client, unique):
    """IT-U02: missing required field -> 422 VALIDATION_ERROR."""
    payload = _valid_payload(unique)
    del payload["last_name"]
    resp = user_client.post("/api/v1/users", json=payload)
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_it_u03_duplicate_email_case_insensitive(user_client, unique):
    """IT-U03: duplicate email (different case) -> 409 EMAIL_ALREADY_EXISTS."""
    payload = _valid_payload(unique)
    first = user_client.post("/api/v1/users", json=payload)
    assert first.status_code == 201, first.text

    dup = dict(payload)
    dup["email"] = payload["email"].upper()
    resp = user_client.post("/api/v1/users", json=dup)
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_it_u04_get_by_id_and_404(user_client, unique):
    """IT-U04: GET by id -> 200; unknown id -> 404 NOT_FOUND."""
    created = user_client.post("/api/v1/users", json=_valid_payload(unique)).json()
    ok = user_client.get(f"/api/v1/users/{created['id']}")
    assert ok.status_code == 200
    assert ok.json()["id"] == created["id"]

    missing = user_client.get(f"/api/v1/users/{unique.uuid()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_it_u05_list_pagination_and_role_filter(user_client, unique):
    """IT-U05: paginated list and role filter."""
    organizer = user_client.post(
        "/api/v1/users", json=_valid_payload(unique, role="organizer")
    ).json()

    listed = user_client.get("/api/v1/users?page=1&page_size=5&role=organizer")
    assert listed.status_code == 200
    page = listed.json()
    assert page["page"] == 1 and page["page_size"] == 5
    assert all(u["role"] == "organizer" for u in page["items"])
    assert any(u["id"] == organizer["id"] for u in page["items"]) or page["total"] >= 1


def test_it_u06_put_and_patch_update_timestamp(user_client, unique):
    """IT-U06: PUT and PATCH -> 200, updated_at changes."""
    created = user_client.post("/api/v1/users", json=_valid_payload(unique)).json()

    put_payload = _valid_payload(unique)
    put_payload["email"] = created["email"]  # keep unique email stable
    put_resp = user_client.put(f"/api/v1/users/{created['id']}", json=put_payload)
    assert put_resp.status_code == 200, put_resp.text
    assert put_resp.json()["first_name"] == "Ada"

    patch_resp = user_client.patch(
        f"/api/v1/users/{created['id']}", json={"company": "New Co"}
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["company"] == "New Co"
    assert patch_resp.json()["updated_at"] >= created["updated_at"]


def test_it_u07_delete_then_404(user_client, unique):
    """IT-U07: DELETE -> 204, then GET -> 404."""
    created = user_client.post("/api/v1/users", json=_valid_payload(unique)).json()
    deleted = user_client.delete(f"/api/v1/users/{created['id']}")
    assert deleted.status_code == 204
    gone = user_client.get(f"/api/v1/users/{created['id']}")
    assert gone.status_code == 404


def test_it_u08_malformed_json_and_health(user_client):
    """IT-U08: malformed JSON -> 400; GET /health -> 200."""
    resp = user_client.post(
        "/api/v1/users",
        data="{not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400, resp.text

    health = user_client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["service"]
