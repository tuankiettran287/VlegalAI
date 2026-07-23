from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert

from app.core.config import Settings
from app.db import SessionFactory
from app.models import GuestRateLimit


class GuestRateLimitExceeded(RuntimeError):
    pass


class GuestRateLimitUnavailable(RuntimeError):
    pass


class GuestRateLimiter:
    """PostgreSQL-backed fixed-window limiter for anonymous AI requests."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def check(self, subject: str) -> None:
        now = datetime.now(UTC)
        subject_hash = hashlib.sha256(subject.encode("utf-8")).hexdigest()
        minute_start = now.replace(second=0, microsecond=0)
        hour_start = minute_start.replace(minute=0)
        counts: dict[str, int] = {}
        try:
            async with SessionFactory() as db:
                for window_kind, window_start in (
                    ("MINUTE", minute_start),
                    ("HOUR", hour_start),
                ):
                    statement = (
                        insert(GuestRateLimit)
                        .values(
                            subject_hash=subject_hash,
                            window_kind=window_kind,
                            window_start=window_start,
                            request_count=1,
                        )
                        .on_conflict_do_update(
                            index_elements=[
                                GuestRateLimit.subject_hash,
                                GuestRateLimit.window_kind,
                                GuestRateLimit.window_start,
                            ],
                            set_={
                                "request_count": GuestRateLimit.request_count + 1,
                                "updated_at": func.now(),
                            },
                        )
                        .returning(GuestRateLimit.request_count)
                    )
                    counts[window_kind] = int(await db.scalar(statement))
                await db.execute(
                    delete(GuestRateLimit).where(
                        GuestRateLimit.window_start < hour_start - timedelta(hours=1),
                    )
                )
                await db.commit()
        except Exception as exc:
            raise GuestRateLimitUnavailable(
                "Không thể xác minh hạn mức chat tạm thời; vui lòng đăng nhập Google hoặc thử lại sau"
            ) from exc

        if counts["MINUTE"] > self.settings.guest_chat_requests_per_minute:
            raise GuestRateLimitExceeded("Bạn gửi câu hỏi quá nhanh; vui lòng chờ một phút rồi thử lại")
        if counts["HOUR"] > self.settings.guest_chat_requests_per_hour:
            raise GuestRateLimitExceeded(
                "Phiên khách đã đạt hạn mức theo giờ; đăng nhập Google để tiếp tục và lưu lịch sử"
            )
