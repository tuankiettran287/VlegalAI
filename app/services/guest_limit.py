from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from app.core.config import Settings
from app.core.redis_client import create_async_redis


class GuestRateLimitExceeded(RuntimeError):
    pass


class GuestRateLimitUnavailable(RuntimeError):
    pass


class GuestRateLimiter:
    """Distributed fixed-window limiter for anonymous AI requests."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.redis = create_async_redis(settings)

    async def close(self) -> None:
        await self.redis.aclose()

    async def check(self, subject: str) -> None:
        now = datetime.now(UTC)
        # The hash tag keeps both counters in one Redis Cluster slot. Hashing
        # also prevents braces in an untrusted subject from changing the slot.
        subject_slot = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:32]
        minute_key = f"guest-chat:{{{subject_slot}}}:minute:{now:%Y%m%d%H%M}"
        hour_key = f"guest-chat:{{{subject_slot}}}:hour:{now:%Y%m%d%H}"
        try:
            async with self.redis.pipeline(transaction=not self.settings.redis_cluster_mode) as pipeline:
                pipeline.incr(minute_key)
                pipeline.expire(minute_key, 90)
                pipeline.incr(hour_key)
                pipeline.expire(hour_key, 3700)
                minute_count, _, hour_count, _ = await pipeline.execute()
        except Exception as exc:
            raise GuestRateLimitUnavailable(
                "Không thể xác minh hạn mức chat tạm thời; vui lòng đăng nhập Google hoặc thử lại sau"
            ) from exc

        if int(minute_count) > self.settings.guest_chat_requests_per_minute:
            raise GuestRateLimitExceeded("Bạn gửi câu hỏi quá nhanh; vui lòng chờ một phút rồi thử lại")
        if int(hour_count) > self.settings.guest_chat_requests_per_hour:
            raise GuestRateLimitExceeded(
                "Phiên khách đã đạt hạn mức theo giờ; đăng nhập Google để tiếp tục và lưu lịch sử"
            )
