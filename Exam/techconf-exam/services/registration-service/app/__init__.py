"""app/__init__.py — Flask app factory for registration-service."""
from __future__ import annotations

from flask import Flask, jsonify

from . import config
from .clients import EventServiceClient, UserServiceClient
from .repository import make_repository
from .routes import bp, init_service
from .service import RegistrationService


def _register_error_handlers(app: Flask) -> None:
    def error(code: str, message: str, status: int):
        return jsonify({"error": {"code": code, "message": message, "details": {}}}), status

    @app.errorhandler(404)
    def not_found(_exc):
        return error("NOT_FOUND", "Resource not found.", 404)

    @app.errorhandler(405)
    def method_not_allowed(_exc):
        return error("METHOD_NOT_ALLOWED", "Method not allowed.", 405)

    @app.errorhandler(500)
    def internal_error(_exc):
        return error("INTERNAL_ERROR", "Internal server error.", 500)


def create_app(
    storage_backend: str | None = None,
    data_dir: str | None = None,
    user_service_url: str | None = None,
    event_service_url: str | None = None,
    user_client=None,
    event_client=None,
) -> Flask:
    app = Flask(__name__)
    repo = make_repository(storage_backend or config.STORAGE_BACKEND, data_dir or config.DATA_DIR)
    users = user_client or UserServiceClient(user_service_url or config.USER_SERVICE_URL)
    events = event_client or EventServiceClient(event_service_url or config.EVENT_SERVICE_URL)
    init_service(RegistrationService(repo, users, events))
    app.register_blueprint(bp)
    _register_error_handlers(app)
    return app
