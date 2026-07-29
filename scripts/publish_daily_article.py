from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.worker import _publish_daily_article


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish one dated VLegal daily article when it does not already exist.",
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        help="Local Asia/Bangkok publication date in YYYY-MM-DD format.",
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


def main() -> None:
    args = parse_args()
    result = asyncio.run(_publish_daily_article(publication_time(args.date)))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
