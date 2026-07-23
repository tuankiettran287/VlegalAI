from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.dialects import postgresql

from app.core.celery import postgres_celery_urls
from app.core.config import Settings
from app.services import guest_limit
from app.services.guest_limit import GuestRateLimiter


class _FakeSession:
    def __init__(self, counts: list[int]) -> None:
        self.counts = iter(counts)
        self.statements: list[object] = []
        self.committed = False

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def scalar(self, statement: object) -> int:
        self.statements.append(statement)
        return next(self.counts)

    async def execute(self, statement: object) -> None:
        self.statements.append(statement)

    async def commit(self) -> None:
        self.committed = True


def test_celery_uses_postgresql_transport_and_result_backend() -> None:
    broker, backend = postgres_celery_urls(
        "postgresql+asyncpg://vlegal:secret@postgres:5432/vlegal"
    )

    assert broker == "sqla+postgresql+psycopg://vlegal:secret@postgres:5432/vlegal"
    assert backend == "db+postgresql+psycopg://vlegal:secret@postgres:5432/vlegal"


def test_celery_rejects_non_postgresql_database() -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        postgres_celery_urls("sqlite:///vlegal.db")


def test_guest_rate_limit_is_an_atomic_postgresql_upsert(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeSession([1, 1])
    monkeypatch.setattr(guest_limit, "SessionFactory", lambda: db)
    limiter = GuestRateLimiter(Settings(_env_file=None))

    asyncio.run(limiter.check("anonymous-subject"))

    assert db.committed
    assert len(db.statements) == 3
    for statement in db.statements[:2]:
        sql = str(statement.compile(dialect=postgresql.dialect()))
        assert "INSERT INTO guest_rate_limit" in sql
        assert "ON CONFLICT" in sql
        assert "request_count" in sql
