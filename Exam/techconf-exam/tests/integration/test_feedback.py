"""Acceptance tests — feedback-service (IT-F01..IT-F05). Optional."""

from __future__ import annotations

import pytest

from conftest import make_event, make_user

pytestmark = [pytest.mark.optional, pytest.mark.feedback]


def _register(registration_client, user_id, event_id):
    return registration_client.post(
        "/api/v1/registrations",
        json={"user_id": user_id, "event_id": event_id},
    )


def _confirmed_attendee(user_client, event_client, registration_client, event, unique):
    attendee = make_user(user_client, unique)
    reg = _register(registration_client, attendee["id"], event["id"])
    assert reg.status_code == 201, reg.text
    return attendee, reg.json()


def test_it_f01_registered_user_can_feedback(
    user_client, event_client, registration_client, feedback_client, unique
):
    """IT-F01: registered user -> 201."""
    organizer = make_user(user_client, unique, role="organizer")
    event = make_event(event_client, organizer["id"], unique, status="published")
    attendee, _ = _confirmed_attendee(
        user_client, event_client, registration_client, event, unique
    )
    resp = feedback_client.post(
        "/api/v1/feedbacks",
        json={"user_id": attendee["id"], "event_id": event["id"], "rating": 5,
              "comment": "Great"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.headers.get("Location")


def test_it_f02_not_registered(
    user_client, event_client, registration_client, feedback_client, unique
):
    """IT-F02: user not registered (or cancelled) -> 422 NOT_REGISTERED."""
    organizer = make_user(user_client, unique, role="organizer")
    event = make_event(event_client, organizer["id"], unique, status="published")
    stranger = make_user(user_client, unique)

    resp = feedback_client.post(
        "/api/v1/feedbacks",
        json={"user_id": stranger["id"], "event_id": event["id"], "rating": 4},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "NOT_REGISTERED"


def test_it_f03_double_feedback_and_bad_rating(
    user_client, event_client, registration_client, feedback_client, unique
):
    """IT-F03: double feedback -> 409; rating=6 -> 422."""
    organizer = make_user(user_client, unique, role="organizer")
    event = make_event(event_client, organizer["id"], unique, status="published")
    attendee, _ = _confirmed_attendee(
        user_client, event_client, registration_client, event, unique
    )

    first = feedback_client.post(
        "/api/v1/feedbacks",
        json={"user_id": attendee["id"], "event_id": event["id"], "rating": 4},
    )
    assert first.status_code == 201, first.text

    dup = feedback_client.post(
        "/api/v1/feedbacks",
        json={"user_id": attendee["id"], "event_id": event["id"], "rating": 3},
    )
    assert dup.status_code == 409, dup.text
    assert dup.json()["error"]["code"] == "FEEDBACK_ALREADY_EXISTS"

    bad = feedback_client.post(
        "/api/v1/feedbacks",
        json={"user_id": attendee["id"], "event_id": event["id"], "rating": 6},
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"


def test_it_f04_summary(
    user_client, event_client, registration_client, feedback_client, unique
):
    """IT-F04: summary count/average_rating; unknown event -> 404."""
    organizer = make_user(user_client, unique, role="organizer")
    event = make_event(event_client, organizer["id"], unique, status="published")

    ratings = [4, 5]
    for r in ratings:
        attendee, _ = _confirmed_attendee(
            user_client, event_client, registration_client, event, unique
        )
        posted = feedback_client.post(
            "/api/v1/feedbacks",
            json={"user_id": attendee["id"], "event_id": event["id"], "rating": r},
        )
        assert posted.status_code == 201, posted.text

    summary = feedback_client.get(f"/api/v1/feedbacks/summary?event_id={event['id']}")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["count"] == 2
    assert abs(body["average_rating"] - 4.5) < 1e-6

    missing = feedback_client.get(f"/api/v1/feedbacks/summary?event_id={unique.uuid()}")
    assert missing.status_code == 404, missing.text
    assert missing.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.resilience
def test_it_f05_dependency_unreachable(dead_dependency_client, unique):
    """IT-F05: registration-service unreachable -> 503."""
    client = dead_dependency_client("feedback")
    resp = client.post(
        "/api/v1/feedbacks",
        json={"user_id": unique.uuid(), "event_id": unique.uuid(), "rating": 5},
    )
    assert resp.status_code == 503, resp.text
    assert resp.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
