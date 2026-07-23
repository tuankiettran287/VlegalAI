from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy.dialects import postgresql

from app.api import _load_postgres_chat_history
from app.core.config import Settings
from app.core.security import encrypt_text


class _ScalarRows:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def all(self) -> list[SimpleNamespace]:
        return self._rows


def test_authenticated_history_is_loaded_from_postgresql_in_chronological_order() -> None:
    settings = Settings(_env_file=None, session_secret="test-session-secret")
    conversation_id = uuid.uuid4()
    now = datetime.now(UTC)
    oldest = SimpleNamespace(
        role="USER",
        content_ciphertext=encrypt_text("Câu hỏi trước", settings),
        created_at=now,
    )
    newest = SimpleNamespace(
        role="ASSISTANT",
        content_ciphertext=encrypt_text("Câu trả lời sau", settings),
        created_at=now + timedelta(seconds=1),
    )
    db = SimpleNamespace(scalars=AsyncMock(return_value=_ScalarRows([newest, oldest])))

    history = asyncio.run(
        _load_postgres_chat_history(db, conversation_id, settings, limit=12)
    )

    assert history == [("USER", "Câu hỏi trước"), ("ASSISTANT", "Câu trả lời sau")]
    statement = db.scalars.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FROM chat_message" in sql
    assert "chat_message.conversation_id" in sql
    assert "ORDER BY chat_message.created_at DESC" in sql
