"""Shared fixtures and helpers for the TechConf acceptance suite.

Non-modifiable. Provides:
  * session-scoped platform launch (reads services.yaml);
  * per-service ``client`` fixtures that SKIP when the service is not declared;
  * a small HTTP client with contract validation baked in;
  * unique-data factories (random emails / titles) so no DB reset is needed.
"""

from __future__ import annotations

import random
import string
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import pytest
import requests

# Make contracts/validator.py importable.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "contracts"))

from validator import assert_matches_contract  # noqa: E402

from harness import (  # noqa: E402
    ACCEPTANCE_PORTS,
    MANDATORY,
    RunningService,
    ServiceSpec,
    launch_platform,
    launch_with_dead_dependency,
    load_manifest,
)


# --------------------------------------------------------------------------- #
# Session platform
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def manifest() -> dict[str, ServiceSpec]:
    return load_manifest()


@pytest.fixture(scope="session")
def platform(manifest: dict[str, ServiceSpec]) -> Iterator[dict[str, RunningService]]:
    if not manifest:
        pytest.skip("No services.yaml manifest found; nothing to test.")
    with launch_platform(manifest) as running:
        yield running


# --------------------------------------------------------------------------- #
# HTTP client with contract validation
# --------------------------------------------------------------------------- #


@dataclass
class ServiceClient:
    service: str
    base_url: str
    session: requests.Session

    def _url(self, path: str) -> str:
        return self.base_url + path

    def request(
        self, method: str, path: str, *, validate: bool = True, **kwargs: Any
    ) -> requests.Response:
        kwargs.setdefault("timeout", 5)
        resp = self.session.request(method, self._url(path), **kwargs)
        if validate:
            # Validate against the OpenAPI contract of this service.
            assert_matches_contract(self.service, method, path, resp)
        return resp

    def get(self, path: str, **kw: Any) -> requests.Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> requests.Response:
        return self.request("POST", path, **kw)

    def put(self, path: str, **kw: Any) -> requests.Response:
        return self.request("PUT", path, **kw)

    def patch(self, path: str, **kw: Any) -> requests.Response:
        return self.request("PATCH", path, **kw)

    def delete(self, path: str, **kw: Any) -> requests.Response:
        return self.request("DELETE", path, **kw)


def _client_for(
    service: str, platform: dict[str, RunningService]
) -> ServiceClient:
    if service not in platform:
        pytest.skip(f"Service '{service}' not declared in services.yaml (skipped).")
    running = platform[service]
    return ServiceClient(service, running.base_url, requests.Session())


@pytest.fixture
def user_client(platform: dict[str, RunningService]) -> ServiceClient:
    return _client_for("user", platform)


@pytest.fixture
def event_client(platform: dict[str, RunningService]) -> ServiceClient:
    return _client_for("event", platform)


@pytest.fixture
def registration_client(platform: dict[str, RunningService]) -> ServiceClient:
    return _client_for("registration", platform)


@pytest.fixture
def feedback_client(platform: dict[str, RunningService]) -> ServiceClient:
    return _client_for("feedback", platform)


@pytest.fixture
def notification_client(platform: dict[str, RunningService]) -> ServiceClient:
    return _client_for("notification", platform)


# --------------------------------------------------------------------------- #
# Resilience helper: launch a service with dead dependencies
# --------------------------------------------------------------------------- #


@pytest.fixture
def dead_dependency_client(manifest: dict[str, ServiceSpec]):
    """Return a factory that yields a ServiceClient pointed at an instance whose
    dependency URLs are unreachable (for 503 tests)."""

    started: list[Any] = []

    def _factory(service: str) -> ServiceClient:
        if service not in manifest:
            pytest.skip(f"Service '{service}' not declared in services.yaml (skipped).")
        cm = launch_with_dead_dependency(manifest[service])
        running = cm.__enter__()
        started.append(cm)
        return ServiceClient(service, running.base_url, requests.Session())

    yield _factory

    for cm in reversed(started):
        cm.__exit__(None, None, None)


# --------------------------------------------------------------------------- #
# Unique-data factories (no DB reset needed between runs)
# --------------------------------------------------------------------------- #


def _rand(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


@pytest.fixture
def unique():
    """Namespace of helpers producing globally-unique test data."""

    class _Unique:
        @staticmethod
        def email() -> str:
            return f"user_{_rand()}@example.com"

        @staticmethod
        def title() -> str:
            return f"Conf {_rand()} {_rand(4)}"

        @staticmethod
        def uuid() -> str:
            return str(uuid.uuid4())

        @staticmethod
        def token() -> str:
            return _rand(10)

    return _Unique()


# --------------------------------------------------------------------------- #
# Helpers reused across service tests (builders)
# --------------------------------------------------------------------------- #


def make_user(user_client: ServiceClient, unique, role: str = "attendee") -> dict:
    payload = {
        "first_name": "Test",
        "last_name": "User",
        "email": unique.email(),
        "role": role,
    }
    resp = user_client.post("/api/v1/users", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def make_event(
    event_client: ServiceClient,
    organizer_id: str,
    unique,
    *,
    capacity: int = 10,
    price: float = 149.00,
    status: str = "draft",
) -> dict:
    payload = {
        "title": unique.title(),
        "organizer_id": organizer_id,
        "venue": "Auditorium",
        "city": "Roma",
        "start_date": "2026-10-15",
        "end_date": "2026-10-16",
        "capacity": capacity,
        "price": price,
    }
    resp = event_client.post("/api/v1/events", json=payload)
    assert resp.status_code == 201, resp.text
    event = resp.json()
    if status != "draft":
        resp = event_client.patch(
            f"/api/v1/events/{event['id']}", json={"status": status}
        )
        assert resp.status_code == 200, resp.text
        event = resp.json()
    return event


def publish_event(event_client: ServiceClient, event_id: str) -> dict:
    resp = event_client.patch(
        f"/api/v1/events/{event_id}", json={"status": "published"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()
