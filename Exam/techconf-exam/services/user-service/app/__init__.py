"""app/__init__.py — Flask application factory."""
from __future__ import annotations

from flask import Flask, jsonify

from . import config
from .repository import make_repository
from .routes import bp, init_service
from .service import UserService


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


def create_app(storage_backend: str | None = None, data_dir: str | None = None) -> Flask:
    """Create the app and inject the configured repository into the service layer."""
    app = Flask(__name__)
    backend = storage_backend or config.STORAGE_BACKEND
    d_dir = data_dir or config.DATA_DIR
    repo = make_repository(backend, d_dir)
    init_service(UserService(repo))
    app.register_blueprint(bp)
    _register_error_handlers(app)
    return app
