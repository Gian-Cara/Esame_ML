"""clients.py — HTTP client to user-service."""
from __future__ import annotations

import requests

from . import config


class DependencyError(Exception):
    """Raised when a downstream service is unavailable."""


class UserServiceClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base = (base_url or config.USER_SERVICE_URL).rstrip("/")

    def get_user(self, user_id: str) -> dict | None:
        """Return user dict on 200, None on 404, raise DependencyError otherwise."""
        try:
            resp = requests.get(
                f"{self._base}/api/v1/users/{user_id}", timeout=2
            )
        except requests.exceptions.RequestException as exc:
            raise DependencyError(str(exc)) from exc

        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            return None
        raise DependencyError(f"user-service returned {resp.status_code}")
