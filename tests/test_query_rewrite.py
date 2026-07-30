from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.services.ai import GeminiError
from app.services.query_rewrite import (
    rewrite_query_if_needed,
    should_rewrite_query,
)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "query_rewrite_enabled": True,
        "query_rewrite_timeout_seconds": 2,
        "query_rewrite_min_confidence": 0.75,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    "query",
    [
        "cty ko trả lương thì lm ntn?",
        "NLĐ nghỉ việc có được nhận BHXH không?",
        "kh0ng ký hđlđ có sao ko???",
        "trờiiii công ty giữ lương",
        "công ty gi@ lương thì làm sao?",
    ],
)
def test_noisy_or_abbreviated_query_requires_rewrite(query: str) -> None:
    assert should_rewrite_query(query)


@pytest.mark.parametrize(
    "query",
    [
        "Cưỡng bức lao động",
        "Doanh nghiệp có được giữ lương của người lao động không?",
        "Điều kiện hưởng trợ cấp thất nghiệp là gì?",
        "Luật lao động 2019 có mấy điều?",
    ],
)
def test_clear_query_skips_rewrite(query: str) -> None:
    assert not should_rewrite_query(query)


def test_clear_query_does_not_call_llm() -> None:
    ai = SimpleNamespace(complete_json=AsyncMock())

    result = asyncio.run(
        rewrite_query_if_needed(
            ai,
            "Cưỡng bức lao động",
            history=[],
            settings=_settings(),
        )
    )

    assert result.retrieval_query == "Cưỡng bức lao động"
    assert not result.attempted
    assert not result.rewritten
    ai.complete_json.assert_not_awaited()


def test_teencode_query_is_rewritten_for_retrieval() -> None:
    ai = SimpleNamespace(
        complete_json=AsyncMock(
            return_value={
                "rewrite_required": True,
                "rewritten_query": (
                    "Công ty không trả lương thì người lao động cần làm như thế nào?"
                ),
                "confidence": 0.96,
                "reason": "Mở rộng teencode và từ viết tắt.",
            }
        )
    )

    result = asyncio.run(
        rewrite_query_if_needed(
            ai,
            "cty ko trả lương thì NLĐ lm ntn?",
            history=[("user", "Tôi đang hỏi về quan hệ lao động.")],
            settings=_settings(),
        )
    )

    assert result.attempted
    assert result.rewritten
    assert result.confidence == 0.96
    assert result.original_query == "cty ko trả lương thì NLĐ lm ntn?"
    assert result.retrieval_query == (
        "Công ty không trả lương thì người lao động cần làm như thế nào?"
    )
    ai.complete_json.assert_awaited_once()


def test_low_confidence_rewrite_falls_back_to_original() -> None:
    ai = SimpleNamespace(
        complete_json=AsyncMock(
            return_value={
                "rewrite_required": True,
                "rewritten_query": "Bảo hiểm nào được áp dụng?",
                "confidence": 0.51,
                "reason": "Từ viết tắt có nhiều nghĩa.",
            }
        )
    )

    result = asyncio.run(
        rewrite_query_if_needed(
            ai,
            "bh tn áp dụng ntn?",
            history=[],
            settings=_settings(),
        )
    )

    assert result.attempted
    assert not result.rewritten
    assert result.retrieval_query == "bh tn áp dụng ntn?"


def test_rewrite_cannot_invent_legal_references_or_numbers() -> None:
    ai = SimpleNamespace(
        complete_json=AsyncMock(
            return_value={
                "rewrite_required": True,
                "rewritten_query": (
                    "Theo Điều 17, công ty không trả lương trong 15 ngày thì làm gì?"
                ),
                "confidence": 0.99,
                "reason": "Chuẩn hóa câu hỏi.",
            }
        )
    )

    result = asyncio.run(
        rewrite_query_if_needed(
            ai,
            "cty ko trả lương thì lm j?",
            history=[],
            settings=_settings(),
        )
    )

    assert not result.rewritten
    assert result.retrieval_query == "cty ko trả lương thì lm j?"


def test_llm_failure_falls_back_to_original_query() -> None:
    ai = SimpleNamespace(
        complete_json=AsyncMock(side_effect=GeminiError("Vertex unavailable"))
    )

    result = asyncio.run(
        rewrite_query_if_needed(
            ai,
            "cty ko trả lương thì lm j?",
            history=[],
            settings=_settings(),
        )
    )

    assert result.attempted
    assert not result.rewritten
    assert result.reason == "llm_unavailable"
    assert result.retrieval_query == "cty ko trả lương thì lm j?"
