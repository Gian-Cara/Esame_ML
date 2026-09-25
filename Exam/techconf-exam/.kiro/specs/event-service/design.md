# Design — event-service

**Contract reference:** `contracts/openapi/event-service.yaml`
**Requirements reference:** `.kiro/specs/event-service/requirements.md`

---

## 1. Component overview

```
services/event-service/
├── app/
│   ├── __init__.py       # Flask app factory
│   ├── __main__.py       # Entrypoint
│   ├── config.py         # ENV vars: PORT, STORAGE_BACKEND, DATA_DIR, USER_SERVICE_URL
│   ├── routes.py         # HTTP layer
│   ├── service.py        # Business rules (REQ-EVT-B*)
│   ├── repository.py     # memory / json / sqlite backends
│   └── clients.py        # HTTP call to user-service
├── tests/
│   ├── unit/             # pytest + responses mock, all 3 backends, ≥80% coverage
│   └── integration/      # starts real user-service, verifies +/422/503 cases
├── requirements.txt
└── data/
```

---

## 2. Data model

| Field | Type | Notes |
|---|---|---|
| `id` | UUID v4 | Server-generated |
| `title` | string | 3–120 chars |
| `description` | string\|null | max 2000 |
| `organizer_id` | UUID | Must exist in user-service with role=organizer |
| `venue` | string | max 100 |
| `city` | string | max 60 |
| `start_date` | YYYY-MM-DD | |
| `end_date` | YYYY-MM-DD | ≥ start_date |
| `capacity` | int | 1–10000 |
| `price` | decimal | ≥ 0, stored as float, serialised with 2 decimal places |
| `status` | enum | draft\|published\|cancelled, default draft |
| `created_at` | ISO 8601 UTC | Immutable after creation |
| `updated_at` | ISO 8601 UTC | Updated on every write |

---

## 3. clients.py — user-service integration

```python
class UserServiceClient:
    def get_user(self, user_id: str) -> dict | None:
        # GET USER_SERVICE_URL/api/v1/users/{user_id}, timeout=2s
        # Returns dict on 200, None on 404
        # Raises DependencyError on timeout/connection error/5xx
```

Used exclusively in `service.py`. In unit tests, mocked with `responses` library.

---

## 4. Business rules (service.py)

| Rule | Implementation |
|---|---|
| REQ-EVT-B01 | Call `client.get_user(organizer_id)` → None → 422 `REFERENCE_NOT_FOUND` |
| REQ-EVT-B02 | Returned user `.role != "organizer"` → 422 `INVALID_ORGANIZER` |
| REQ-EVT-B03 | `end_date < start_date` → 422 `VALIDATION_ERROR` |
| REQ-EVT-B04 | Validate transition via `ALLOWED_TRANSITIONS` set; invalid → 422 `INVALID_STATUS_TRANSITION` |
| REQ-EVT-B05 | `DependencyError` from client → 503 `DEPENDENCY_UNAVAILABLE` |
| REQ-EVT-B06 | Filter by `status` and `city` (case-insensitive) in repository.list() |

**Status transition table:**
```python
ALLOWED_TRANSITIONS = {
    ("draft", "published"),
    ("draft", "cancelled"),
    ("published", "cancelled"),
}
```

---

## 5. Repository interface

Same pattern as user-service:
```python
def create(event) -> dict
def get(event_id) -> dict | None
def update(event_id, data) -> dict | None
def delete(event_id) -> bool
def list(filters, page, page_size) -> tuple[list, int]
```

Three backends: `MemoryEventRepository`, `JsonEventRepository`, `SqliteEventRepository`.

SQLite schema:
```sql
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY, title TEXT, description TEXT,
    organizer_id TEXT, venue TEXT, city TEXT,
    start_date TEXT, end_date TEXT,
    capacity INTEGER, price REAL,
    status TEXT, created_at TEXT, updated_at TEXT
)
```

---

## 6. Configuration (config.py)

```python
PORT             = int(os.environ.get("PORT", 5002))
STORAGE_BACKEND  = os.environ.get("STORAGE_BACKEND", "memory")
DATA_DIR         = os.environ.get("DATA_DIR", "./data")
USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://localhost:5001")
```

---

## 7. Testing strategy

### Unit tests
- Mock user-service with `responses` library (success, 404, timeout).
- Test all three backends with `tmp_path`.
- At least 1 contract-validation test per endpoint with `assert_matches_contract`.
- Coverage ≥ 80%.

### Integration tests (`tests/integration/`)
- Launch user-service as subprocess on a free port.
- Test: create event with valid organizer (201), invalid organizer_id (422), user-service down (503).
- Teardown: kill subprocess.
