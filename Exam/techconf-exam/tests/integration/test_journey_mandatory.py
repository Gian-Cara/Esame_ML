"""End-to-end journey — IT-J01 (mandatory).

Organizer + 3 attendees -> event (capacity 2) -> publish -> 2 registrations ->
3rd rejected -> 1 cancellation -> 3rd accepted -> stats coherent.
"""

from __future__ import annotations

import pytest

from conftest import make_event, make_user

pytestmark = [pytest.mark.mandatory, pytest.mark.e2e]


def test_it_j01_full_journey(user_client, event_client, registration_client, unique):
    organizer = make_user(user_client, unique, role="organizer")
    attendees = [make_user(user_client, unique) for _ in range(3)]

    event = make_event(
        event_client, organizer["id"], unique, capacity=2, status="published"
    )

    def register(user_id, validate=True):
        return registration_client.post(
            "/api/v1/registrations",
            json={"user_id": user_id, "event_id": event["id"]},
            validate=validate,
        )

    r1 = register(attendees[0]["id"])
    r2 = register(attendees[1]["id"])
    assert r1.status_code == 201 and r2.status_code == 201

    # Third registration rejected: EVENT_FULL.
    r3 = register(attendees[2]["id"])
    assert r3.status_code == 409, r3.text
    assert r3.json()["error"]["code"] == "EVENT_FULL"

    # Cancel the first registration -> frees a seat.
    reg1 = r1.json()
    cancelled = registration_client.patch(
        f"/api/v1/registrations/{reg1['id']}", json={"status": "cancelled"}
    )
    assert cancelled.status_code == 200, cancelled.text

    # Now the third attendee can register.
    r3b = register(attendees[2]["id"])
    assert r3b.status_code == 201, r3b.text

    # Stats: capacity 2, confirmed 2 (attendee[1] + attendee[2]), available 0.
    stats = registration_client.get(
        f"/api/v1/registrations/stats?event_id={event['id']}"
    ).json()
    assert stats["capacity"] == 2
    assert stats["confirmed"] == 2
    assert stats["available"] == 0
