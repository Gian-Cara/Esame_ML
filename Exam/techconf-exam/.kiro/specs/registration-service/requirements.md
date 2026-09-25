# Requirements — registration-service

**Contract reference:** `contracts/openapi/registration-service.yaml`
**Port:** 5003 | **Base path:** `/api/v1/registrations`

---

## User Stories & Acceptance Criteria (EARS notation)

---

### REQ-REG-01 — Create registration

**User story:** As an attendee, I want to register for a published event so that I can attend it.

**Acceptance criteria**

1. WHEN a POST request is made to `/api/v1/registrations` with valid `user_id` and `event_id` THE SYSTEM SHALL create the registration with `status = confirmed`, respond 201, and include a `Location` header.
2. WHEN a POST request is made with a missing `user_id` or `event_id` THE SYSTEM SHALL respond 422 `VALIDATION_ERROR`.
3. WHEN a POST request is made with a malformed JSON body THE SYSTEM SHALL respond 400.
4. WHEN a registration is created THE SYSTEM SHALL generate a UUID v4 `id`, `created_at`, and `updated_at`, all server-side.

---

### REQ-REG-B01 — User must exist

**Acceptance criteria**

1. WHEN creating a registration THE SYSTEM SHALL call `GET /api/v1/users/{user_id}` on user-service.
2. IF user-service returns 404 THEN THE SYSTEM SHALL respond 422 `REFERENCE_NOT_FOUND`.

---

### REQ-REG-B02 — Event must exist

**Acceptance criteria**

1. WHEN creating a registration THE SYSTEM SHALL call `GET /api/v1/events/{event_id}` on event-service.
2. IF event-service returns 404 THEN THE SYSTEM SHALL respond 422 `REFERENCE_NOT_FOUND`.

---

### REQ-REG-B03 — Event must be published

**Acceptance criteria**

1. IF the event `status != published` THEN THE SYSTEM SHALL respond 422 `EVENT_NOT_OPEN`.

---

### REQ-REG-B04 — No duplicate confirmed registration

**User story:** As a platform admin, I want to prevent a user from registering twice for the same event.

**Acceptance criteria**

1. IF the user already has a `confirmed` registration for the same event THEN THE SYSTEM SHALL respond 409 `ALREADY_REGISTERED`.

---

### REQ-REG-B05 — Event capacity

**User story:** As an organizer, I want registrations to stop when the event is full so that we never exceed venue capacity.

**Acceptance criteria**

1. WHEN a registration is requested AND the confirmed registrations for the event are fewer than `event.capacity` THE SYSTEM SHALL create it with status `confirmed`.
2. IF the confirmed registrations equal `event.capacity` THEN THE SYSTEM SHALL respond 409 `EVENT_FULL`.
3. WHEN a confirmed registration is cancelled THE SYSTEM SHALL free one seat.

---

### REQ-REG-B06 — Amount copied from event

**Acceptance criteria**

1. WHEN a registration is created THE SYSTEM SHALL set `amount` = `event.price` read from event-service, never from the client.

---

### REQ-REG-B07 — Status transition

**Acceptance criteria**

1. WHEN a PATCH request sets `status` to `cancelled` on a `confirmed` registration THE SYSTEM SHALL allow it and free a seat.
2. IF a PATCH request attempts `cancelled → confirmed` THEN THE SYSTEM SHALL respond 422 `INVALID_STATUS_TRANSITION`.
3. WHEN a PATCH request is made to a non-existent registration THE SYSTEM SHALL respond 404 `NOT_FOUND`.

---

### REQ-REG-B08 — Stats

**Acceptance criteria**

1. WHEN a GET request is made to `/api/v1/registrations/stats?event_id=` for an existing event THE SYSTEM SHALL respond 200 with `{event_id, capacity, confirmed, available}`.
2. IF the event does not exist THEN THE SYSTEM SHALL respond 404 `NOT_FOUND`.
3. `available` SHALL equal `capacity - confirmed`.

---

### REQ-REG-B09 — Dependency unavailable

**Acceptance criteria**

1. IF user-service or event-service is unreachable (timeout, connection refused, 5xx) THEN THE SYSTEM SHALL respond 503 `DEPENDENCY_UNAVAILABLE`.

---

### REQ-REG-02 — Read, list, delete

**Acceptance criteria**

1. WHEN a GET request is made to `/api/v1/registrations/{id}` with an existing UUID THE SYSTEM SHALL respond 200.
2. WHEN a GET request is made to a non-existent UUID THE SYSTEM SHALL respond 404 `NOT_FOUND`.
3. WHEN a GET request is made to `/api/v1/registrations` THE SYSTEM SHALL respond 200 with a paginated list, filterable by `user_id`, `event_id`, `status`.
4. WHEN a DELETE request is made to an existing registration THE SYSTEM SHALL respond 204.
5. WHEN a DELETE request is made to a non-existent registration THE SYSTEM SHALL respond 404.

---

### REQ-REG-B10 — PUT not allowed

**Acceptance criteria**

1. WHEN a PUT request is made to `/api/v1/registrations/{id}` THE SYSTEM SHALL respond 405 (method not allowed).

---

### REQ-REG-03 — Health & config

**Acceptance criteria**

1. WHEN a GET request is made to `/health` THE SYSTEM SHALL respond 200 with `{"status": "ok", "service": "registration-service"}`.
2. WHEN the service starts THE SYSTEM SHALL read `PORT` (default 5003).
3. THE SYSTEM SHALL read `USER_SERVICE_URL` (default `http://localhost:5001`) and `EVENT_SERVICE_URL` (default `http://localhost:5002`).
4. THE SYSTEM SHALL support `memory`, `json`, and `sqlite` backends via `STORAGE_BACKEND`.
