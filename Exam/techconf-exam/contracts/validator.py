"""Contract validation helper for the TechConf acceptance suite.

This module is part of the *non-modifiable* template. It loads the OpenAPI 3.0
contracts under ``contracts/openapi/`` and validates an HTTP response against the
schema declared for a given ``(service, method, path)`` operation.

Public API
----------
    assert_matches_contract(service, method, path, response)

``response`` may be any object exposing:
    * ``status_code`` (int)
    * ``headers`` (mapping)
    * ``json()``  -> parsed body  (as in ``requests.Response``)

or a plain ``dict`` shaped as ``{"status_code": int, "headers": {...}, "json": <body>}``.

The helper is intentionally dependency-light: it only needs ``PyYAML`` and
``jsonschema``. OpenAPI 3.0 ``nullable`` is translated to JSON-Schema-compatible
type unions before validation.
"""

from __future__ import annotations

import copy
import functools
import re
from pathlib import Path
from typing import Any, Mapping

import yaml
from jsonschema import Draft7Validator
from jsonschema import exceptions as js_exceptions

# --------------------------------------------------------------------------- #
# Contract loading
# --------------------------------------------------------------------------- #

_CONTRACTS_DIR = Path(__file__).resolve().parent / "openapi"

_SERVICE_FILES = {
    "user": "user-service.yaml",
    "user-service": "user-service.yaml",
    "event": "event-service.yaml",
    "event-service": "event-service.yaml",
    "registration": "registration-service.yaml",
    "registration-service": "registration-service.yaml",
    "feedback": "feedback-service.yaml",
    "feedback-service": "feedback-service.yaml",
    "notification": "notification-service.yaml",
    "notification-service": "notification-service.yaml",
}


class ContractError(AssertionError):
    """Raised when a response does not match its OpenAPI contract."""


@functools.lru_cache(maxsize=None)
def _load_spec(service: str) -> dict[str, Any]:
    key = service.lower()
    if key not in _SERVICE_FILES:
        raise ContractError(
            f"Unknown service '{service}'. "
            f"Known services: {sorted(set(_SERVICE_FILES))}"
        )
    path = _CONTRACTS_DIR / _SERVICE_FILES[key]
    if not path.is_file():
        raise ContractError(f"Contract file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# --------------------------------------------------------------------------- #
# Path matching (templated paths like /api/v1/users/{id})
# --------------------------------------------------------------------------- #


def _normalize_path(path: str) -> str:
    """Strip query string and trailing slash (except root)."""
    path = path.split("?", 1)[0]
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path


def _path_regex(template: str) -> re.Pattern[str]:
    # Replace {param} with a non-slash-matching group.
    escaped = re.escape(template)
    escaped = re.sub(r"\\\{[^/}]+\\\}", r"[^/]+", escaped)
    return re.compile(f"^{escaped}$")


def _find_operation(
    spec: Mapping[str, Any], method: str, path: str
) -> dict[str, Any]:
    method = method.lower()
    target = _normalize_path(path)
    paths: dict[str, Any] = spec.get("paths", {})

    # Prefer an exact literal match, then fall back to templated matching.
    candidates: list[str] = []
    if target in paths:
        candidates.append(target)
    for template in paths:
        if template == target:
            continue
        if "{" in template and _path_regex(_normalize_path(template)).match(target):
            candidates.append(template)

    for template in candidates:
        operations = paths.get(template, {})
        if method in operations:
            return operations[method]

    raise ContractError(
        f"No operation '{method.upper()} {target}' found in contract."
    )


# --------------------------------------------------------------------------- #
# $ref resolution + OpenAPI 3.0 -> JSON Schema (Draft 7) adaptation
# --------------------------------------------------------------------------- #


def _resolve_refs(node: Any, root: Mapping[str, Any], _seen: frozenset[str] = frozenset()) -> Any:
    """Recursively inline local ``$ref`` pointers and adapt ``nullable``."""
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"]
            if not ref.startswith("#/"):
                raise ContractError(f"Only local $ref supported, got: {ref}")
            if ref in _seen:
                # Cyclic ref guard — return a permissive schema.
                return {}
            target: Any = root
            for part in ref.lstrip("#/").split("/"):
                target = target[part]
            return _resolve_refs(target, root, _seen | {ref})

        resolved = {k: _resolve_refs(v, root, _seen) for k, v in node.items()}

        # Adapt OpenAPI 3.0 `nullable: true` to a Draft-7-compatible type union.
        if resolved.pop("nullable", False):
            if "type" in resolved and isinstance(resolved["type"], str):
                resolved["type"] = [resolved["type"], "null"]
            elif "enum" in resolved and None not in resolved["enum"]:
                resolved["enum"] = list(resolved["enum"]) + [None]
            else:
                # Wrap in anyOf allowing null.
                inner = {k: resolved[k] for k in list(resolved) if k not in ("description",)}
                resolved = {"anyOf": [inner, {"type": "null"}]}
        return resolved

    if isinstance(node, list):
        return [_resolve_refs(item, root, _seen) for item in node]

    return node


def _response_schema(
    operation: Mapping[str, Any], root: Mapping[str, Any], status_code: int
) -> dict[str, Any] | None:
    responses = operation.get("responses", {})
    entry = responses.get(str(status_code)) or responses.get(status_code)
    if entry is None:
        raise ContractError(
            f"Status {status_code} is not declared for this operation. "
            f"Declared: {sorted(responses)}"
        )
    entry = _resolve_refs(entry, root)
    content = entry.get("content", {})
    json_content = content.get("application/json")
    if not json_content or "schema" not in json_content:
        # No body expected (e.g. 204). A body-less response is valid.
        return None
    return json_content["schema"]


# --------------------------------------------------------------------------- #
# Response adapter
# --------------------------------------------------------------------------- #


def _extract(response: Any) -> tuple[int, dict[str, Any], Any]:
    if isinstance(response, dict) and "status_code" in response:
        status = int(response["status_code"])
        headers = dict(response.get("headers", {}) or {})
        body = response.get("json", None)
        return status, headers, body

    status = int(getattr(response, "status_code"))
    headers = dict(getattr(response, "headers", {}) or {})
    body: Any = None
    text = getattr(response, "text", "") or ""
    if text.strip():
        try:
            body = response.json()
        except Exception as exc:  # noqa: BLE001 - surface as contract failure
            raise ContractError(f"Response body is not valid JSON: {exc}") from exc
    return status, headers, body


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def assert_matches_contract(
    service: str,
    method: str,
    path: str,
    response: Any,
) -> None:
    """Assert that ``response`` conforms to the OpenAPI contract of ``service``.

    Parameters
    ----------
    service:
        Service name or file stem, e.g. ``"user"`` or ``"user-service"``.
    method:
        HTTP method, e.g. ``"POST"`` (case-insensitive).
    path:
        Request path, e.g. ``"/api/v1/users/123"``. A query string is ignored.
    response:
        A ``requests.Response``-like object or a dict with
        ``status_code`` / ``headers`` / ``json`` keys.

    Raises
    ------
    ContractError
        If the status code is not declared, or the body violates the schema.
    """
    spec = _load_spec(service)
    operation = _find_operation(spec, method, path)
    status, _headers, body = _extract(response)

    schema = _response_schema(operation, spec, status)

    if schema is None:
        # No JSON body expected for this status; nothing more to validate.
        return

    validator = Draft7Validator(copy.deepcopy(schema))
    errors = sorted(validator.iter_errors(body), key=lambda e: list(e.path))
    if errors:
        details = "\n".join(_format_error(e) for e in errors)
        raise ContractError(
            f"{method.upper()} {path} -> {status} does not match "
            f"{service} contract:\n{details}"
        )


def _format_error(error: js_exceptions.ValidationError) -> str:
    location = "/".join(str(p) for p in error.absolute_path) or "<root>"
    return f"  - at '{location}': {error.message}"
