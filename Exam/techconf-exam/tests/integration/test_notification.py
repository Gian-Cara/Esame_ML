"""Acceptance tests — notification-service (IT-N01..IT-N04). Optional."""

from __future__ import annotations

import pytest

from conftest import make_event, make_user

pytestmark = [pytest.mark.optional, pytest.mark.notification]


def _notification_payload(user_id):
    return {
        "user_id": user_id,
        "channel": "email",
        "subject": "Welcome",
        "body": "Thanks for joining TechConf.",
    }


def test_it_n01_create_for_existing_user(user_client, notification_client, unique):
    """IT-N01: create for existing user -> 201, status=queued."""
    user = make_user(user_client, unique)
    resp = notification_client.post(
        "/api/v1/notifications", json=_notification_payload(user["id"])
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["sent_at"] is None
    assert resp.headers.get("Location")


def test_it_n02_user_not_found(notification_client, unique):
    """IT-N02: unknown user -> 422 REFERENCE_NOT_FOUND."""
    resp = notification_client.post(
        "/api/v1/notifications", json=_notification_payload(unique.uuid())
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "REFERENCE_NOT_FOUND"


def test_it_n03_status_transitions(user_client, notification_client, unique):
    """IT-N03: queued->sent sets sent_at; sent->queued -> 422."""
    user = make_user(user_client, unique)
    created = notification_client.post(
        "/api/v1/notifications", json=_notification_payload(user["id"])
    ).json()

    sent = notification_client.patch(
        f"/api/v1/notifications/{created['id']}", json={"status": "sent"}
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "sent"
    assert sent.json()["sent_at"] is not None

    invalid = notification_client.patch(
        f"/api/v1/notifications/{created['id']}", json={"status": "queued"}
    )
    assert invalid.status_code == 422, invalid.text
    assert invalid.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_it_n04_broadcast_only_confirmed(
    user_client, event_client, registration_client, notification_client, unique
):
    """IT-N04: broadcast creates n notifications only for confirmed registrants."""
    organizer = make_user(user_client, unique, role="organizer")
    event = make_event(
        event_client, organizer["id"], unique, capacity=10, status="published"
    )

    # Two confirmed, one cancelled.
    confirmed_ids = []
    for _ in range(2):
        attendee = make_user(user_client, unique)
        reg = registration_client.post(
            "/api/v1/registrations",
            json={"user_id": attendee["id"], "event_id": event["id"]},
        )
        assert reg.status_code == 201, reg.text
        confirmed_ids.append(attendee["id"])

    cancel_attendee = make_user(user_client, unique)
    creg = registration_client.post(
        "/api/v1/registrations",
        json={"user_id": cancel_attendee["id"], "event_id": event["id"]},
    ).json()
    registration_client.patch(
        f"/api/v1/registrations/{creg['id']}", json={"status": "cancelled"}
    )

    resp = notification_client.post(
        "/api/v1/notifications/broadcast",
        json={
            "event_id": event["id"],
            "channel": "email",
            "subject": "Thank you",
            "body": "See you next year!",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["event_id"] == event["id"]
    assert body["created"] == 2  # only the confirmed registrants
