"""Process harness for the TechConf acceptance suite.

Non-modifiable. Reads ``services.yaml`` from the repository root, launches the
declared services as ordinary Python processes on the acceptance ports, injects
the required environment variables, and waits for each ``/health`` endpoint.

Also supports launching an extra *resilience* instance of a service whose
dependency URLs point at a closed port, to exercise the 503 paths.
"""

from __future__ import annotations

import contextlib
import os
import signal
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import requests
import yaml

# --------------------------------------------------------------------------- #
# Layout / constants
# --------------------------------------------------------------------------- #

# tests/integration/harness.py  ->  repo root is two levels up.
REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "services.yaml"
LOG_DIR = REPO_ROOT / ".it-logs"

# Canonical service metadata.
SERVICE_ORDER = ["user", "event", "registration", "feedback", "notification"]
MANDATORY = {"user", "event", "registration"}

ACCEPTANCE_PORTS = {
    "user": 15001,
    "event": 15002,
    "registration": 15003,
    "feedback": 15004,
    "notification": 15005,
}
# Resilience instances live at +100.
RESILIENCE_PORTS = {name: port + 100 for name, port in ACCEPTANCE_PORTS.items()}

ENV_URL_KEYS = {
    "user": "USER_SERVICE_URL",
    "event": "EVENT_SERVICE_URL",
    "registration": "REGISTRATION_SERVICE_URL",
    "feedback": "FEEDBACK_SERVICE_URL",
    "notification": "NOTIFICATION_SERVICE_URL",
}

# A port that is guaranteed to be closed, used for resilience tests.
CLOSED_PORT = 1  # connections are refused immediately

HEALTH_TIMEOUT_S = 25.0
HEALTH_POLL_S = 0.25


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #


@dataclass
class ServiceSpec:
    name: str
    cwd: Path
    command: str
    health_path: str = "/health"


def load_manifest() -> dict[str, ServiceSpec]:
    """Return declared services keyed by canonical name.

    Missing manifest -> empty dict (every service is then skipped).
    """
    if not MANIFEST.is_file():
        return {}
    with MANIFEST.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    services = raw.get("services", {}) or {}
    result: dict[str, ServiceSpec] = {}
    for name, cfg in services.items():
        key = name.lower().replace("-service", "")
        if key not in ACCEPTANCE_PORTS:
            continue
        cwd = (REPO_ROOT / cfg["cwd"]).resolve()
        result[key] = ServiceSpec(
            name=key,
            cwd=cwd,
            command=str(cfg["command"]),
            health_path=str(cfg.get("health_path", "/health")),
        )
    return result


# --------------------------------------------------------------------------- #
# Process management
# --------------------------------------------------------------------------- #


def _free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _wait_health(base_url: str, health_path: str, proc: subprocess.Popen) -> None:
    url = base_url + health_path
    deadline = time.time() + HEALTH_TIMEOUT_S
    last_err: str = "no attempt"
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"Service process exited early (code {proc.returncode}) "
                f"before {url} became healthy."
            )
        try:
            resp = requests.get(url, timeout=1.0)
            if resp.status_code == 200:
                return
            last_err = f"status {resp.status_code}"
        except requests.RequestException as exc:
            last_err = str(exc)
        time.sleep(HEALTH_POLL_S)
    raise RuntimeError(f"Timed out waiting for {url} to be healthy ({last_err}).")


@dataclass
class RunningService:
    name: str
    base_url: str
    proc: subprocess.Popen
    log_handle: object = field(default=None, repr=False)

    def terminate(self) -> None:
        if self.proc.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                if os.name == "posix":
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                else:  # pragma: no cover - non-posix fallback
                    self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    if os.name == "posix":
                        os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                    else:  # pragma: no cover
                        self.proc.kill()
        if self.log_handle is not None:
            with contextlib.suppress(Exception):
                self.log_handle.close()


def _launch(
    spec: ServiceSpec,
    port: int,
    service_urls: dict[str, str],
    log_suffix: str = "",
    extra_env: dict[str, str] | None = None,
) -> RunningService:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{spec.name}{log_suffix}.log"
    log_handle = log_path.open("w", encoding="utf-8")

    env = os.environ.copy()
    env["PORT"] = str(port)
    for url_key, url in service_urls.items():
        env[url_key] = url
    if extra_env:
        env.update(extra_env)

    popen_kwargs: dict[str, object] = dict(
        cwd=str(spec.cwd),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        shell=True,
    )
    if os.name == "posix":
        popen_kwargs["preexec_fn"] = os.setsid  # own process group for clean kill

    proc = subprocess.Popen(spec.command, **popen_kwargs)  # noqa: S602 - trusted manifest
    base_url = f"http://127.0.0.1:{port}"
    running = RunningService(spec.name, base_url, proc, log_handle)
    try:
        _wait_health(base_url, spec.health_path, proc)
    except Exception:
        running.terminate()
        # Surface the tail of the log to aid debugging.
        tail = ""
        with contextlib.suppress(Exception):
            tail = log_path.read_text(encoding="utf-8")[-2000:]
        raise RuntimeError(
            f"Failed to start service '{spec.name}'. Log tail:\n{tail}"
        )
    return running


def _standard_urls(ports: dict[str, str]) -> dict[str, str]:
    """Map *_SERVICE_URL env vars from a name->url dict."""
    return {ENV_URL_KEYS[name]: url for name, url in ports.items()}


@contextlib.contextmanager
def launch_platform(specs: dict[str, ServiceSpec]) -> Iterator[dict[str, RunningService]]:
    """Launch every declared service on its acceptance port, in dependency order.

    All declared services receive the full set of *_SERVICE_URL variables so
    inter-service calls resolve to the acceptance instances.
    """
    urls = {
        name: f"http://127.0.0.1:{ACCEPTANCE_PORTS[name]}"
        for name in specs
    }
    service_urls = _standard_urls(urls)

    running: dict[str, RunningService] = {}
    try:
        for name in SERVICE_ORDER:
            if name not in specs:
                continue
            port = ACCEPTANCE_PORTS[name]
            if not _free(port):
                raise RuntimeError(
                    f"Acceptance port {port} for '{name}' is already in use."
                )
            running[name] = _launch(specs[name], port, service_urls)
        yield running
    finally:
        for svc in reversed(list(running.values())):
            svc.terminate()


@contextlib.contextmanager
def launch_with_dead_dependency(
    spec: ServiceSpec,
) -> Iterator[RunningService]:
    """Launch a single service whose dependency URLs point at a closed port.

    Used by resilience tests to force ``503 DEPENDENCY_UNAVAILABLE``.
    """
    port = RESILIENCE_PORTS[spec.name]
    if not _free(port):
        raise RuntimeError(f"Resilience port {port} for '{spec.name}' is in use.")
    dead = f"http://127.0.0.1:{CLOSED_PORT}"
    service_urls = {key: dead for key in ENV_URL_KEYS.values()}
    running = _launch(
        spec, port, service_urls, log_suffix="-resilience"
    )
    try:
        yield running
    finally:
        running.terminate()
