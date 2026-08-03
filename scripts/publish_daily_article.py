from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import SessionFactory
from app.models import Article
from app.worker import _publish_daily_article


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Publish the 10-article VLegal batch for the applicable scheduled "
            "time when individual articles do not already exist."
        ),
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        help="Local Asia/Bangkok publication date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--purge-all",
        action="store_true",
        help=(
            "Delete only rows from the article table before rebuilding the "
            "current scheduled batch. Legal documents and indexes are untouched."
        ),
    )
    return parser.parse_args()


def publication_time(local_date: date | None) -> datetime | None:
    if local_date is None:
        return None
    return datetime.combine(
        local_date,
        time(hour=7),
        tzinfo=ZoneInfo("Asia/Bangkok"),
    )


async def purge_all_articles() -> int:
    async with SessionFactory() as db:
        count = int(await db.scalar(select(func.count()).select_from(Article)) or 0)
        await db.execute(delete(Article))
        await db.commit()
    return count


async def run(args: argparse.Namespace) -> dict[str, object]:
    purged_count = await purge_all_articles() if args.purge_all else 0
    result = await _publish_daily_article(publication_time(args.date))
    return {**result, "purged_count": purged_count}


def main() -> None:
    args = parse_args()
    result = asyncio.run(run(args))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
