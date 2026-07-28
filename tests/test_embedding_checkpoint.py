from app.legal_graphrag import (
    CHUNK_OVERLAP_WORDS,
    CHUNK_WINDOW_WORDS,
    embedding_text_windows,
)
from app.services.embedding_checkpoint import (
    _postgres_dsn,
    embedding_content_hash,
)


def test_embedding_content_hash_is_stable_and_content_sensitive() -> None:
    assert embedding_content_hash("Điều 1") == embedding_content_hash("Điều 1")
    assert embedding_content_hash("Điều 1") != embedding_content_hash("Điều 2")


def test_postgres_dsn_converts_async_driver_and_ssl_alias() -> None:
    dsn = _postgres_dsn(
        "postgresql+asyncpg://user:password@localhost:5432/vlegal?ssl=require"
    )

    assert dsn.startswith("postgresql://user:password@localhost:5432/vlegal")
    assert "sslmode=require" in dsn
    assert "ssl=" not in dsn


def test_embedding_text_windows_bounds_and_overlaps_long_content() -> None:
    words = [f"word-{index}" for index in range(CHUNK_WINDOW_WORDS * 2)]

    windows = embedding_text_windows(" ".join(words))

    assert len(windows) >= 2
    assert all(len(window.split()) <= CHUNK_WINDOW_WORDS for window in windows)
    first = windows[0].split()
    second = windows[1].split()
    assert first[-CHUNK_OVERLAP_WORDS:] == second[:CHUNK_OVERLAP_WORDS]
