from __future__ import annotations

from sqlalchemy.engine import URL, make_url


def asyncpg_database_url(database_url: str) -> URL:
    """Translate libpq-style provider parameters to asyncpg parameters."""
    url = make_url(database_url)
    if url.drivername != "postgresql+asyncpg":
        raise ValueError("DATABASE_URL must use the postgresql+asyncpg driver")

    query = dict(url.query)
    ssl_mode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    if ssl_mode and "ssl" not in query:
        query["ssl"] = ssl_mode
    return url.set(query=query)
