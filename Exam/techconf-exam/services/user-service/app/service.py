"""
service.py — business rules for user-service.

All REQ-USR-* rules live here. This module does not import Flask and
does not read environment variables directly.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Custom exceptions (translated to HTTP codes in routes.py)
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    """422 — field validation failed."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConflictError(Exception):
    """409 — uniqueness constraint violated."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class NotFoundError(Exception):
    """404 — resource not found."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_ROLES = {"attendee", "speaker", "organizer"}
USER_INPUT_FIELDS = {"first_name", "last_name", "email", "company", "role"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_user_fields(data: dict, partial: bool = False) -> None:
    """Validate input types, allowed properties, and field constraints."""
    errors: dict[str, str] = {}

    unknown = sorted(set(data) - USER_INPUT_FIELDS)
    if unknown:
        errors["fields"] = f"Unknown fields: {', '.join(unknown)}."

    for field in ("first_name", "last_name"):
        if not partial or field in data:
            value = data.get(field)
            if not isinstance(value, str):
                errors[field] = "Must be a string."
            elif not (1 <= len(value) <= 50):
                errors[field] = "Must be 1–50 characters."

    if not partial or "email" in data:
        value = data.get("email")
        if not isinstance(value, str) or not EMAIL_RE.fullmatch(value):
            errors["email"] = "Must be a valid email address."

    if "company" in data and data["company"] is not None:
        value = data["company"]
        if not isinstance(value, str):
            errors["company"] = "Must be a string or null."
        elif len(value) > 100:
            errors["company"] = "Must be at most 100 characters."

    if "role" in data:
        value = data["role"]
        if not isinstance(value, str) or value not in VALID_ROLES:
            errors["role"] = f"Must be one of: {', '.join(sorted(VALID_ROLES))}."

    if errors:
        raise ValidationError("Validation failed.", details=errors)


# ---------------------------------------------------------------------------
# UserService
# ---------------------------------------------------------------------------

class UserService:
    def __init__(self, repository: Any) -> None:
        self._repo = repository

    # ------------------------------------------------------------------
    # Create  REQ-USR-01, REQ-USR-02, REQ-USR-03
    # ------------------------------------------------------------------
    def create_user(self, data: dict) -> dict:
        # Required fields present
        for field in ("first_name", "last_name", "email"):
            if field not in data or data[field] is None or str(data[field]).strip() == "":
                raise ValidationError(f"'{field}' is required.")

        _validate_user_fields(data)

        email_lower = data["email"].lower()  # REQ-USR-02 normalise

        # Uniqueness check  REQ-USR-02
        if self._repo.email_exists(email_lower):
            raise ConflictError("EMAIL_ALREADY_EXISTS", "A user with this email already exists.")

        now = _now_utc()
        user = {
            "id": str(uuid.uuid4()),
            "first_name": data["first_name"],
            "last_name": data["last_name"],
            "email": email_lower,
            "company": data.get("company"),
            "role": data.get("role", "attendee"),   # REQ-USR-01 default
            "created_at": now,
            "updated_at": now,
        }
        return self._repo.create(user)

    # ------------------------------------------------------------------
    # Read  REQ-USR-04
    # ------------------------------------------------------------------
    def get_user(self, user_id: str) -> dict:
        user = self._repo.get(user_id)
        if user is None:
            raise NotFoundError(f"User '{user_id}' not found.")
        return user

    # ------------------------------------------------------------------
    # List  REQ-USR-05
    # ------------------------------------------------------------------
    def list_users(self, filters: dict, page: int, page_size: int) -> dict:
        if page < 1:
            raise ValidationError("'page' must be ≥ 1.")
        if not (1 <= page_size <= 100):
            raise ValidationError("'page_size' must be between 1 and 100.")
        if "role" in filters and filters["role"] not in VALID_ROLES:
            raise ValidationError(f"'role' must be one of: {', '.join(sorted(VALID_ROLES))}.")

        items, total = self._repo.list(filters, page, page_size)
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    # ------------------------------------------------------------------
    # Replace (PUT)  REQ-USR-06
    # ------------------------------------------------------------------
    def replace_user(self, user_id: str, data: dict) -> dict:
        existing = self._repo.get(user_id)
        if existing is None:
            raise NotFoundError(f"User '{user_id}' not found.")

        for field in ("first_name", "last_name", "email"):
            if field not in data or data[field] is None or str(data[field]).strip() == "":
                raise ValidationError(f"'{field}' is required.")

        _validate_user_fields(data)

        email_lower = data["email"].lower()
        if self._repo.email_exists(email_lower, exclude_id=user_id):
            raise ConflictError("EMAIL_ALREADY_EXISTS", "A user with this email already exists.")

        updated = {
            "id": user_id,
            "first_name": data["first_name"],
            "last_name": data["last_name"],
            "email": email_lower,
            "company": data.get("company"),
            "role": data.get("role", "attendee"),
            "created_at": existing["created_at"],
            "updated_at": _now_utc(),
        }
        return self._repo.update(user_id, updated)

    # ------------------------------------------------------------------
    # Partial update (PATCH)  REQ-USR-07
    # ------------------------------------------------------------------
    def update_user(self, user_id: str, data: dict) -> dict:
        existing = self._repo.get(user_id)
        if existing is None:
            raise NotFoundError(f"User '{user_id}' not found.")

        _validate_user_fields(data, partial=True)

        if "email" in data:
            email_lower = data["email"].lower()
            if self._repo.email_exists(email_lower, exclude_id=user_id):
                raise ConflictError("EMAIL_ALREADY_EXISTS", "A user with this email already exists.")
            data["email"] = email_lower

        data["updated_at"] = _now_utc()
        # Protect immutable fields
        data.pop("id", None)
        data.pop("created_at", None)

        return self._repo.update(user_id, data)

    # ------------------------------------------------------------------
    # Delete  REQ-USR-08
    # ------------------------------------------------------------------
    def delete_user(self, user_id: str) -> None:
        if not self._repo.delete(user_id):
            raise NotFoundError(f"User '{user_id}' not found.")
