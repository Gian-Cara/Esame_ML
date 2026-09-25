"""service.py — business rules for event-service (REQ-EVT-*)."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from .clients import DependencyError

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
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

class InvalidStatusTransitionError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_STATUSES = {"draft", "published", "cancelled"}
ALLOWED_TRANSITIONS = {("draft", "published"), ("draft", "cancelled"), ("published", "cancelled")}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _validate_fields(data: dict, partial: bool = False) -> None:
    errors: dict[str, str] = {}

    if not partial or "title" in data:
        v = str(data.get("title", ""))
        if not (3 <= len(v) <= 120):
            errors["title"] = "Must be 3–120 characters."

    if "description" in data and data["description"] is not None:
        if len(str(data["description"])) > 2000:
            errors["description"] = "Max 2000 characters."

    if not partial or "venue" in data:
        v = str(data.get("venue", ""))
        if len(v) > 100 or (not partial and len(v) == 0):
            errors["venue"] = "Must be 1–100 characters."

    if not partial or "city" in data:
        v = str(data.get("city", ""))
        if len(v) > 60 or (not partial and len(v) == 0):
            errors["city"] = "Must be 1–60 characters."

    if not partial or "capacity" in data:
        try:
            cap = int(data.get("capacity", 1))
            if not (1 <= cap <= 10000):
                errors["capacity"] = "Must be 1–10000."
        except (TypeError, ValueError):
            errors["capacity"] = "Must be an integer."

    if not partial or "price" in data:
        try:
            price = float(data.get("price", 0))
            if price < 0:
                errors["price"] = "Must be ≥ 0."
        except (TypeError, ValueError):
            errors["price"] = "Must be a number."

    if "status" in data and data["status"] is not None:
        if data["status"] not in VALID_STATUSES:
            errors["status"] = f"Must be one of: {', '.join(sorted(VALID_STATUSES))}."

    # Date validation
    for field in ("start_date", "end_date"):
        if not partial or field in data:
            v = str(data.get(field, ""))
            if not DATE_RE.match(v):
                errors[field] = "Must be YYYY-MM-DD."

    if errors:
        raise ValidationError("Validation failed.", details=errors)

    # Cross-field: end_date >= start_date
    if not partial or ("start_date" in data and "end_date" in data):
        sd = data.get("start_date")
        ed = data.get("end_date")
        if sd and ed and not errors:
            if ed < sd:
                raise ValidationError("end_date must be >= start_date.", details={"end_date": "Must be >= start_date."})

# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class EventService:
    def __init__(self, repository: Any, client: Any) -> None:
        self._repo = repository
        self._client = client

    def _validate_organizer(self, organizer_id: str) -> None:
        try:
            user = self._client.get_user(organizer_id)
        except DependencyError as e:
            raise DependencyUnavailableError(str(e)) from e
        if user is None:
            raise ValidationError("Organizer not found.", details={"organizer_id": "REFERENCE_NOT_FOUND"})
        if user.get("role") != "organizer":
            raise ValidationError("User is not an organizer.", details={"organizer_id": "INVALID_ORGANIZER"})

    def create_event(self, data: dict) -> dict:
        required = ("title", "organizer_id", "venue", "city", "start_date", "end_date", "capacity", "price")
        for f in required:
            if f not in data or data[f] is None:
                raise ValidationError(f"'{f}' is required.")
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
            "capacity": int(data["capacity"]),
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
            raise ValidationError(f"'status' must be one of: {', '.join(sorted(VALID_STATUSES))}.")
        items, total = self._repo.list(filters, page, page_size)
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    def replace_event(self, event_id: str, data: dict) -> dict:
        existing = self._repo.get(event_id)
        if existing is None:
            raise NotFoundError(f"Event '{event_id}' not found.")
        required = ("title", "organizer_id", "venue", "city", "start_date", "end_date", "capacity", "price")
        for f in required:
            if f not in data or data[f] is None:
                raise ValidationError(f"'{f}' is required.")
        _validate_fields(data)
        # Status transition check
        new_status = data.get("status", existing["status"])
        if new_status != existing["status"]:
            if (existing["status"], new_status) not in ALLOWED_TRANSITIONS:
                raise InvalidStatusTransitionError(
                    f"Transition {existing['status']}→{new_status} not allowed."
                )
        if "organizer_id" in data:
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
            "capacity": int(data["capacity"]),
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
        # Status transition
        if "status" in data and data["status"] != existing["status"]:
            if (existing["status"], data["status"]) not in ALLOWED_TRANSITIONS:
                raise InvalidStatusTransitionError(
                    f"Transition {existing['status']}→{data['status']} not allowed."
                )
        if "organizer_id" in data:
            self._validate_organizer(data["organizer_id"])
        if "capacity" in data:
            data["capacity"] = int(data["capacity"])
        if "price" in data:
            data["price"] = round(float(data["price"]), 2)
        data.pop("id", None)
        data.pop("created_at", None)
        data["updated_at"] = _now()
        return self._repo.update(event_id, data)

    def delete_event(self, event_id: str) -> None:
        if not self._repo.delete(event_id):
            raise NotFoundError(f"Event '{event_id}' not found.")
