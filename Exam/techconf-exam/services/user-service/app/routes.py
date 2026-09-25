"""
routes.py — HTTP layer for user-service.

Parses requests, delegates to UserService, serialises responses.
No business logic lives here.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .service import ConflictError, NotFoundError, UserService, ValidationError

bp = Blueprint("users", __name__)

# Will be set by create_app()
_svc: UserService | None = None


def init_service(service: UserService) -> None:
    global _svc
    _svc = service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error(code: str, message: str, details: dict | None = None, status: int = 422):
    body = {"error": {"code": code, "message": message, "details": details or {}}}
    return jsonify(body), status


def _get_pagination() -> tuple[int, int] | tuple[None, None]:
    """Parse page / page_size from query string. Returns (None, None) on error."""
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
    except (TypeError, ValueError):
        return None, None
    return page, page_size


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@bp.route("/health")
def health():
    return jsonify({"status": "ok", "service": "user-service"}), 200


# ---------------------------------------------------------------------------
# POST /api/v1/users
# ---------------------------------------------------------------------------

@bp.route("/api/v1/users", methods=["POST"])
def create_user():
    body = request.get_json(silent=True)
    if body is None:
        return _error("MALFORMED_JSON", "Request body is not valid JSON.", status=400)
    try:
        user = _svc.create_user(body)
    except ValidationError as e:
        return _error("VALIDATION_ERROR", e.message, e.details, 422)
    except ConflictError as e:
        return _error(e.code, e.message, status=409)
    resp = jsonify(user)
    resp.status_code = 201
    resp.headers["Location"] = f"/api/v1/users/{user['id']}"
    return resp


# ---------------------------------------------------------------------------
# GET /api/v1/users
# ---------------------------------------------------------------------------

@bp.route("/api/v1/users", methods=["GET"])
def list_users():
    page, page_size = _get_pagination()
    if page is None:
        return _error("VALIDATION_ERROR", "'page' and 'page_size' must be integers.", status=422)

    filters = {}
    if "role" in request.args:
        filters["role"] = request.args["role"]
    if "email" in request.args:
        filters["email"] = request.args["email"]

    try:
        result = _svc.list_users(filters, page, page_size)
    except ValidationError as e:
        return _error("VALIDATION_ERROR", e.message, e.details, 422)
    return jsonify(result), 200


# ---------------------------------------------------------------------------
# GET /api/v1/users/<id>
# ---------------------------------------------------------------------------

@bp.route("/api/v1/users/<user_id>", methods=["GET"])
def get_user(user_id: str):
    try:
        user = _svc.get_user(user_id)
    except NotFoundError:
        return _error("NOT_FOUND", f"User '{user_id}' not found.", status=404)
    return jsonify(user), 200


# ---------------------------------------------------------------------------
# PUT /api/v1/users/<id>
# ---------------------------------------------------------------------------

@bp.route("/api/v1/users/<user_id>", methods=["PUT"])
def replace_user(user_id: str):
    body = request.get_json(silent=True)
    if body is None:
        return _error("MALFORMED_JSON", "Request body is not valid JSON.", status=400)
    try:
        user = _svc.replace_user(user_id, body)
    except NotFoundError:
        return _error("NOT_FOUND", f"User '{user_id}' not found.", status=404)
    except ValidationError as e:
        return _error("VALIDATION_ERROR", e.message, e.details, 422)
    except ConflictError as e:
        return _error(e.code, e.message, status=409)
    return jsonify(user), 200


# ---------------------------------------------------------------------------
# PATCH /api/v1/users/<id>
# ---------------------------------------------------------------------------

@bp.route("/api/v1/users/<user_id>", methods=["PATCH"])
def update_user(user_id: str):
    body = request.get_json(silent=True)
    if body is None:
        return _error("MALFORMED_JSON", "Request body is not valid JSON.", status=400)
    try:
        user = _svc.update_user(user_id, body)
    except NotFoundError:
        return _error("NOT_FOUND", f"User '{user_id}' not found.", status=404)
    except ValidationError as e:
        return _error("VALIDATION_ERROR", e.message, e.details, 422)
    except ConflictError as e:
        return _error(e.code, e.message, status=409)
    return jsonify(user), 200


# ---------------------------------------------------------------------------
# DELETE /api/v1/users/<id>
# ---------------------------------------------------------------------------

@bp.route("/api/v1/users/<user_id>", methods=["DELETE"])
def delete_user(user_id: str):
    try:
        _svc.delete_user(user_id)
    except NotFoundError:
        return _error("NOT_FOUND", f"User '{user_id}' not found.", status=404)
    return "", 204
