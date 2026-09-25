# Design — user-service

**Contract reference:** `contracts/openapi/user-service.yaml`
**Requirements reference:** `.kiro/specs/user-service/requirements.md`

---

## 1. Component overview

```
services/user-service/
├── app/
│   ├── __init__.py       # Flask app factory (create_app)
│   ├── __main__.py       # Entrypoint: reads PORT from env, runs Flask
│   ├── config.py         # Single place for ALL env-var reads
│   ├── routes.py         # HTTP layer: parse request → call service → serialize response
│   ├── service.py        # Business rules (REQ-USR-*): validation, uniqueness, defaults
│   ├── repository.py     # Storage abstraction: memory / json / sqlite
│   └── clients.py        # HTTP clients to external services (empty for user-service)
├── tests/
│   ├── unit/             # pytest, responses mock, all 3 backends, ≥80% coverage
│   └── integration/      # starts real service process, tests live HTTP
├── requirements.txt
└── data/                 # excluded from git; json/sqlite files land here
```

### Responsibility boundaries

| Module | Responsibility | Must NOT |
|---|---|---|
| `routes.py` | Parse HTTP request, call service layer, return HTTP response with correct status + headers | Contain business logic or storage code |
| `service.py` | Enforce all REQ-USR-* rules: field validation, email uniqueness, defaults | Import Flask, read env vars, touch storage directly |
| `repository.py` | Expose uniform CRUD interface regardless of backend | Contain business rules |
| `config.py` | Read every env var with defaults | — |
| `clients.py` | HTTP calls to other services (none needed for user-service) | — |

---

## 2. Data model

### User resource

| Field | Type | Notes |
|---|---|---|
| `id` | UUID v4 string | Generated server-side, never from client |
| `first_name` | string | 1–50 chars |
| `last_name` | string | 1–50 chars |
| `email` | string | Valid email, stored lowercase, unique |
| `company` | string \| null | max 100 chars, optional |
| `role` | enum | `attendee` \| `speaker` \| `organizer`, default `attendee` |
| `created_at` | ISO 8601 UTC string | Set at creation, never updated |
| `updated_at` | ISO 8601 UTC string | Updated on every write |

---

## 3. Business rules implementation (service.py)

All rules from `requirements.md` live in `service.py`:

- **Field validation** (REQ-USR-03): check lengths, email format regex, role enum — raise `ValidationError(422)` on failure.
- **Email uniqueness** (REQ-USR-02): before create/update, query repository for existing email (case-insensitive); raise `ConflictError(409, "EMAIL_ALREADY_EXISTS")` if found on a different `id`.
- **Email normalisation** (REQ-USR-02): `email.lower()` before storing.
- **Default role** (REQ-USR-01): if `role` not in payload, default to `"attendee"`.
- **ID generation** (REQ-USR-01): `str(uuid.uuid4())` always server-side.
- **Timestamps** (REQ-USR-01): `datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")`.

---

## 4. Repository interface

```python
class UserRepository:
    def create(self, user: dict) -> dict: ...
    def get(self, user_id: str) -> dict | None: ...
    def update(self, user_id: str, data: dict) -> dict | None: ...
    def delete(self, user_id: str) -> bool: ...
    def list(self, filters: dict, page: int, page_size: int) -> tuple[list, int]: ...
```

Three concrete implementations behind the same interface, selected by `config.STORAGE_BACKEND`:

| Backend | Implementation | Notes |
|---|---|---|
| `memory` | `dict` in RAM | Default; reset on restart |
| `json` | Read/write single JSON file in `DATA_DIR/users.json` | File created on first write |
| `sqlite` | `sqlite3` in `DATA_DIR/users.db` | Table auto-created on startup |

`service.py` receives the repository via dependency injection (passed by `create_app`), making it trivial to swap backends in tests.

---

## 5. HTTP layer (routes.py)

### Error response format (all errors)

```json
{"error": {"code": "UPPER_SNAKE", "message": "...", "details": {}}}
```

### Endpoint mapping

| Method | Path | Service call | Success | Errors |
|---|---|---|---|---|
| POST | `/api/v1/users` | `svc.create_user(body)` | 201 + Location header | 400, 409, 422 |
| GET | `/api/v1/users` | `svc.list_users(filters, page, page_size)` | 200 paginated | 422 |
| GET | `/api/v1/users/{id}` | `svc.get_user(id)` | 200 | 404 |
| PUT | `/api/v1/users/{id}` | `svc.replace_user(id, body)` | 200 | 404, 409, 422 |
| PATCH | `/api/v1/users/{id}` | `svc.update_user(id, body)` | 200 | 404, 409, 422 |
| DELETE | `/api/v1/users/{id}` | `svc.delete_user(id)` | 204 | 404 |
| GET | `/health` | — | 200 | — |

Malformed JSON (not parseable) → 400 before reaching service layer (Flask `get_json(silent=True)` returns None).

---

## 6. Configuration (config.py)

```python
PORT             = int(os.environ.get("PORT", 5001))
STORAGE_BACKEND  = os.environ.get("STORAGE_BACKEND", "memory")   # memory|json|sqlite
DATA_DIR         = os.environ.get("DATA_DIR", "./data")
# user-service calls no other services, so no *_SERVICE_URL needed here
```

---

## 7. Startup (\_\_main\_\_.py)

```python
from app import create_app
from app.config import PORT

app = create_app()
app.run(host="0.0.0.0", port=PORT)
```

`create_app()` in `__init__.py`:
1. Reads `config.STORAGE_BACKEND`, instantiates the correct repository.
2. Creates service instance with the repository.
3. Registers blueprints (routes).

---

## 8. Testing strategy

### Unit tests (`tests/unit/`)

- **All three backends** tested with `tmp_path` fixture (json/sqlite) or plain memory.
- HTTP calls mocked with `responses` library (not applicable here — user-service makes no outbound calls).
- At least **1 contract-validation test per endpoint** using `assert_matches_contract("user", method, path, response)`.
- Marker `@pytest.mark.req("REQ-USR-XX")` on every test.
- Coverage target: ≥ 80% (`pytest --cov=app`).

### Integration tests (`tests/integration/`)

- Not required for user-service (it has no upstream dependencies).
- The acceptance suite (`tests/integration/test_user.py`) covers IT-U01–IT-U08.

---

## 9. Contract compliance

The OpenAPI contract (`contracts/openapi/user-service.yaml`) defines:

- `User` schema: `id`, `first_name`, `last_name`, `email`, `company` (nullable), `role`, `created_at`, `updated_at` — all required except `company`. `additionalProperties: false`.
- `UserPage` schema: `items`, `page`, `page_size`, `total` — all required. `additionalProperties: false`.
- `Error` schema: `{"error": {"code": ..., "message": ..., "details": ...}}`. `additionalProperties: false`.
- `Health` schema: `{"status": "ok", "service": "..."}`. `additionalProperties: false`.

Any extra field in a response will fail contract validation. Use `assert_matches_contract` in tests to catch this early.
