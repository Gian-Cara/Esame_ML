"""routes.py — HTTP layer for event-service."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .service import (
    DependencyUnavailableError,
    EventService,
    InvalidStatusTransitionError,
    NotFoundError,
    ValidationError,
)

bp = Blueprint("events", __name__)
_svc: EventService | None = None


def init_service(service: EventService) -> None:
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
    return jsonify({"status": "ok", "service": "event-service"}), 200


@bp.route("/api/v1/events", methods=["POST"])
def create_event():
    body = request.get_json(silent=True)
    if body is None:
        return _error("MALFORMED_JSON", "Request body is not valid JSON.", status=400)
    try:
        event = _svc.create_event(body)
    except ValidationError as e:
        code = "REFERENCE_NOT_FOUND" if "REFERENCE_NOT_FOUND" in str(e.details) else \
               "INVALID_ORGANIZER" if "INVALID_ORGANIZER" in str(e.details) else "VALIDATION_ERROR"
        return _error(code, e.message, e.details, 422)
    except DependencyUnavailableError:
        return _error("DEPENDENCY_UNAVAILABLE", "user-service is unavailable.", status=503)
    resp = jsonify(event)
    resp.status_code = 201
    resp.headers["Location"] = f"/api/v1/events/{event['id']}"
    return resp


@bp.route("/api/v1/events", methods=["GET"])
def list_events():
    page, page_size = _pagination()
    if page is None:
        return _error("VALIDATION_ERROR", "Invalid pagination parameters.", status=422)
    filters = {}
    if "status" in request.args:
        filters["status"] = request.args["status"]
    if "city" in request.args:
        filters["city"] = request.args["city"]
    try:
        result = _svc.list_events(filters, page, page_size)
    except ValidationError as e:
        return _error("VALIDATION_ERROR", e.message, e.details, 422)
    return jsonify(result), 200


@bp.route("/api/v1/events/<event_id>", methods=["GET"])
def get_event(event_id: str):
    try:
        event = _svc.get_event(event_id)
    except NotFoundError:
        return _error("NOT_FOUND", f"Event '{event_id}' not found.", status=404)
    return jsonify(event), 200


@bp.route("/api/v1/events/<event_id>", methods=["PUT"])
def replace_event(event_id: str):
    body = request.get_json(silent=True)
    if body is None:
        return _error("MALFORMED_JSON", "Request body is not valid JSON.", status=400)
    try:
        event = _svc.replace_event(event_id, body)
    except NotFoundError:
        return _error("NOT_FOUND", f"Event '{event_id}' not found.", status=404)
    except InvalidStatusTransitionError as e:
        return _error("INVALID_STATUS_TRANSITION", e.message, status=422)
    except ValidationError as e:
        code = "REFERENCE_NOT_FOUND" if "REFERENCE_NOT_FOUND" in str(e.details) else \
               "INVALID_ORGANIZER" if "INVALID_ORGANIZER" in str(e.details) else "VALIDATION_ERROR"
        return _error(code, e.message, e.details, 422)
    except DependencyUnavailableError:
        return _error("DEPENDENCY_UNAVAILABLE", "user-service is unavailable.", status=503)
    return jsonify(event), 200


@bp.route("/api/v1/events/<event_id>", methods=["PATCH"])
def update_event(event_id: str):
    body = request.get_json(silent=True)
    if body is None:
        return _error("MALFORMED_JSON", "Request body is not valid JSON.", status=400)
    try:
        event = _svc.update_event(event_id, body)
    except NotFoundError:
        return _error("NOT_FOUND", f"Event '{event_id}' not found.", status=404)
    except InvalidStatusTransitionError as e:
        return _error("INVALID_STATUS_TRANSITION", e.message, status=422)
    except ValidationError as e:
        code = "REFERENCE_NOT_FOUND" if "REFERENCE_NOT_FOUND" in str(e.details) else \
               "INVALID_ORGANIZER" if "INVALID_ORGANIZER" in str(e.details) else "VALIDATION_ERROR"
        return _error(code, e.message, e.details, 422)
    except DependencyUnavailableError:
        return _error("DEPENDENCY_UNAVAILABLE", "user-service is unavailable.", status=503)
    return jsonify(event), 200


@bp.route("/api/v1/events/<event_id>", methods=["DELETE"])
def delete_event(event_id: str):
    try:
        _svc.delete_event(event_id)
    except NotFoundError:
        return _error("NOT_FOUND", f"Event '{event_id}' not found.", status=404)
    return "", 204
