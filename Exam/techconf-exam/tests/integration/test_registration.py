"""Acceptance tests — registration-service (IT-R01..IT-R10).

Service->service, client->service and resilience.
"""

from __future__ import annotations

import pytest

from conftest import make_event, make_user, publish_event

pytestmark = [pytest.mark.mandatory, pytest.mark.registration]


def _register(registration_client, user_id, event_id, validate=True):
    return registration_client.post(
        "/api/v1/registrations",
        json={"user_id": user_id, "event_id": event_id},
        validate=validate,
    )


def test_it_r01_register_published_event(
    user_client, event_client, registration_client, unique
):
    """IT-R01: register to published event -> 201, confirmed, amount=event.price."""
    organizer = make_user(user_client, unique, role="organizer")
    attendee = make_user(user_client, unique)
    event = make_event(
        event_client, organizer["id"], unique, price=149.00, status="published"
    )

    resp = _register(registration_client, attendee["id"], event["id"])
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "confirmed"
    assert float(body["amount"]) == 149.00
    assert resp.headers.get("Location")


def test_it_r02_user_not_found(
    user_client, event_client, registration_client, unique
):
    """IT-R02: unknown user -> 422 REFERENCE_NOT_FOUND."""
    organizer = make_user(user_client, unique, role="organizer")
    event = make_event(event_client, organizer["id"], unique, status="published")
    resp = _register(registration_client, unique.uuid(), event["id"])
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "REFERENCE_NOT_FOUND"


def test_it_r03_event_not_found(user_client, registration_client, unique):
    """IT-R03: unknown event -> 422 REFERENCE_NOT_FOUND."""
    attendee = make_user(user_client, unique)
    resp = _register(registration_client, attendee["id"], unique.uuid())
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "REFERENCE_NOT_FOUND"


def test_it_r04_event_not_published(
    user_client, event_client, registration_client, unique
):
    """IT-R04: event in draft -> 422 EVENT_NOT_OPEN."""
    organizer = make_user(user_client, unique, role="organizer")
    attendee = make_user(user_client, unique)
    event = make_event(event_client, organizer["id"], unique, status="draft")
    resp = _register(registration_client, attendee["id"], event["id"])
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "EVENT_NOT_OPEN"


def test_it_r05_double_registration(
    user_client, event_client, registration_client, unique
):
    """IT-R05: double registration -> 409 ALREADY_REGISTERED."""
    organizer = make_user(user_client, unique, role="organizer")
    attendee = make_user(user_client, unique)
    event = make_event(event_client, organizer["id"], unique, status="published")

    first = _register(registration_client, attendee["id"], event["id"])
    assert first.status_code == 201, first.text
    second = _register(registration_client, attendee["id"], event["id"])
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "ALREADY_REGISTERED"


def test_it_r06_event_full(
    user_client, event_client, registration_client, unique
):
    """IT-R06: capacity 2, third registration -> 409 EVENT_FULL."""
    organizer = make_user(user_client, unique, role="organizer")
    event = make_event(
        event_client, organizer["id"], unique, capacity=2, status="published"
    )
    for _ in range(2):
        attendee = make_user(user_client, unique)
        ok = _register(registration_client, attendee["id"], event["id"])
        assert ok.status_code == 201, ok.text

    third = make_user(user_client, unique)
    resp = _register(registration_client, third["id"], event["id"])
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "EVENT_FULL"


def test_it_r07_cancel_frees_seat(
    user_client, event_client, registration_client, unique
):
    """IT-R07: cancellation -> 200 and seat freed; cancelled->confirmed -> 422."""
    organizer = make_user(user_client, unique, role="organizer")
    event = make_event(
        event_client, organizer["id"], unique, capacity=1, status="published"
    )
    a1 = make_user(user_client, unique)
    reg = _register(registration_client, a1["id"], event["id"]).json()

    cancelled = registration_client.patch(
        f"/api/v1/registrations/{reg['id']}", json={"status": "cancelled"}
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    # Seat freed: a new attendee can now register.
    a2 = make_user(user_client, unique)
    again = _register(registration_client, a2["id"], event["id"])
    assert again.status_code == 201, again.text

    # cancelled -> confirmed is not allowed.
    invalid = registration_client.patch(
        f"/api/v1/registrations/{reg['id']}", json={"status": "confirmed"}
    )
    assert invalid.status_code == 422, invalid.text
    assert invalid.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_it_r08_stats(user_client, event_client, registration_client, unique):
    """IT-R08: stats capacity/confirmed/available; unknown event -> 404."""
    organizer = make_user(user_client, unique, role="organizer")
    event = make_event(
        event_client, organizer["id"], unique, capacity=5, status="published"
    )
    for _ in range(2):
        attendee = make_user(user_client, unique)
        _register(registration_client, attendee["id"], event["id"])

    stats = registration_client.get(
        f"/api/v1/registrations/stats?event_id={event['id']}"
    )
    assert stats.status_code == 200, stats.text
    body = stats.json()
    assert body["event_id"] == event["id"]
    assert body["capacity"] == 5
    assert body["confirmed"] == 2
    assert body["available"] == 3

    missing = registration_client.get(
        f"/api/v1/registrations/stats?event_id={unique.uuid()}"
    )
    assert missing.status_code == 404, missing.text
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_it_r09_put_not_allowed(registration_client, unique):
    """IT-R09: PUT -> 405."""
    resp = registration_client.put(f"/api/v1/registrations/{unique.uuid()}")
    assert resp.status_code == 405, resp.text


@pytest.mark.resilience
def test_it_r10_dependency_unreachable(dead_dependency_client, unique):
    """IT-R10: dependency unreachable -> 503 DEPENDENCY_UNAVAILABLE."""
    client = dead_dependency_client("registration")
    resp = client.post(
        "/api/v1/registrations",
        json={"user_id": unique.uuid(), "event_id": unique.uuid()},
    )
    assert resp.status_code == 503, resp.text
    assert resp.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
