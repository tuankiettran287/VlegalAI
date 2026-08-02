"""Tests for generation timeout guards and aggregate telemetry in /api/chat.

These tests verify the P0 fixes:
1. _complete_with_citation_repair raises GeminiError when generation_timeout elapses.
2. Citation repair raises GeminiError (or returns grounded draft) when
   citation_repair_timeout elapses.
3. Settings correctly exposes legal_chat_fast_timeout_seconds,
   legal_chat_generation_timeout_seconds, and
   legal_chat_citation_repair_timeout_seconds.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api import _complete_with_citation_repair
from app.core.config import Settings
from app.services.ai import GeminiError, GeminiService


# ---------------------------------------------------------------------------
# Helper: build a minimal GeminiService stub
# ---------------------------------------------------------------------------

def _make_ai_stub(*, delay: float = 0.0, text: str = "Câu trả lời hợp lệ [S1].") -> GeminiService:
    """Return a GeminiService mock whose complete() waits *delay* seconds."""

    async def _slow_complete(*args, **kwargs) -> str:
        if delay:
            await asyncio.sleep(delay)
        return text

    async def _slow_complete_json(*args, **kwargs) -> dict:
        if delay:
            await asyncio.sleep(delay)
        return {"statements": [{"text": "Theo Điều 1 [S1].", "citations": ["S1"]}]}

    stub = MagicMock(spec=GeminiService)
    stub.complete = AsyncMock(side_effect=_slow_complete)
    stub.complete_json = AsyncMock(side_effect=_slow_complete_json)
    return stub


# ---------------------------------------------------------------------------
# Tests: generation timeout
# ---------------------------------------------------------------------------

def test_generation_timeout_raises_gemini_error() -> None:
    """When generation takes longer than generation_timeout, GeminiError is raised."""
    ai = _make_ai_stub(delay=2.0)

    async def _run():
        with pytest.raises(GeminiError, match="timed out"):
            await _complete_with_citation_repair(
                ai,
                system="sys",
                prompt="user",
                allowed_ids=["S1"],
                max_tokens=500,
                generation_timeout=0.05,  # 50 ms — intentionally shorter than delay
            )

    asyncio.run(_run())


def test_generation_succeeds_within_timeout() -> None:
    """When generation is fast, it succeeds even with a strict timeout."""
    ai = _make_ai_stub(delay=0.0, text="Theo Điều 1 khoản 2 BLLĐ 2019 [S1], ...")

    async def _run():
        result = await _complete_with_citation_repair(
            ai,
            system="sys",
            prompt="user",
            allowed_ids=["S1"],
            max_tokens=500,
            generation_timeout=5.0,
        )
        assert result  # returned something non-empty

    asyncio.run(_run())


def test_no_generation_timeout_when_none() -> None:
    """Passing generation_timeout=None disables the guard."""
    ai = _make_ai_stub(delay=0.0, text="Theo Điều 1 [S1].")

    async def _run():
        result = await _complete_with_citation_repair(
            ai,
            system="sys",
            prompt="user",
            allowed_ids=["S1"],
            max_tokens=500,
            generation_timeout=None,
        )
        assert result

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Tests: citation_repair_timeout
# ---------------------------------------------------------------------------

def test_citation_repair_timeout_returns_grounded_draft() -> None:
    """When citation_repair times out AND the draft is safety-valid,
    the original grounded draft is returned instead of raising GeminiError."""

    draft_text = "Theo Điều 1 khoản 2 BLLĐ [S1], người lao động có quyền nghỉ phép."

    async def _fast_draft(*args, **kwargs):
        return draft_text

    async def _slow_repair(*args, **kwargs):
        await asyncio.sleep(2.0)
        return {"statements": [{"text": draft_text, "citations": ["S1"]}]}

    ai = MagicMock(spec=GeminiService)
    ai.complete = AsyncMock(side_effect=_fast_draft)
    ai.complete_json = AsyncMock(side_effect=_slow_repair)

    async def _run():
        result = await _complete_with_citation_repair(
            ai,
            system="sys",
            prompt="user",
            allowed_ids=["S1"],
            max_tokens=500,
            generation_timeout=5.0,
            citation_repair_timeout=0.05,
        )
        assert result == draft_text

    asyncio.run(_run())


def test_citation_repair_timeout_raises_when_draft_not_grounded() -> None:
    """When citation_repair times out AND the draft is NOT safety-valid,
    GeminiError is raised."""

    draft_text = "Câu trả lời không có trích dẫn hợp lệ."

    async def _fast_draft(*args, **kwargs):
        return draft_text

    async def _slow_repair(*args, **kwargs):
        await asyncio.sleep(2.0)
        return {"statements": [{"text": draft_text, "citations": ["S1"]}]}

    ai = MagicMock(spec=GeminiService)
    ai.complete = AsyncMock(side_effect=_fast_draft)
    ai.complete_json = AsyncMock(side_effect=_slow_repair)

    async def _run():
        with pytest.raises(GeminiError):
            await _complete_with_citation_repair(
                ai,
                system="sys",
                prompt="user",
                allowed_ids=["S1"],
                max_tokens=500,
                generation_timeout=5.0,
                citation_repair_timeout=0.05,
            )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Tests: Settings config fields
# ---------------------------------------------------------------------------

def test_settings_has_legal_chat_timeout_fields() -> None:
    """Settings must expose the three legal_chat timeout fields with correct defaults."""
    s = Settings(
        database_url="postgresql+asyncpg://u:p@h:5432/db",
        session_secret="x" * 32,
    )
    assert s.legal_chat_fast_timeout_seconds == 8.0
    assert s.legal_chat_generation_timeout_seconds == 30.0
    assert s.legal_chat_citation_repair_timeout_seconds == 5.0


def test_settings_fast_timeout_overridable() -> None:
    """Settings accepts overrides for legal_chat_fast_timeout_seconds."""
    s = Settings(
        database_url="postgresql+asyncpg://u:p@h:5432/db",
        session_secret="x" * 32,
        legal_chat_fast_timeout_seconds=12.0,
    )
    assert s.legal_chat_fast_timeout_seconds == 12.0


def test_settings_timeouts_respect_bounds() -> None:
    """legal_chat_fast_timeout_seconds must reject values below ge=2.0."""
    import pydantic
    with pytest.raises((pydantic.ValidationError, ValueError)):
        Settings(
            database_url="postgresql+asyncpg://u:p@h:5432/db",
            session_secret="x" * 32,
            legal_chat_fast_timeout_seconds=0.5,  # below ge=2.0
        )
