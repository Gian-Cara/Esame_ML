"""service.py — business rules for registration-service (REQ-REG-*)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .clients import DependencyError


class ValidationError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class ConflictError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class NotFoundError(Exception):
    pass


class DependencyUnavailableError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RegistrationService:
    def __init__(self, repository: Any, user_client: Any, event_client: Any) -> None:
        self._repo = repository
        self._users = user_client
        self._events = event_client

    def create_registration(self, data: dict) -> dict:
        unknown = sorted(set(data) - {"user_id", "event_id"})
        if unknown:
            raise ValidationError(
                "VALIDATION_ERROR", f"Unknown fields: {', '.join(unknown)}."
            )
        for field in ("user_id", "event_id"):
            if field not in data or not isinstance(data[field], str) or not data[field]:
                raise ValidationError(
                    "VALIDATION_ERROR", f"'{field}' must be a non-empty UUID string."
                )

        user_id = data["user_id"]
        event_id = data["event_id"]

        try:
            user = self._users.get_user(user_id)
        except DependencyError as exc:
            raise DependencyUnavailableError(str(exc)) from exc
        if user is None:
            raise ValidationError("REFERENCE_NOT_FOUND", "User not found.")

        try:
            event = self._events.get_event(event_id)
        except DependencyError as exc:
            raise DependencyUnavailableError(str(exc)) from exc
        if event is None:
            raise ValidationError("REFERENCE_NOT_FOUND", "Event not found.")
        if event.get("status") != "published":
            raise ValidationError("EVENT_NOT_OPEN", "Event is not open for registration.")
        if self._repo.has_confirmed(user_id, event_id):
            raise ConflictError(
                "ALREADY_REGISTERED", "User already registered for this event."
            )

        confirmed = self._repo.count_confirmed(event_id)
        if confirmed >= int(event["capacity"]):
            raise ConflictError("EVENT_FULL", "Event has reached capacity.")

        now = _now()
        registration = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "event_id": event_id,
            "amount": round(float(event["price"]), 2),
            "status": "confirmed",
            "created_at": now,
            "updated_at": now,
        }
        return self._repo.create(registration)

    def get_registration(self, reg_id: str) -> dict:
        registration = self._repo.get(reg_id)
        if registration is None:
            raise NotFoundError(f"Registration '{reg_id}' not found.")
        return registration

    def list_registrations(self, filters: dict, page: int, page_size: int) -> dict:
        if page < 1:
            raise ValidationError("VALIDATION_ERROR", "'page' must be >= 1.")
        if not (1 <= page_size <= 100):
            raise ValidationError("VALIDATION_ERROR", "'page_size' must be 1-100.")
        if "status" in filters and filters["status"] not in ("confirmed", "cancelled"):
            raise ValidationError("VALIDATION_ERROR", "Invalid status filter.")
        items, total = self._repo.list(filters, page, page_size)
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    def update_status(self, reg_id: str, data: dict) -> dict:
        registration = self._repo.get(reg_id)
        if registration is None:
            raise NotFoundError(f"Registration '{reg_id}' not found.")
        unknown = sorted(set(data) - {"status"})
        if unknown:
            raise ValidationError(
                "VALIDATION_ERROR", f"Unknown fields: {', '.join(unknown)}."
            )
        if "status" not in data:
            raise ValidationError("VALIDATION_ERROR", "'status' is required.")
        new_status = data["status"]
        if not isinstance(new_status, str) or new_status not in ("confirmed", "cancelled"):
            raise ValidationError("VALIDATION_ERROR", "Invalid status.")
        current = registration["status"]
        if not (current == "confirmed" and new_status == "cancelled"):
            raise ValidationError(
                "INVALID_STATUS_TRANSITION",
                f"Transition {current}->{new_status} not allowed.",
            )
        return self._repo.update(
            reg_id, {"status": "cancelled", "updated_at": _now()}
        )

    def delete_registration(self, reg_id: str) -> None:
        if not self._repo.delete(reg_id):
            raise NotFoundError(f"Registration '{reg_id}' not found.")

    def stats(self, event_id: str) -> dict:
        try:
            event = self._events.get_event(event_id)
        except DependencyError as exc:
            raise DependencyUnavailableError(str(exc)) from exc
        if event is None:
            raise NotFoundError(f"Event '{event_id}' not found.")
        capacity = int(event["capacity"])
        confirmed = self._repo.count_confirmed(event_id)
        return {
            "event_id": event_id,
            "capacity": capacity,
            "confirmed": confirmed,
            "available": capacity - confirmed,
        }
