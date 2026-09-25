# Requirements — user-service

**Contract reference:** `contracts/openapi/user-service.yaml`
**Port:** 5001 | **Base path:** `/api/v1/users`

---

## User Stories & Acceptance Criteria (EARS notation)

---

### REQ-USR-01 — Create user

**User story:** As a platform client, I want to register a new user so that they can participate in TechConf events.

**Acceptance criteria**

1. WHEN a POST request is made to `/api/v1/users` with a valid JSON body containing `first_name`, `last_name`, and `email` THE SYSTEM SHALL create the user and respond 201 with the full user object and a `Location` header pointing to `/api/v1/users/{id}`.
2. WHEN a POST request is made with a missing or empty `first_name`, `last_name`, or `email` THE SYSTEM SHALL respond 422 with error code `VALIDATION_ERROR`.
3. WHEN a POST request is made with a malformed JSON body THE SYSTEM SHALL respond 400.
4. WHEN a POST request is made without a `role` field THE SYSTEM SHALL default `role` to `attendee`.
5. WHEN a user is created THE SYSTEM SHALL generate a UUID v4 `id`, never accepting it from the client.
6. WHEN a user is created THE SYSTEM SHALL set `created_at` and `updated_at` to the current UTC timestamp in ISO 8601 format.

---

### REQ-USR-02 — Email uniqueness

**User story:** As a platform administrator, I want email addresses to be unique so that each person has exactly one account.

**Acceptance criteria**

1. WHEN a POST request is made with an `email` that already exists (case-insensitive comparison) THE SYSTEM SHALL respond 409 with error code `EMAIL_ALREADY_EXISTS`.
2. WHEN a PUT or PATCH request changes the `email` to one already used by another user (case-insensitive) THE SYSTEM SHALL respond 409 with error code `EMAIL_ALREADY_EXISTS`.
3. WHEN a user is created or updated THE SYSTEM SHALL store the email in lowercase.

---

### REQ-USR-03 — Field validation

**User story:** As a platform client, I want field constraints enforced so that data quality is guaranteed.

**Acceptance criteria**

1. WHEN `first_name` has fewer than 1 or more than 50 characters THE SYSTEM SHALL respond 422 with error code `VALIDATION_ERROR`.
2. WHEN `last_name` has fewer than 1 or more than 50 characters THE SYSTEM SHALL respond 422 with error code `VALIDATION_ERROR`.
3. WHEN `email` is not a valid email format THE SYSTEM SHALL respond 422 with error code `VALIDATION_ERROR`.
4. WHEN `company` is provided and exceeds 100 characters THE SYSTEM SHALL respond 422 with error code `VALIDATION_ERROR`.
5. WHEN `role` is provided with a value other than `attendee`, `speaker`, or `organizer` THE SYSTEM SHALL respond 422 with error code `VALIDATION_ERROR`.

---

### REQ-USR-04 — Get user by ID

**User story:** As a platform client, I want to retrieve a specific user by their ID so that I can display or validate their profile.

**Acceptance criteria**

1. WHEN a GET request is made to `/api/v1/users/{id}` with a valid existing UUID THE SYSTEM SHALL respond 200 with the full user object.
2. WHEN a GET request is made to `/api/v1/users/{id}` with a UUID that does not exist THE SYSTEM SHALL respond 404 with error code `NOT_FOUND`.

---

### REQ-USR-05 — List users with pagination and filters

**User story:** As a platform client, I want to list users with optional filters and pagination so that I can browse or search the user registry.

**Acceptance criteria**

1. WHEN a GET request is made to `/api/v1/users` THE SYSTEM SHALL respond 200 with a paginated response `{"items": [...], "page": N, "page_size": N, "total": N}`.
2. WHEN `page` and `page_size` query parameters are provided THE SYSTEM SHALL return the corresponding slice of results.
3. WHEN `page_size` exceeds 100 THE SYSTEM SHALL respond 422 with error code `VALIDATION_ERROR`.
4. WHEN `page` or `page_size` are not provided THE SYSTEM SHALL default to `page=1` and `page_size=20`.
5. WHEN the `role` query parameter is provided THE SYSTEM SHALL return only users whose `role` matches.
6. WHEN the `email` query parameter is provided THE SYSTEM SHALL return only users whose email matches (case-insensitive).

---

### REQ-USR-06 — Replace user (PUT)

**User story:** As a platform client, I want to fully replace a user's data so that I can update all fields at once.

**Acceptance criteria**

1. WHEN a PUT request is made to `/api/v1/users/{id}` with a valid body THE SYSTEM SHALL replace all fields and respond 200 with the updated user object.
2. WHEN a PUT request is made to a non-existent user THE SYSTEM SHALL respond 404 with error code `NOT_FOUND`.
3. WHEN a PUT request is made THE SYSTEM SHALL update `updated_at` to the current UTC timestamp.
4. WHEN a PUT request is made THE SYSTEM SHALL NOT change `id` or `created_at`.

---

### REQ-USR-07 — Partially update user (PATCH)

**User story:** As a platform client, I want to update individual fields of a user without sending the full object.

**Acceptance criteria**

1. WHEN a PATCH request is made to `/api/v1/users/{id}` with one or more valid fields THE SYSTEM SHALL update only the provided fields and respond 200 with the updated user object.
2. WHEN a PATCH request is made to a non-existent user THE SYSTEM SHALL respond 404 with error code `NOT_FOUND`.
3. WHEN a PATCH request is made THE SYSTEM SHALL update `updated_at` to the current UTC timestamp.
4. WHEN a PATCH request is made THE SYSTEM SHALL NOT change `id` or `created_at`.

---

### REQ-USR-08 — Delete user

**User story:** As a platform administrator, I want to delete a user so that they are removed from the registry.

**Acceptance criteria**

1. WHEN a DELETE request is made to `/api/v1/users/{id}` with an existing UUID THE SYSTEM SHALL delete the user and respond 204 with no body.
2. WHEN a DELETE request is made to a non-existent UUID THE SYSTEM SHALL respond 404 with error code `NOT_FOUND`.

---

### REQ-USR-09 — Health check

**User story:** As the acceptance test suite, I want a health endpoint so that I can verify the service is running.

**Acceptance criteria**

1. WHEN a GET request is made to `/health` THE SYSTEM SHALL respond 200 with `{"status": "ok", "service": "user-service"}`.

---

### REQ-USR-10 — Persistence backends

**User story:** As a developer, I want the service to support three storage backends so that I can run it in-memory during tests and with durable storage in production.

**Acceptance criteria**

1. WHEN `STORAGE_BACKEND=memory` (or not set) THE SYSTEM SHALL store data in RAM.
2. WHEN `STORAGE_BACKEND=json` THE SYSTEM SHALL persist data as a JSON file in `DATA_DIR` (default `./data`).
3. WHEN `STORAGE_BACKEND=sqlite` THE SYSTEM SHALL persist data in a SQLite file in `DATA_DIR` using only the `sqlite3` standard library.
4. IF the storage backend changes THE SYSTEM SHALL require no modifications to the business logic layer.

---

### REQ-USR-11 — Configuration

**User story:** As an operator, I want all configuration read from environment variables so that the service can be deployed without code changes.

**Acceptance criteria**

1. WHEN the service starts THE SYSTEM SHALL read `PORT` from the environment and listen on that port.
2. WHEN `PORT` is not set THE SYSTEM SHALL default to `5001`.
3. WHEN the service starts THE SYSTEM SHALL read all env vars from a single `config.py` module — no other module reads env vars directly.
