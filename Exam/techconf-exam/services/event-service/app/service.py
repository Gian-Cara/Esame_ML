"""service.py — business rules for event-service (REQ-EVT-*)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .clients import DependencyError


class ValidationError(Exception):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(Exception):
    pass


class DependencyUnavailableError(Exception):
    pass


class InvalidStatusTransitionError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


VALID_STATUSES = {"draft", "published", "cancelled"}
ALLOWED_TRANSITIONS = {
    ("draft", "published"),
    ("draft", "cancelled"),
    ("published", "cancelled"),
}
EVENT_INPUT_FIELDS = {
    "title",
    "description",
    "organizer_id",
    "venue",
    "city",
    "start_date",
    "end_date",
    "capacity",
    "price",
    "status",
}
REQUIRED_EVENT_FIELDS = (
    "title",
    "organizer_id",
    "venue",
    "city",
    "start_date",
    "end_date",
    "capacity",
    "price",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_date(field: str, value: object, errors: dict[str, str]):
    if not isinstance(value, str):
        errors[field] = "Must be a date string in YYYY-MM-DD format."
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        errors[field] = "Must be a valid date in YYYY-MM-DD format."
        return None


def _validate_fields(data: dict, partial: bool = False) -> None:
    """Validate allowed properties, JSON types, constraints, and full date ranges."""
    errors: dict[str, str] = {}

    unknown = sorted(set(data) - EVENT_INPUT_FIELDS)
    if unknown:
        errors["fields"] = f"Unknown fields: {', '.join(unknown)}."

    if not partial or "title" in data:
        value = data.get("title")
        if not isinstance(value, str):
            errors["title"] = "Must be a string."
        elif not (3 <= len(value) <= 120):
            errors["title"] = "Must be 3–120 characters."

    if "description" in data and data["description"] is not None:
        value = data["description"]
        if not isinstance(value, str):
            errors["description"] = "Must be a string or null."
        elif len(value) > 2000:
            errors["description"] = "Must be at most 2000 characters."

    for field, maximum in (("venue", 100), ("city", 60)):
        if not partial or field in data:
            value = data.get(field)
            if not isinstance(value, str):
                errors[field] = "Must be a string."
            elif not (1 <= len(value) <= maximum):
                errors[field] = f"Must be 1–{maximum} characters."

    if not partial or "organizer_id" in data:
        value = data.get("organizer_id")
        if not isinstance(value, str) or not value:
            errors["organizer_id"] = "Must be a non-empty UUID string."

    if not partial or "capacity" in data:
        value = data.get("capacity")
        if isinstance(value, bool) or not isinstance(value, int):
            errors["capacity"] = "Must be an integer."
        elif not (1 <= value <= 10000):
            errors["capacity"] = "Must be 1–10000."

    if not partial or "price" in data:
        value = data.get("price")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors["price"] = "Must be a number."
        elif value < 0:
            errors["price"] = "Must be ≥ 0."

    if "status" in data:
        value = data["status"]
        if not isinstance(value, str) or value not in VALID_STATUSES:
            errors["status"] = f"Must be one of: {', '.join(sorted(VALID_STATUSES))}."

    parsed_dates = {}
    for field in ("start_date", "end_date"):
        if not partial or field in data:
            parsed_dates[field] = _parse_date(field, data.get(field), errors)

    if not partial and not errors:
        if parsed_dates["end_date"] < parsed_dates["start_date"]:
            errors["end_date"] = "Must be greater than or equal to start_date."

    if errors:
        raise ValidationError("Validation failed.", details=errors)


def _validate_merged_date_range(existing: dict, changes: dict) -> None:
    """Validate the final range when PATCH changes only one of the two dates."""
    start = datetime.strptime(changes.get("start_date", existing["start_date"]), "%Y-%m-%d").date()
    end = datetime.strptime(changes.get("end_date", existing["end_date"]), "%Y-%m-%d").date()
    if end < start:
        raise ValidationError(
            "end_date must be >= start_date.",
            details={"end_date": "Must be greater than or equal to start_date."},
        )


class EventService:
    def __init__(self, repository: Any, client: Any) -> None:
        self._repo = repository
        self._client = client

    def _validate_organizer(self, organizer_id: str) -> None:
        try:
            user = self._client.get_user(organizer_id)
        except DependencyError as exc:
            raise DependencyUnavailableError(str(exc)) from exc
        if user is None:
            raise ValidationError(
                "Organizer not found.", details={"organizer_id": "REFERENCE_NOT_FOUND"}
            )
        if user.get("role") != "organizer":
            raise ValidationError(
                "User is not an organizer.", details={"organizer_id": "INVALID_ORGANIZER"}
            )

    def create_event(self, data: dict) -> dict:
        for field in REQUIRED_EVENT_FIELDS:
            if field not in data or data[field] is None:
                raise ValidationError(f"'{field}' is required.")
        _validate_fields(data)
        self._validate_organizer(data["organizer_id"])
        now = _now()
        event = {
            "id": str(uuid.uuid4()),
            "title": data["title"],
            "description": data.get("description"),
            "organizer_id": data["organizer_id"],
            "venue": data["venue"],
            "city": data["city"],
            "start_date": data["start_date"],
            "end_date": data["end_date"],
            "capacity": data["capacity"],
            "price": round(float(data["price"]), 2),
            "status": data.get("status", "draft"),
            "created_at": now,
            "updated_at": now,
        }
        return self._repo.create(event)

    def get_event(self, event_id: str) -> dict:
        event = self._repo.get(event_id)
        if event is None:
            raise NotFoundError(f"Event '{event_id}' not found.")
        return event

    def list_events(self, filters: dict, page: int, page_size: int) -> dict:
        if page < 1:
            raise ValidationError("'page' must be ≥ 1.")
        if not (1 <= page_size <= 100):
            raise ValidationError("'page_size' must be 1–100.")
        if "status" in filters and filters["status"] not in VALID_STATUSES:
            raise ValidationError(
                f"'status' must be one of: {', '.join(sorted(VALID_STATUSES))}."
            )
        items, total = self._repo.list(filters, page, page_size)
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    def replace_event(self, event_id: str, data: dict) -> dict:
        existing = self._repo.get(event_id)
        if existing is None:
            raise NotFoundError(f"Event '{event_id}' not found.")
        for field in REQUIRED_EVENT_FIELDS:
            if field not in data or data[field] is None:
                raise ValidationError(f"'{field}' is required.")
        _validate_fields(data)
        new_status = data.get("status", existing["status"])
        if (
            new_status != existing["status"]
            and (existing["status"], new_status) not in ALLOWED_TRANSITIONS
        ):
            raise InvalidStatusTransitionError(
                f"Transition {existing['status']}→{new_status} not allowed."
            )
        self._validate_organizer(data["organizer_id"])
        updated = {
            "id": event_id,
            "title": data["title"],
            "description": data.get("description"),
            "organizer_id": data["organizer_id"],
            "venue": data["venue"],
            "city": data["city"],
            "start_date": data["start_date"],
            "end_date": data["end_date"],
            "capacity": data["capacity"],
            "price": round(float(data["price"]), 2),
            "status": new_status,
            "created_at": existing["created_at"],
            "updated_at": _now(),
        }
        return self._repo.update(event_id, updated)

    def update_event(self, event_id: str, data: dict) -> dict:
        existing = self._repo.get(event_id)
        if existing is None:
            raise NotFoundError(f"Event '{event_id}' not found.")
        _validate_fields(data, partial=True)
        _validate_merged_date_range(existing, data)
        if (
            "status" in data
            and data["status"] != existing["status"]
            and (existing["status"], data["status"]) not in ALLOWED_TRANSITIONS
        ):
            raise InvalidStatusTransitionError(
                f"Transition {existing['status']}→{data['status']} not allowed."
            )
        if "organizer_id" in data:
            self._validate_organizer(data["organizer_id"])
        if "price" in data:
            data["price"] = round(float(data["price"]), 2)
        data["updated_at"] = _now()
        return self._repo.update(event_id, data)

    def delete_event(self, event_id: str) -> None:
        if not self._repo.delete(event_id):
            raise NotFoundError(f"Event '{event_id}' not found.")
