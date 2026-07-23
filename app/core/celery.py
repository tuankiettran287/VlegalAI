from __future__ import annotations


def postgres_celery_urls(database_url: str) -> tuple[str, str]:
    """Derive Celery's synchronous PostgreSQL URLs from the async app URL."""
    if database_url.startswith("postgresql+asyncpg://"):
        sync_url = database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    elif database_url.startswith("postgresql+psycopg://"):
        sync_url = database_url
    elif database_url.startswith("postgresql://"):
        sync_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    else:
        raise ValueError("DATABASE_URL must point to PostgreSQL")
    return f"sqla+{sync_url}", f"db+{sync_url}"
