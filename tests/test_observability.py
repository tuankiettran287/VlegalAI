from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.observability import (
    current_request_id,
    log_progress,
    reset_request_id,
    set_request_id,
)
from app.schemas import VerificationItem
from app.services.freshness import FreshnessUnavailable, LegalFreshnessService


def test_progress_log_includes_request_context_and_sanitizes_labels(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("app.tests.observability")
    token = set_request_id("request-42")
    try:
        with caplog.at_level(logging.INFO, logger=logger.name):
            log_progress(
                logger,
                "chat",
                "phase\nforged",
                time.perf_counter(),
                outcome="safe\r\nvalue",
            )
    finally:
        reset_request_id(token)

    assert current_request_id() == "-"
    assert "request_id=request-42" in caplog.text
    assert "stage=phase_forged" in caplog.text
    assert "outcome=safe_value" in caplog.text


def test_freshness_batch_has_a_hard_timeout() -> None:
    service = object.__new__(LegalFreshnessService)
    service.settings = SimpleNamespace(
        legal_freshness_timeout_seconds=0.01,
        max_laws_verified_per_request=16,
        require_freshness_check=True,
        tavily_ready=True,
    )

    async def delayed_verification(*_: object) -> object:
        await asyncio.sleep(60)
        raise AssertionError("timeout must cancel the verification task")

    service._verify_one = delayed_verification  # type: ignore[method-assign]

    source = {
        "doc_id": "45-2019",
        "title": "Bộ luật Lao động 45/2019/QH14",
        "citation": "45/2019/QH14",
        "text": "Nội dung pháp luật.",
    }

    async def scenario() -> None:
        with pytest.raises(FreshnessUnavailable):
            await service.verify_sources([source])

    started_at = time.perf_counter()
    asyncio.run(scenario())
    assert time.perf_counter() - started_at < 1


def test_freshness_batch_keeps_verified_items_when_a_secondary_item_fails() -> None:
    service = object.__new__(LegalFreshnessService)
    service.settings = SimpleNamespace(
        legal_freshness_timeout_seconds=1,
        max_laws_verified_per_request=16,
        require_freshness_check=True,
        tavily_ready=True,
    )

    async def partial_verification(
        code: str,
        *_: object,
    ) -> tuple[VerificationItem, bool]:
        if code == "45/2019/QH14":
            return (
                VerificationItem(
                    code=code,
                    title="Bộ luật Lao động",
                    status="IN_FORCE",
                    checked_at=datetime.now(UTC),
                    source_url="https://vbpl.vn/example",
                ),
                False,
            )
        raise FreshnessUnavailable("secondary source unavailable")

    service._verify_one = partial_verification  # type: ignore[method-assign]
    sources = [
        {
            "doc_id": "45-2019",
            "title": "Bộ luật Lao động 45/2019/QH14",
            "citation": "45/2019/QH14",
            "text": "Nội dung pháp luật.",
        },
        {
            "doc_id": "58-2010",
            "title": "Luật 58/2010/QH12",
            "citation": "58/2010/QH12",
            "text": "Nguồn phụ.",
        },
    ]

    report, updated = asyncio.run(service.verify_sources(sources))

    assert not updated
    assert report.checked is False
    assert report.all_current is False
    assert [item.code for item in report.items] == ["45/2019/QH14"]
    assert "58/2010/QH12" in report.note
