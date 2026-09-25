"""routes.py — HTTP layer for registration-service."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .service import (
    ConflictError,
    DependencyUnavailableError,
    NotFoundError,
    RegistrationService,
    ValidationError,
)

bp = Blueprint("registrations", __name__)
_svc: RegistrationService | None = None


def init_service(service: RegistrationService) -> None:
    global _svc
    _svc = service


def _error(code: str, message: str, details: dict | None = None, status: int = 422):
    return jsonify({"error": {"code": code, "message": message, "details": details or {}}}), status


def _pagination():
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
    except (TypeError, ValueError):
        return None, None
    return page, page_size


@bp.route("/health")
def health():
    return jsonify({"status": "ok", "service": "registration-service"}), 200


@bp.route("/api/v1/registrations", methods=["POST"])
def create_registration():
    body = request.get_json(silent=True)
    if body is None:
        return _error("MALFORMED_JSON", "Request body is not valid JSON.", status=400)
    if not isinstance(body, dict):
        return _error("VALIDATION_ERROR", "Request body must be a JSON object.", status=422)
    try:
        reg = _svc.create_registration(body)
    except ValidationError as e:
        return _error(e.code, e.message, e.details, 422)
    except ConflictError as e:
        return _error(e.code, e.message, status=409)
    except DependencyUnavailableError:
        return _error("DEPENDENCY_UNAVAILABLE", "A dependency is unavailable.", status=503)
    resp = jsonify(reg)
    resp.status_code = 201
    resp.headers["Location"] = f"/api/v1/registrations/{reg['id']}"
    return resp


@bp.route("/api/v1/registrations", methods=["GET"])
def list_registrations():
    page, page_size = _pagination()
    if page is None:
        return _error("VALIDATION_ERROR", "Invalid pagination.", status=422)
    filters = {}
    for key in ("user_id", "event_id", "status"):
        if key in request.args:
            filters[key] = request.args[key]
    try:
        result = _svc.list_registrations(filters, page, page_size)
    except ValidationError as e:
        return _error(e.code, e.message, e.details, 422)
    return jsonify(result), 200


# stats must be registered before /<id> to avoid capture
@bp.route("/api/v1/registrations/stats", methods=["GET"])
def stats():
    event_id = request.args.get("event_id")
    if not event_id:
        return _error("VALIDATION_ERROR", "'event_id' is required.", status=422)
    try:
        result = _svc.stats(event_id)
    except NotFoundError:
        return _error("NOT_FOUND", f"Event '{event_id}' not found.", status=404)
    except DependencyUnavailableError:
        return _error("DEPENDENCY_UNAVAILABLE", "A dependency is unavailable.", status=503)
    return jsonify(result), 200


@bp.route("/api/v1/registrations/<reg_id>", methods=["GET"])
def get_registration(reg_id: str):
    try:
        reg = _svc.get_registration(reg_id)
    except NotFoundError:
        return _error("NOT_FOUND", f"Registration '{reg_id}' not found.", status=404)
    return jsonify(reg), 200


@bp.route("/api/v1/registrations/<reg_id>", methods=["PUT"])
def put_not_allowed(reg_id: str):
    return _error("METHOD_NOT_ALLOWED", "PUT is not allowed on registrations.", status=405)


@bp.route("/api/v1/registrations/<reg_id>", methods=["PATCH"])
def patch_registration(reg_id: str):
    body = request.get_json(silent=True)
    if body is None:
        return _error("MALFORMED_JSON", "Request body is not valid JSON.", status=400)
    if not isinstance(body, dict):
        return _error("VALIDATION_ERROR", "Request body must be a JSON object.", status=422)
    try:
        reg = _svc.update_status(reg_id, body)
    except NotFoundError:
        return _error("NOT_FOUND", f"Registration '{reg_id}' not found.", status=404)
    except ValidationError as e:
        return _error(e.code, e.message, e.details, 422)
    return jsonify(reg), 200


@bp.route("/api/v1/registrations/<reg_id>", methods=["DELETE"])
def delete_registration(reg_id: str):
    try:
        _svc.delete_registration(reg_id)
    except NotFoundError:
        return _error("NOT_FOUND", f"Registration '{reg_id}' not found.", status=404)
    return "", 204
