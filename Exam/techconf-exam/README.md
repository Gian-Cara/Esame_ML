# techconf-exam — Template Repository

Template repository for the **TechConf** practical exam (Spec-Driven Development with Kiro).

Fork this repository and implement the microservices described in `Exam.MD` / the exam
brief. This template ships the **non-modifiable** contracts and the acceptance test suite.

## What this template provides

| Path | Content | Modifiable? |
|---|---|---|
| `contracts/openapi/*.yaml` | OpenAPI 3.0 contracts for the 5 services — the source of truth | ❌ NO |
| `contracts/validator.py` | `assert_matches_contract(service, method, path, response)` helper | ❌ NO |
| `tests/integration/` | Acceptance test suite (client→service, service→service, e2e, resilience) | ❌ NO |
| `CHECKSUMS.sha256` | Fingerprints of the non-modifiable files | ❌ NO |
| `services.example.yaml` | Example manifest read by the suite to launch your services | ✅ copy to `services.yaml` |

Everything else (service code, unit tests, specs, steering) is designed by you.

## Verifying the protected files

```bash
sha256sum -c CHECKSUMS.sha256
```

If you believe a contract is wrong, **open an issue** — do not modify it.

## Running the acceptance suite

1. Copy the manifest and declare the services you implemented:

   ```bash
   cp services.example.yaml services.yaml
   ```

2. Install the suite dependencies:

   ```bash
   pip install -r tests/integration/requirements.txt
   ```

3. Run the suite:

   ```bash
   pytest tests/integration -v                 # all declared services
   pytest tests/integration -m mandatory -v    # only the 3 mandatory services
   pytest tests/integration -k registration -v # a single service
   ```

Services not declared in `services.yaml` are **skipped**, not failed.

## The manifest (`services.yaml`)

For each implemented service declare its working directory (`cwd`) and start `command`.
The suite injects `PORT` and `*_SERVICE_URL` environment variables. Each service **must**
listen on the port given by `PORT`.

See `services.example.yaml` for the exact schema.

## Ports

- Development ports: `5001`–`5005`.
- Acceptance ports: `15001`–`15005` (and `15101+` for resilience instances).
- Your service must **always** read the port from the `PORT` environment variable.

Logs of services launched by the suite are written to `.it-logs/<service>.log`.
