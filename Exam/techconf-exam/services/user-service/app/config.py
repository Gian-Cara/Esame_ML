"""
config.py — single source of truth for all environment variables.
No other module reads os.environ directly.
"""
import os

PORT: int = int(os.environ.get("PORT", 5001))
STORAGE_BACKEND: str = os.environ.get("STORAGE_BACKEND", "memory")  # memory | json | sqlite
DATA_DIR: str = os.environ.get("DATA_DIR", "./data")
