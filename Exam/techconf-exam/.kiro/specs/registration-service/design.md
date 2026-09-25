# Design — registration-service

**Contract reference:** `contracts/openapi/registration-service.yaml`
**Requirements reference:** `.kiro/specs/registration-service/requirements.md`

---

## 1. Component overview

```
services/registration-service/
├── app/
│   ├── __init__.py       # Flask app factory
│   ├── __main__.py       # Entrypoint
│   ├── config.py         # PORT, STORAGE_BACKEND, DATA_DIR, USER_SERVICE_URL, EVENT_SERVICE_URL
│   ├── routes.py         # HTTP layer (incl. PUT -> 405, /stats)
│   ├── service.py        # Business rules REQ-REG-B01..B10
│   ├── repository.py     # memory / json / sqlite
│   └── clients.py        # UserServiceClient + EventServiceClient
├── tests/
│   ├── unit/
│   └── integration/
├── requirements.txt
└── data/
```

---

## 2. Data model

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Server-generated |
| `user_id` | UUID | Must exist in user-service |
| `event_id` | UUID | Must exist in event-service, status=published |
| `amount` | decimal | Read-only, copied from event.price |
| `status` | enum | confirmed\|cancelled, always confirmed on create |
| `created_at` / `updated_at` | ISO 8601 UTC | |

---

## 3. clients.py

Two clients, both timeout 2s:
```python
class UserServiceClient:
    def get_user(self, user_id) -> dict | None   # 200->dict, 404->None, else DependencyError

class EventServiceClient:
    def get_event(self, event_id) -> dict | None  # 200->dict, 404->None, else DependencyError
```

Mocked with `responses` in unit tests.

---

## 4. Business rules (service.py)

| Rule | Implementation |
|---|---|
| REQ-REG-B01 | `user_client.get_user()` None → 422 `REFERENCE_NOT_FOUND` |
| REQ-REG-B02 | `event_client.get_event()` None → 422 `REFERENCE_NOT_FOUND` |
| REQ-REG-B03 | event status != published → 422 `EVENT_NOT_OPEN` |
| REQ-REG-B04 | count confirmed for (user,event) > 0 → 409 `ALREADY_REGISTERED` |
| REQ-REG-B05 | confirmed count for event >= capacity → 409 `EVENT_FULL` |
| REQ-REG-B06 | amount = event.price |
| REQ-REG-B07 | transition confirmed→cancelled ok; cancelled→confirmed → 422 `INVALID_STATUS_TRANSITION` |
| REQ-REG-B08 | stats: count confirmed, available = capacity - confirmed; event missing → 404 |
| REQ-REG-B09 | DependencyError → 503 `DEPENDENCY_UNAVAILABLE` |

Order of checks in create: user exists → event exists → event published → not already registered → capacity available.

---

## 5. Repository interface

```python
def create(reg) -> dict
def get(reg_id) -> dict | None
def update(reg_id, data) -> dict | None
def delete(reg_id) -> bool
def list(filters, page, page_size) -> tuple[list, int]
def count_confirmed(event_id) -> int
def has_confirmed(user_id, event_id) -> bool
```

Three backends: Memory, Json, Sqlite.

SQLite schema:
```sql
CREATE TABLE IF NOT EXISTS registrations (
    id TEXT PRIMARY KEY, user_id TEXT, event_id TEXT,
    amount REAL, status TEXT, created_at TEXT, updated_at TEXT
)
```

---

## 6. Configuration (config.py)

```python
PORT              = int(os.environ.get("PORT", 5003))
STORAGE_BACKEND   = os.environ.get("STORAGE_BACKEND", "memory")
DATA_DIR          = os.environ.get("DATA_DIR", "./data")
USER_SERVICE_URL  = os.environ.get("USER_SERVICE_URL", "http://localhost:5001")
EVENT_SERVICE_URL = os.environ.get("EVENT_SERVICE_URL", "http://localhost:5002")
```

---

## 7. Special routing

- `PUT /api/v1/registrations/{id}` → 405 (explicit route returning MethodNotAllowed error body).
- `GET /api/v1/registrations/stats?event_id=` → must be registered BEFORE `/{id}` route to avoid `stats` being captured as an id.

---

## 8. Testing strategy

### Unit tests
- Mock both user-service and event-service with `responses`.
- Test all 3 backends.
- ≥1 contract-validation test per endpoint.
- Cover: capacity full, duplicate, event not published, cancel frees seat, stats, 503.
- Coverage ≥ 80%.

### Integration tests
- Launch real user-service AND event-service subprocesses.
- Test: full happy path (create user, organizer, event, publish, register), missing reference (422), dependency down (503).
