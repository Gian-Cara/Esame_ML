"""End-to-end journey — IT-J02 (all services, optional).

Like IT-J01 + feedback from registrants + a thank-you broadcast.
"""

from __future__ import annotations

import pytest

from conftest import make_event, make_user

pytestmark = [pytest.mark.optional, pytest.mark.e2e]


def test_it_j02_full_platform_journey(
    user_client, event_client, registration_client, feedback_client,
    notification_client, unique
):
    organizer = make_user(user_client, unique, role="organizer")
    attendees = [make_user(user_client, unique) for _ in range(3)]

    event = make_event(
        event_client, organizer["id"], unique, capacity=2, status="published"
    )

    def register(user_id):
        return registration_client.post(
            "/api/v1/registrations",
            json={"user_id": user_id, "event_id": event["id"]},
        )

    r1 = register(attendees[0]["id"])
    r2 = register(attendees[1]["id"])
    assert r1.status_code == 201 and r2.status_code == 201

    full = register(attendees[2]["id"])
    assert full.status_code == 409 and full.json()["error"]["code"] == "EVENT_FULL"

    # Cancel first, third joins.
    registration_client.patch(
        f"/api/v1/registrations/{r1.json()['id']}", json={"status": "cancelled"}
    )
    r3 = register(attendees[2]["id"])
    assert r3.status_code == 201, r3.text

    # Confirmed registrants (attendee[1], attendee[2]) leave feedback.
    for attendee, rating in ((attendees[1], 5), (attendees[2], 4)):
        fb = feedback_client.post(
            "/api/v1/feedbacks",
            json={"user_id": attendee["id"], "event_id": event["id"], "rating": rating},
        )
        assert fb.status_code == 201, fb.text

    summary = feedback_client.get(
        f"/api/v1/feedbacks/summary?event_id={event['id']}"
    ).json()
    assert summary["count"] == 2
    assert abs(summary["average_rating"] - 4.5) < 1e-6

    # Thank-you broadcast reaches the 2 confirmed registrants.
    bc = notification_client.post(
        "/api/v1/notifications/broadcast",
        json={"event_id": event["id"], "channel": "email",
              "subject": "Thanks", "body": "Grazie!"},
    )
    assert bc.status_code == 201, bc.text
    assert bc.json()["created"] == 2
