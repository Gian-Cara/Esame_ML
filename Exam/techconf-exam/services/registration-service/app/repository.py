"""repository.py — storage abstraction for registration-service (memory/json/sqlite)."""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any


def _matches_filters(reg: dict, filters: dict) -> bool:
    for key, value in filters.items():
        if key in ("user_id", "event_id", "status"):
            if reg.get(key) != value:
                return False
    return True


def _paginate(items: list, page: int, page_size: int) -> tuple[list, int]:
    total = len(items)
    start = (page - 1) * page_size
    return items[start: start + page_size], total


class _BaseMixin:
    """Shared count/has helpers built on top of _all()."""

    def _all(self) -> list[dict]:
        raise NotImplementedError

    def count_confirmed(self, event_id: str) -> int:
        return sum(1 for r in self._all()
                   if r["event_id"] == event_id and r["status"] == "confirmed")

    def has_confirmed(self, user_id: str, event_id: str) -> bool:
        return any(r["user_id"] == user_id and r["event_id"] == event_id
                   and r["status"] == "confirmed" for r in self._all())


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class MemoryRegistrationRepository(_BaseMixin):
    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    def _all(self):
        return list(self._store.values())

    def create(self, reg: dict) -> dict:
        self._store[reg["id"]] = reg
        return reg

    def get(self, reg_id: str) -> dict | None:
        return self._store.get(reg_id)

    def update(self, reg_id: str, data: dict) -> dict | None:
        reg = self._store.get(reg_id)
        if reg is None:
            return None
        reg.update(data)
        return reg

    def delete(self, reg_id: str) -> bool:
        if reg_id in self._store:
            del self._store[reg_id]
            return True
        return False

    def list(self, filters: dict, page: int, page_size: int) -> tuple[list, int]:
        filtered = [r for r in self._store.values() if _matches_filters(r, filters)]
        return _paginate(filtered, page, page_size)


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

class JsonRegistrationRepository(_BaseMixin):
    def __init__(self, data_dir: str) -> None:
        os.makedirs(data_dir, exist_ok=True)
        self._path = os.path.join(data_dir, "registrations.json")
        if not os.path.exists(self._path):
            self._write({})

    def _read(self) -> dict:
        with open(self._path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, store: dict) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)

    def _all(self):
        return list(self._read().values())

    def create(self, reg: dict) -> dict:
        store = self._read()
        store[reg["id"]] = reg
        self._write(store)
        return reg

    def get(self, reg_id: str) -> dict | None:
        return self._read().get(reg_id)

    def update(self, reg_id: str, data: dict) -> dict | None:
        store = self._read()
        reg = store.get(reg_id)
        if reg is None:
            return None
        reg.update(data)
        self._write(store)
        return reg

    def delete(self, reg_id: str) -> bool:
        store = self._read()
        if reg_id in store:
            del store[reg_id]
            self._write(store)
            return True
        return False

    def list(self, filters: dict, page: int, page_size: int) -> tuple[list, int]:
        filtered = [r for r in self._read().values() if _matches_filters(r, filters)]
        return _paginate(filtered, page, page_size)


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------

_CREATE = """
CREATE TABLE IF NOT EXISTS registrations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_FIELDS = ("id", "user_id", "event_id", "amount", "status", "created_at", "updated_at")


class SqliteRegistrationRepository(_BaseMixin):
    def __init__(self, data_dir: str) -> None:
        os.makedirs(data_dir, exist_ok=True)
        self._db = os.path.join(data_dir, "registrations.db")
        with self._conn() as c:
            c.execute(_CREATE)

    def _conn(self):
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        return conn

    def _row(self, row) -> dict:
        d = dict(row)
        d["amount"] = float(d["amount"])
        return d

    def _all(self):
        with self._conn() as c:
            rows = c.execute("SELECT * FROM registrations").fetchall()
        return [self._row(r) for r in rows]

    def create(self, reg: dict) -> dict:
        with self._conn() as c:
            c.execute(
                f"INSERT INTO registrations ({','.join(_FIELDS)}) "
                f"VALUES ({','.join(':'+f for f in _FIELDS)})",
                reg,
            )
        return reg

    def get(self, reg_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM registrations WHERE id=?", (reg_id,)).fetchone()
        return self._row(row) if row else None

    def update(self, reg_id: str, data: dict) -> dict | None:
        reg = self.get(reg_id)
        if reg is None:
            return None
        reg.update(data)
        sets = ", ".join(f"{f}=:{f}" for f in _FIELDS if f != "id")
        with self._conn() as c:
            c.execute(f"UPDATE registrations SET {sets} WHERE id=:id", reg)
        return reg

    def delete(self, reg_id: str) -> bool:
        with self._conn() as c:
            cur = c.execute("DELETE FROM registrations WHERE id=?", (reg_id,))
        return cur.rowcount > 0

    def list(self, filters: dict, page: int, page_size: int) -> tuple[list, int]:
        filtered = [r for r in self._all() if _matches_filters(r, filters)]
        return _paginate(filtered, page, page_size)


def make_repository(backend: str, data_dir: str) -> Any:
    if backend == "json":
        return JsonRegistrationRepository(data_dir)
    if backend == "sqlite":
        return SqliteRegistrationRepository(data_dir)
    return MemoryRegistrationRepository()
