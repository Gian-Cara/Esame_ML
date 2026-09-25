# Tasks — event-service

- [ ] **T-01** — Project scaffold: `services/event-service/` with `app/`, `tests/unit/`, `tests/integration/`, `requirements.txt`, `data/.gitkeep`
  _Requirements: REQ-EVT-06_

- [ ] **T-02** — `config.py`: PORT, STORAGE_BACKEND, DATA_DIR, USER_SERVICE_URL
  _Requirements: REQ-EVT-06_

- [ ] **T-03** — `repository.py`: memory backend (create, get, update, delete, list with status/city filters)
  _Requirements: REQ-EVT-04, REQ-EVT-B06_

- [ ] **T-04** — `repository.py`: json backend
  _Requirements: REQ-EVT-06_

- [ ] **T-05** — `repository.py`: sqlite backend
  _Requirements: REQ-EVT-06_

- [ ] **T-06** — `clients.py`: UserServiceClient with get_user(); raises DependencyError on timeout/5xx
  _Requirements: REQ-EVT-B01, REQ-EVT-B05_

- [ ] **T-07** — `service.py`: field validation (title, dates, capacity, price, status enum)
  _Requirements: REQ-EVT-03, REQ-EVT-B03_

- [ ] **T-08** — `service.py`: organizer validation (call client, check role) → REFERENCE_NOT_FOUND / INVALID_ORGANIZER / DEPENDENCY_UNAVAILABLE
  _Requirements: REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05_

- [ ] **T-09** — `service.py`: status transition enforcement → INVALID_STATUS_TRANSITION
  _Requirements: REQ-EVT-B04_

- [ ] **T-10** — `service.py`: create_event, get_event, list_events, replace_event, update_event, delete_event
  _Requirements: REQ-EVT-01, REQ-EVT-04_

- [ ] **T-11** — `routes.py`: all endpoints + /health, malformed JSON → 400
  _Requirements: REQ-EVT-01, REQ-EVT-04, REQ-EVT-05_

- [ ] **T-12** — `__init__.py` + `__main__.py`: app factory wiring + entrypoint
  _Requirements: REQ-EVT-06_

- [ ] **T-13** — Unit tests: all 3 backends, responses mock for user-service, ≥1 contract test per endpoint, coverage ≥ 80%
  _Requirements: REQ-EVT-01 through REQ-EVT-B06_

- [ ] **T-14** — Integration tests: real user-service subprocess, test +/422(ref)/503 cases
  _Requirements: REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05_
