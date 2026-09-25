"""app/__init__.py — Flask app factory for registration-service."""
from __future__ import annotations

from flask import Flask

from . import config
from .clients import EventServiceClient, UserServiceClient
from .repository import make_repository
from .routes import bp, init_service
from .service import RegistrationService


def create_app(
    storage_backend: str | None = None,
    data_dir: str | None = None,
    user_service_url: str | None = None,
    event_service_url: str | None = None,
    user_client=None,
    event_client=None,
) -> Flask:
    app = Flask(__name__)
    backend = storage_backend or config.STORAGE_BACKEND
    d_dir = data_dir or config.DATA_DIR
    repo = make_repository(backend, d_dir)
    u_client = user_client or UserServiceClient(user_service_url or config.USER_SERVICE_URL)
    e_client = event_client or EventServiceClient(event_service_url or config.EVENT_SERVICE_URL)
    svc = RegistrationService(repo, u_client, e_client)
    init_service(svc)
    app.register_blueprint(bp)
    return app
