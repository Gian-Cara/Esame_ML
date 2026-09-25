"""
repository.py — storage abstraction for user-service.

Exposes a single UserRepository class whose backend is selected by the
STORAGE_BACKEND config value: 'memory' | 'json' | 'sqlite'.
Business logic never touches storage directly.
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _matches_filters(user: dict, filters: dict) -> bool:
    """Return True when *user* satisfies all key/value pairs in *filters*."""
    for key, value in filters.items():
        if key == "email":
            if user.get("email", "").lower() != value.lower():
                return False
        elif key == "role":
            if user.get("role") != value:
                return False
    return True


def _paginate(items: list, page: int, page_size: int) -> tuple[list, int]:
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], total


# ---------------------------------------------------------------------------
# Memory backend
# ---------------------------------------------------------------------------

class MemoryUserRepository:
    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    def create(self, user: dict) -> dict:
        self._store[user["id"]] = user
        return user

    def get(self, user_id: str) -> dict | None:
        return self._store.get(user_id)

    def update(self, user_id: str, data: dict) -> dict | None:
        user = self._store.get(user_id)
        if user is None:
            return None
        user.update(data)
        return user

    def delete(self, user_id: str) -> bool:
        if user_id in self._store:
            del self._store[user_id]
            return True
        return False

    def list(self, filters: dict, page: int, page_size: int) -> tuple[list, int]:
        all_users = [u for u in self._store.values() if _matches_filters(u, filters)]
        return _paginate(all_users, page, page_size)

    def email_exists(self, email: str, exclude_id: str | None = None) -> bool:
        for user in self._store.values():
            if user["email"].lower() == email.lower():
                if exclude_id is None or user["id"] != exclude_id:
                    return True
        return False


# ---------------------------------------------------------------------------
# JSON backend
# ---------------------------------------------------------------------------

class JsonUserRepository:
    def __init__(self, data_dir: str) -> None:
        os.makedirs(data_dir, exist_ok=True)
        self._path = os.path.join(data_dir, "users.json")
        if not os.path.exists(self._path):
            self._write({})

    def _read(self) -> dict[str, dict]:
        with open(self._path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, store: dict) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)

    def create(self, user: dict) -> dict:
        store = self._read()
        store[user["id"]] = user
        self._write(store)
        return user

    def get(self, user_id: str) -> dict | None:
        return self._read().get(user_id)

    def update(self, user_id: str, data: dict) -> dict | None:
        store = self._read()
        user = store.get(user_id)
        if user is None:
            return None
        user.update(data)
        self._write(store)
        return user

    def delete(self, user_id: str) -> bool:
        store = self._read()
        if user_id in store:
            del store[user_id]
            self._write(store)
            return True
        return False

    def list(self, filters: dict, page: int, page_size: int) -> tuple[list, int]:
        all_users = [u for u in self._read().values() if _matches_filters(u, filters)]
        return _paginate(all_users, page, page_size)

    def email_exists(self, email: str, exclude_id: str | None = None) -> bool:
        for user in self._read().values():
            if user["email"].lower() == email.lower():
                if exclude_id is None or user["id"] != exclude_id:
                    return True
        return False


# ---------------------------------------------------------------------------
# SQLite backend
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id         TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name  TEXT NOT NULL,
    email      TEXT NOT NULL,
    company    TEXT,
    role       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class SqliteUserRepository:
    def __init__(self, data_dir: str) -> None:
        os.makedirs(data_dir, exist_ok=True)
        self._db_path = os.path.join(data_dir, "users.db")
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create(self, user: dict) -> dict:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO users (id, first_name, last_name, email, company, role, created_at, updated_at) "
                "VALUES (:id, :first_name, :last_name, :email, :company, :role, :created_at, :updated_at)",
                user,
            )
        return user

    def get(self, user_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_dict(row) if row else None

    def update(self, user_id: str, data: dict) -> dict | None:
        user = self.get(user_id)
        if user is None:
            return None
        user.update(data)
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET first_name=:first_name, last_name=:last_name, email=:email, "
                "company=:company, role=:role, updated_at=:updated_at WHERE id=:id",
                user,
            )
        return user

    def delete(self, user_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return cursor.rowcount > 0

    def list(self, filters: dict, page: int, page_size: int) -> tuple[list, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM users").fetchall()
        all_users = [_row_to_dict(r) for r in rows]
        filtered = [u for u in all_users if _matches_filters(u, filters)]
        return _paginate(filtered, page, page_size)

    def email_exists(self, email: str, exclude_id: str | None = None) -> bool:
        with self._connect() as conn:
            if exclude_id:
                row = conn.execute(
                    "SELECT id FROM users WHERE LOWER(email) = LOWER(?) AND id != ?",
                    (email, exclude_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)
                ).fetchone()
        return row is not None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_repository(backend: str, data_dir: str) -> Any:
    """Return the correct repository implementation for *backend*."""
    if backend == "json":
        return JsonUserRepository(data_dir)
    if backend == "sqlite":
        return SqliteUserRepository(data_dir)
    return MemoryUserRepository()
