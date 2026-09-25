# Requirements — event-service

**Contract reference:** `contracts/openapi/event-service.yaml`
**Port:** 5002 | **Base path:** `/api/v1/events`

---

## User Stories & Acceptance Criteria (EARS notation)

---

### REQ-EVT-01 — Create event

**User story:** As an organizer, I want to create a new event so that users can register for it.

**Acceptance criteria**

1. WHEN a POST request is made to `/api/v1/events` with a valid body THE SYSTEM SHALL create the event, respond 201 with the full event object, and include a `Location` header pointing to `/api/v1/events/{id}`.
2. WHEN a POST request is made with a missing required field (`title`, `organizer_id`, `venue`, `city`, `start_date`, `end_date`, `capacity`, `price`) THE SYSTEM SHALL respond 422 with error code `VALIDATION_ERROR`.
3. WHEN a POST request is made with a malformed JSON body THE SYSTEM SHALL respond 400.
4. WHEN a POST request is made without a `status` field THE SYSTEM SHALL default `status` to `draft`.
5. WHEN an event is created THE SYSTEM SHALL generate a UUID v4 `id` server-side, never accepting it from the client.
6. WHEN an event is created THE SYSTEM SHALL set `created_at` and `updated_at` to the current UTC timestamp in ISO 8601 format.

---

### REQ-EVT-B01 — Organizer must exist

**User story:** As a platform admin, I want events to reference valid organizers so that data integrity is maintained.

**Acceptance criteria**

1. WHEN a POST or PUT or PATCH request sets `organizer_id` THE SYSTEM SHALL call `GET /api/v1/users/{organizer_id}` on user-service.
2. IF user-service returns 404 THEN THE SYSTEM SHALL respond 422 with error code `REFERENCE_NOT_FOUND`.

---

### REQ-EVT-B02 — Organizer role check

**User story:** As a platform admin, I want only users with `role = organizer` to be able to own events.

**Acceptance criteria**

1. WHEN user-service returns 200 for `organizer_id` AND the returned user has `role != organizer` THE SYSTEM SHALL respond 422 with error code `INVALID_ORGANIZER`.

---

### REQ-EVT-B03 — Date validation

**User story:** As an organizer, I want the system to reject invalid date ranges to prevent data entry errors.

**Acceptance criteria**

1. WHEN `end_date` is earlier than `start_date` THE SYSTEM SHALL respond 422 with error code `VALIDATION_ERROR`.
2. WHEN dates are not in `YYYY-MM-DD` format THE SYSTEM SHALL respond 422 with error code `VALIDATION_ERROR`.

---

### REQ-EVT-B04 — Status transitions

**User story:** As an organizer, I want controlled event lifecycle transitions so that published events cannot be accidentally reverted to draft.

**Acceptance criteria**

1. WHEN a PATCH or PUT request attempts `draft → published` THE SYSTEM SHALL allow the transition.
2. WHEN a PATCH or PUT request attempts `draft → cancelled` THE SYSTEM SHALL allow the transition.
3. WHEN a PATCH or PUT request attempts `published → cancelled` THE SYSTEM SHALL allow the transition.
4. IF a PATCH or PUT request attempts any other status transition (e.g. `published → draft`, `cancelled → draft`, `cancelled → published`) THEN THE SYSTEM SHALL respond 422 with error code `INVALID_STATUS_TRANSITION`.

---

### REQ-EVT-B05 — Dependency unavailable

**User story:** As a platform operator, I want clear error responses when dependencies are down so that clients can handle failures gracefully.

**Acceptance criteria**

1. IF user-service is unreachable (timeout, connection refused, or 5xx) THEN THE SYSTEM SHALL respond 503 with error code `DEPENDENCY_UNAVAILABLE`.

---

### REQ-EVT-B06 — List filters

**User story:** As a client, I want to filter events by status and city so that I can find relevant events.

**Acceptance criteria**

1. WHEN the `status` query parameter is provided THE SYSTEM SHALL return only events whose status matches.
2. WHEN the `city` query parameter is provided THE SYSTEM SHALL return only events whose city matches (case-insensitive).
3. WHEN `page_size` exceeds 100 THE SYSTEM SHALL respond 422 with error code `VALIDATION_ERROR`.

---

### REQ-EVT-03 — Field validation

**Acceptance criteria**

1. WHEN `title` has fewer than 3 or more than 120 characters THE SYSTEM SHALL respond 422 `VALIDATION_ERROR`.
2. WHEN `description` exceeds 2000 characters THE SYSTEM SHALL respond 422 `VALIDATION_ERROR`.
3. WHEN `venue` exceeds 100 characters THE SYSTEM SHALL respond 422 `VALIDATION_ERROR`.
4. WHEN `city` exceeds 60 characters THE SYSTEM SHALL respond 422 `VALIDATION_ERROR`.
5. WHEN `capacity` is less than 1 or greater than 10000 THE SYSTEM SHALL respond 422 `VALIDATION_ERROR`.
6. WHEN `price` is negative THE SYSTEM SHALL respond 422 `VALIDATION_ERROR`.
7. WHEN `status` is not one of `draft`, `published`, `cancelled` THE SYSTEM SHALL respond 422 `VALIDATION_ERROR`.

---

### REQ-EVT-04 — Read, update, delete

**Acceptance criteria**

1. WHEN a GET request is made to `/api/v1/events/{id}` with an existing UUID THE SYSTEM SHALL respond 200 with the event.
2. WHEN a GET request is made to a non-existent UUID THE SYSTEM SHALL respond 404 with error code `NOT_FOUND`.
3. WHEN a PUT request is made THE SYSTEM SHALL replace all fields and respond 200.
4. WHEN a PATCH request is made THE SYSTEM SHALL update only provided fields and respond 200.
5. WHEN a DELETE request is made to an existing event THE SYSTEM SHALL delete it and respond 204.
6. WHEN a DELETE request is made to a non-existent event THE SYSTEM SHALL respond 404.

---

### REQ-EVT-05 — Health check

**Acceptance criteria**

1. WHEN a GET request is made to `/health` THE SYSTEM SHALL respond 200 with `{"status": "ok", "service": "event-service"}`.

---

### REQ-EVT-06 — Persistence and configuration

**Acceptance criteria**

1. WHEN `STORAGE_BACKEND=memory` THE SYSTEM SHALL store data in RAM.
2. WHEN `STORAGE_BACKEND=json` THE SYSTEM SHALL persist to `DATA_DIR/events.json`.
3. WHEN `STORAGE_BACKEND=sqlite` THE SYSTEM SHALL persist to `DATA_DIR/events.db` using `sqlite3`.
4. WHEN the service starts THE SYSTEM SHALL read `PORT` from the environment (default 5002).
5. WHEN calling user-service THE SYSTEM SHALL use `USER_SERVICE_URL` env var (default `http://localhost:5001`).
6. WHEN a call to user-service times out or connection is refused THE SYSTEM SHALL respond 503.
