from __future__ import annotations

from app.core.schedules import (
    ARTICLE_PUBLISH_HOURS,
    LEGAL_FRESHNESS_INTERVAL_DAYS,
    LEGAL_FRESHNESS_INTERVAL_SECONDS,
)


def test_shared_legal_freshness_policy_is_ten_days() -> None:
    assert LEGAL_FRESHNESS_INTERVAL_DAYS == 10
    assert LEGAL_FRESHNESS_INTERVAL_SECONDS == 10 * 24 * 60 * 60


def test_shared_article_publication_hours_match_product_policy() -> None:
    assert ARTICLE_PUBLISH_HOURS == (7, 12, 15, 18, 22)
