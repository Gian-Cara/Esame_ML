"""
app/__init__.py — Flask application factory.
"""
from __future__ import annotations

from flask import Flask

from . import config
from .repository import make_repository
from .routes import bp, init_service
from .service import UserService


def create_app(storage_backend: str | None = None, data_dir: str | None = None) -> Flask:
    """
    Create and configure the Flask application.

    *storage_backend* and *data_dir* can be overridden for testing;
    if omitted they are read from config (environment variables).
    """
    app = Flask(__name__)

    backend = storage_backend or config.STORAGE_BACKEND
    d_dir = data_dir or config.DATA_DIR

    repo = make_repository(backend, d_dir)
    svc = UserService(repo)
    init_service(svc)

    app.register_blueprint(bp)
    return app
