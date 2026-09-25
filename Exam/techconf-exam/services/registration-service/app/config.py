"""config.py — single source of all env vars for registration-service."""
import os

PORT: int = int(os.environ.get("PORT", 5003))
STORAGE_BACKEND: str = os.environ.get("STORAGE_BACKEND", "memory")
DATA_DIR: str = os.environ.get("DATA_DIR", "./data")
USER_SERVICE_URL: str = os.environ.get("USER_SERVICE_URL", "http://localhost:5001")
EVENT_SERVICE_URL: str = os.environ.get("EVENT_SERVICE_URL", "http://localhost:5002")
