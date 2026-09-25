# Tasks — registration-service

- [x] **T-01** — Scaffold: `services/registration-service/` with app/, tests/unit, tests/integration, requirements.txt, pytest.ini, data/.gitkeep
  _Requirements: REQ-REG-03_

- [x] **T-02** — `config.py`: PORT, STORAGE_BACKEND, DATA_DIR, USER_SERVICE_URL, EVENT_SERVICE_URL
  _Requirements: REQ-REG-03_

- [x] **T-03** — `repository.py`: memory backend + count_confirmed + has_confirmed + filters
  _Requirements: REQ-REG-02, REQ-REG-B04, REQ-REG-B05_

- [x] **T-04** — `repository.py`: json backend
  _Requirements: REQ-REG-03_

- [x] **T-05** — `repository.py`: sqlite backend
  _Requirements: REQ-REG-03_

- [x] **T-06** — `clients.py`: UserServiceClient + EventServiceClient, DependencyError
  _Requirements: REQ-REG-B01, REQ-REG-B02, REQ-REG-B09_

- [x] **T-07** — `service.py`: create_registration with full validation chain (user, event, published, duplicate, capacity, amount)
  _Requirements: REQ-REG-01, REQ-REG-B01, REQ-REG-B02, REQ-REG-B03, REQ-REG-B04, REQ-REG-B05, REQ-REG-B06_

- [x] **T-08** — `service.py`: status transition (PATCH), get, list, delete
  _Requirements: REQ-REG-02, REQ-REG-B07_

- [x] **T-09** — `service.py`: stats (count confirmed, available); event missing → 404
  _Requirements: REQ-REG-B08_

- [x] **T-10** — `routes.py`: all endpoints + /health + /stats + PUT->405, malformed JSON->400
  _Requirements: REQ-REG-01, REQ-REG-02, REQ-REG-B08, REQ-REG-B10, REQ-REG-03_

- [x] **T-11** — `__init__.py` + `__main__.py`: app factory + entrypoint
  _Requirements: REQ-REG-03_

- [x] **T-12** — Unit tests: all 3 backends, mock both services, ≥1 contract test per endpoint, capacity/duplicate/transition/stats/503, coverage ≥ 80%
  _Requirements: REQ-REG-01 through REQ-REG-B10_

- [x] **T-13** — Integration tests: real user + event subprocesses, happy path + 422 + 503
  _Requirements: REQ-REG-B01, REQ-REG-B02, REQ-REG-B09_
