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

    # ------------------------------------------------------------------
    # Create — REQ-REG-01, B01..B06
    # ------------------------------------------------------------------
    def create_registration(self, data: dict) -> dict:
        # Required fields
        for f in ("user_id", "event_id"):
            if f not in data or not data[f]:
                raise ValidationError("VALIDATION_ERROR", f"'{f}' is required.")

        user_id = data["user_id"]
        event_id = data["event_id"]

        # REQ-REG-B01 user exists
        try:
            user = self._users.get_user(user_id)
        except DependencyError as e:
            raise DependencyUnavailableError(str(e)) from e
        if user is None:
            raise ValidationError("REFERENCE_NOT_FOUND", "User not found.")

        # REQ-REG-B02 event exists
        try:
            event = self._events.get_event(event_id)
        except DependencyError as e:
            raise DependencyUnavailableError(str(e)) from e
        if event is None:
            raise ValidationError("REFERENCE_NOT_FOUND", "Event not found.")

        # REQ-REG-B03 event published
        if event.get("status") != "published":
            raise ValidationError("EVENT_NOT_OPEN", "Event is not open for registration.")

        # REQ-REG-B04 no duplicate confirmed
        if self._repo.has_confirmed(user_id, event_id):
            raise ConflictError("ALREADY_REGISTERED", "User already registered for this event.")

        # REQ-REG-B05 capacity
        confirmed = self._repo.count_confirmed(event_id)
        if confirmed >= int(event["capacity"]):
            raise ConflictError("EVENT_FULL", "Event has reached capacity.")

        # REQ-REG-B06 amount from event.price
        now = _now()
        reg = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "event_id": event_id,
            "amount": round(float(event["price"]), 2),
            "status": "confirmed",
            "created_at": now,
            "updated_at": now,
        }
        return self._repo.create(reg)

    # ------------------------------------------------------------------
    def get_registration(self, reg_id: str) -> dict:
        reg = self._repo.get(reg_id)
        if reg is None:
            raise NotFoundError(f"Registration '{reg_id}' not found.")
        return reg

    def list_registrations(self, filters: dict, page: int, page_size: int) -> dict:
        if page < 1:
            raise ValidationError("VALIDATION_ERROR", "'page' must be >= 1.")
        if not (1 <= page_size <= 100):
            raise ValidationError("VALIDATION_ERROR", "'page_size' must be 1-100.")
        if "status" in filters and filters["status"] not in ("confirmed", "cancelled"):
            raise ValidationError("VALIDATION_ERROR", "Invalid status filter.")
        items, total = self._repo.list(filters, page, page_size)
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    # ------------------------------------------------------------------
    # PATCH — REQ-REG-B07
    # ------------------------------------------------------------------
    def update_status(self, reg_id: str, data: dict) -> dict:
        reg = self._repo.get(reg_id)
        if reg is None:
            raise NotFoundError(f"Registration '{reg_id}' not found.")
        if "status" not in data:
            raise ValidationError("VALIDATION_ERROR", "'status' is required.")
        new_status = data["status"]
        if new_status not in ("confirmed", "cancelled"):
            raise ValidationError("VALIDATION_ERROR", "Invalid status.")
        current = reg["status"]
        if new_status == current:
            reg["updated_at"] = _now()
            return self._repo.update(reg_id, {"updated_at": reg["updated_at"]})
        # Only confirmed -> cancelled is allowed
        if not (current == "confirmed" and new_status == "cancelled"):
            raise ValidationError("INVALID_STATUS_TRANSITION",
                                  f"Transition {current}->{new_status} not allowed.")
        return self._repo.update(reg_id, {"status": "cancelled", "updated_at": _now()})

    # ------------------------------------------------------------------
    def delete_registration(self, reg_id: str) -> None:
        if not self._repo.delete(reg_id):
            raise NotFoundError(f"Registration '{reg_id}' not found.")

    # ------------------------------------------------------------------
    # Stats — REQ-REG-B08
    # ------------------------------------------------------------------
    def stats(self, event_id: str) -> dict:
        try:
            event = self._events.get_event(event_id)
        except DependencyError as e:
            raise DependencyUnavailableError(str(e)) from e
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
