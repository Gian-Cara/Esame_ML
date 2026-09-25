"""Acceptance tests — event-service (IT-E01..IT-E08).

Mix of service->service, client->service and resilience.
"""

from __future__ import annotations

import pytest

from conftest import make_event, make_user

pytestmark = [pytest.mark.mandatory, pytest.mark.event]


def _event_payload(organizer_id, unique, **overrides):
    payload = {
        "title": unique.title(),
        "organizer_id": organizer_id,
        "venue": "Auditorium Roma",
        "city": "Roma",
        "start_date": "2026-10-15",
        "end_date": "2026-10-16",
        "capacity": 100,
        "price": 149.00,
    }
    payload.update(overrides)
    return payload


def test_it_e01_create_with_valid_organizer(user_client, event_client, unique):
    """IT-E01: valid organizer -> 201, status=draft."""
    organizer = make_user(user_client, unique, role="organizer")
    resp = event_client.post(
        "/api/v1/events", json=_event_payload(organizer["id"], unique)
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "draft"
    assert resp.headers.get("Location")


def test_it_e02_organizer_not_found(event_client, unique):
    """IT-E02: unknown organizer_id -> 422 REFERENCE_NOT_FOUND."""
    resp = event_client.post(
        "/api/v1/events", json=_event_payload(unique.uuid(), unique)
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "REFERENCE_NOT_FOUND"


def test_it_e03_organizer_wrong_role(user_client, event_client, unique):
    """IT-E03: organizer with role=attendee -> 422 INVALID_ORGANIZER."""
    attendee = make_user(user_client, unique, role="attendee")
    resp = event_client.post(
        "/api/v1/events", json=_event_payload(attendee["id"], unique)
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "INVALID_ORGANIZER"


def test_it_e04_end_before_start(user_client, event_client, unique):
    """IT-E04: end_date < start_date -> 422."""
    organizer = make_user(user_client, unique, role="organizer")
    payload = _event_payload(
        organizer["id"], unique, start_date="2026-10-16", end_date="2026-10-15"
    )
    resp = event_client.post("/api/v1/events", json=payload)
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_it_e05_status_transitions(user_client, event_client, unique):
    """IT-E05: draft->published -> 200; published->draft -> 422."""
    organizer = make_user(user_client, unique, role="organizer")
    event = make_event(event_client, organizer["id"], unique)

    published = event_client.patch(
        f"/api/v1/events/{event['id']}", json={"status": "published"}
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"

    invalid = event_client.patch(
        f"/api/v1/events/{event['id']}", json={"status": "draft"}
    )
    assert invalid.status_code == 422, invalid.text
    assert invalid.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_it_e06_filters_and_pagination(user_client, event_client, unique):
    """IT-E06: filter by status, city and pagination."""
    organizer = make_user(user_client, unique, role="organizer")
    event = make_event(event_client, organizer["id"], unique)
    event_client.patch(f"/api/v1/events/{event['id']}", json={"status": "published"})

    listed = event_client.get(
        "/api/v1/events?page=1&page_size=10&status=published&city=Roma"
    )
    assert listed.status_code == 200
    page = listed.json()
    assert page["page"] == 1 and page["page_size"] == 10
    assert all(e["status"] == "published" and e["city"] == "Roma" for e in page["items"])


def test_it_e07_crud_and_404(user_client, event_client, unique):
    """IT-E07: GET/PUT/PATCH/DELETE and 404 for unknown id."""
    organizer = make_user(user_client, unique, role="organizer")
    event = make_event(event_client, organizer["id"], unique)

    got = event_client.get(f"/api/v1/events/{event['id']}")
    assert got.status_code == 200

    put = event_client.put(
        f"/api/v1/events/{event['id']}",
        json=_event_payload(organizer["id"], unique, capacity=200),
    )
    assert put.status_code == 200, put.text
    assert put.json()["capacity"] == 200

    patch = event_client.patch(
        f"/api/v1/events/{event['id']}", json={"venue": "Palazzo Congressi"}
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["venue"] == "Palazzo Congressi"

    deleted = event_client.delete(f"/api/v1/events/{event['id']}")
    assert deleted.status_code == 204

    assert event_client.get(f"/api/v1/events/{unique.uuid()}").status_code == 404


@pytest.mark.resilience
def test_it_e08_user_service_unreachable(dead_dependency_client, unique):
    """IT-E08: user-service unreachable -> 503 DEPENDENCY_UNAVAILABLE."""
    client = dead_dependency_client("event")
    resp = client.post("/api/v1/events", json=_event_payload(unique.uuid(), unique))
    assert resp.status_code == 503, resp.text
    assert resp.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
