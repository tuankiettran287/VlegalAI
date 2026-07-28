from __future__ import annotations

import os


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw_value!r}") from exc
    if value < 1:
        raise RuntimeError(f"{name} must be greater than zero")
    return value


bind = f"0.0.0.0:{_positive_int('PORT', 8080)}"
workers = _positive_int("WEB_CONCURRENCY", 1)
worker_class = "uvicorn.workers.UvicornWorker"
configured_log_level = os.getenv("LOG_LEVEL", "INFO").strip().lower()
loglevel = (
    configured_log_level
    if configured_log_level in {"debug", "info", "warning", "error", "critical"}
    else "info"
)

timeout = _positive_int("GUNICORN_TIMEOUT_SECONDS", 3600)
graceful_timeout = _positive_int("GUNICORN_GRACEFUL_TIMEOUT_SECONDS", 30)
keepalive = _positive_int("GUNICORN_KEEPALIVE_SECONDS", 5)
max_requests = _positive_int("GUNICORN_MAX_REQUESTS", 2000)
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "200"))

worker_tmp_dir = "/dev/shm"
accesslog = "-"
errorlog = "-"
capture_output = True
