"""repository.py — storage abstraction for event-service (memory/json/sqlite)."""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any


def _matches_filters(event: dict, filters: dict) -> bool:
    for key, value in filters.items():
        if key == "status":
            if event.get("status") != value:
                return False
        elif key == "city":
            if event.get("city", "").lower() != value.lower():
                return False
    return True


def _paginate(items: list, page: int, page_size: int) -> tuple[list, int]:
    total = len(items)
    start = (page - 1) * page_size
    return items[start: start + page_size], total


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class MemoryEventRepository:
    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    def create(self, event: dict) -> dict:
        self._store[event["id"]] = event
        return event

    def get(self, event_id: str) -> dict | None:
        return self._store.get(event_id)

    def update(self, event_id: str, data: dict) -> dict | None:
        event = self._store.get(event_id)
        if event is None:
            return None
        event.update(data)
        return event

    def delete(self, event_id: str) -> bool:
        if event_id in self._store:
            del self._store[event_id]
            return True
        return False

    def list(self, filters: dict, page: int, page_size: int) -> tuple[list, int]:
        filtered = [e for e in self._store.values() if _matches_filters(e, filters)]
        return _paginate(filtered, page, page_size)


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

class JsonEventRepository:
    def __init__(self, data_dir: str) -> None:
        os.makedirs(data_dir, exist_ok=True)
        self._path = os.path.join(data_dir, "events.json")
        if not os.path.exists(self._path):
            self._write({})

    def _read(self) -> dict:
        with open(self._path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, store: dict) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)

    def create(self, event: dict) -> dict:
        store = self._read()
        store[event["id"]] = event
        self._write(store)
        return event

    def get(self, event_id: str) -> dict | None:
        return self._read().get(event_id)

    def update(self, event_id: str, data: dict) -> dict | None:
        store = self._read()
        event = store.get(event_id)
        if event is None:
            return None
        event.update(data)
        self._write(store)
        return event

    def delete(self, event_id: str) -> bool:
        store = self._read()
        if event_id in store:
            del store[event_id]
            self._write(store)
            return True
        return False

    def list(self, filters: dict, page: int, page_size: int) -> tuple[list, int]:
        filtered = [e for e in self._read().values() if _matches_filters(e, filters)]
        return _paginate(filtered, page, page_size)


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------

_CREATE = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    organizer_id TEXT NOT NULL,
    venue TEXT NOT NULL,
    city TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    capacity INTEGER NOT NULL,
    price REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_FIELDS = ("id", "title", "description", "organizer_id", "venue", "city",
           "start_date", "end_date", "capacity", "price", "status",
           "created_at", "updated_at")


class SqliteEventRepository:
    def __init__(self, data_dir: str) -> None:
        os.makedirs(data_dir, exist_ok=True)
        self._db = os.path.join(data_dir, "events.db")
        with self._conn() as c:
            c.execute(_CREATE)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        return conn

    def _row(self, row) -> dict:
        d = dict(row)
        d["price"] = float(d["price"])
        d["capacity"] = int(d["capacity"])
        return d

    def create(self, event: dict) -> dict:
        with self._conn() as c:
            c.execute(
                f"INSERT INTO events ({','.join(_FIELDS)}) VALUES ({','.join(':'+f for f in _FIELDS)})",
                event,
            )
        return event

    def get(self, event_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return self._row(row) if row else None

    def update(self, event_id: str, data: dict) -> dict | None:
        event = self.get(event_id)
        if event is None:
            return None
        event.update(data)
        sets = ", ".join(f"{f}=:{f}" for f in _FIELDS if f != "id")
        with self._conn() as c:
            c.execute(f"UPDATE events SET {sets} WHERE id=:id", event)
        return event

    def delete(self, event_id: str) -> bool:
        with self._conn() as c:
            cur = c.execute("DELETE FROM events WHERE id=?", (event_id,))
        return cur.rowcount > 0

    def list(self, filters: dict, page: int, page_size: int) -> tuple[list, int]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM events").fetchall()
        all_events = [self._row(r) for r in rows]
        filtered = [e for e in all_events if _matches_filters(e, filters)]
        return _paginate(filtered, page, page_size)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_repository(backend: str, data_dir: str) -> Any:
    if backend == "json":
        return JsonEventRepository(data_dir)
    if backend == "sqlite":
        return SqliteEventRepository(data_dir)
    return MemoryEventRepository()
