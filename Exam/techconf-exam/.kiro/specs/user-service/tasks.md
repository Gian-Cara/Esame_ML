# Tasks — user-service

All tasks must be executed in order. No application code is written before this file is committed.

---

- [ ] **T-01** — Project scaffold: create `services/user-service/` directory structure with `app/`, `tests/unit/`, `tests/integration/`, `requirements.txt`, `data/.gitkeep`
  _Requirements: REQ-USR-10, REQ-USR-11_

- [ ] **T-02** — `config.py`: read `PORT`, `STORAGE_BACKEND`, `DATA_DIR` from environment with defaults
  _Requirements: REQ-USR-11_

- [ ] **T-03** — `repository.py`: implement `UserRepository` interface with `memory` backend (create, get, update, delete, list with filters and pagination)
  _Requirements: REQ-USR-01, REQ-USR-04, REQ-USR-05, REQ-USR-06, REQ-USR-07, REQ-USR-08_

- [ ] **T-04** — `repository.py`: add `json` backend (read/write `DATA_DIR/users.json`)
  _Requirements: REQ-USR-10_

- [ ] **T-05** — `repository.py`: add `sqlite` backend (auto-create table, CRUD using `sqlite3`)
  _Requirements: REQ-USR-10_

- [ ] **T-06** — `service.py`: field validation (lengths, email format, role enum) → 422 `VALIDATION_ERROR`
  _Requirements: REQ-USR-03_

- [ ] **T-07** — `service.py`: email uniqueness check (case-insensitive) → 409 `EMAIL_ALREADY_EXISTS`; normalise email to lowercase on save
  _Requirements: REQ-USR-02_

- [ ] **T-08** — `service.py`: implement `create_user` — validate, check uniqueness, generate UUID + timestamps, default role, delegate to repository
  _Requirements: REQ-USR-01, REQ-USR-02, REQ-USR-03_

- [ ] **T-09** — `service.py`: implement `get_user`, `list_users`, `replace_user`, `update_user`, `delete_user`
  _Requirements: REQ-USR-04, REQ-USR-05, REQ-USR-06, REQ-USR-07, REQ-USR-08_

- [ ] **T-10** — `routes.py`: register all endpoints (POST, GET list, GET by id, PUT, PATCH, DELETE `/api/v1/users`, GET `/health`); handle malformed JSON → 400
  _Requirements: REQ-USR-01, REQ-USR-04, REQ-USR-05, REQ-USR-06, REQ-USR-07, REQ-USR-08, REQ-USR-09_

- [ ] **T-11** — `__init__.py` + `__main__.py`: Flask app factory wiring repository → service → routes; entrypoint reads PORT and starts server
  _Requirements: REQ-USR-11_

- [ ] **T-12** — Unit tests: test all three backends (memory, json with `tmp_path`, sqlite with `tmp_path`); ≥1 contract-validation test per endpoint using `assert_matches_contract`; coverage ≥ 80%
  _Requirements: REQ-USR-01 through REQ-USR-11_
