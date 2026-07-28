from __future__ import annotations

import logging
import re
import time
from contextvars import ContextVar, Token
from typing import Any


_REQUEST_ID: ContextVar[str] = ContextVar("vlegal_request_id", default="-")
_SAFE_LABEL_RE = re.compile(r"[^A-Za-z0-9_.:-]+")


def set_request_id(value: str) -> Token[str]:
    return _REQUEST_ID.set(value or "-")


def reset_request_id(token: Token[str]) -> None:
    _REQUEST_ID.reset(token)


def current_request_id() -> str:
    return _REQUEST_ID.get()


def elapsed_ms(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


def _safe_label(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return "none"
    if isinstance(value, (int, float)):
        return str(value)
    normalized = _SAFE_LABEL_RE.sub("_", str(value).strip())
    return normalized[:120] or "empty"


def log_progress(
    logger: logging.Logger,
    operation: str,
    stage: str,
    started_at: float,
    **fields: Any,
) -> None:
    details = " ".join(
        f"{_safe_label(key)}={_safe_label(value)}"
        for key, value in sorted(fields.items())
    )
    logger.info(
        "progress operation=%s stage=%s request_id=%s elapsed_ms=%d%s",
        _safe_label(operation),
        _safe_label(stage),
        current_request_id(),
        elapsed_ms(started_at),
        f" {details}" if details else "",
    )
