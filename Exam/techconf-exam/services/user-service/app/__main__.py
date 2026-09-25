"""
app/__main__.py — entrypoint for user-service.

Usage (from services/user-service/):
    python -m app
"""
from . import create_app
from .config import PORT

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
