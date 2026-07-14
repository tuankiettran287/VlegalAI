from __future__ import annotations

from datetime import UTC, datetime

from redis.asyncio import Redis

from app.core.config import Settings


class GuestRateLimitExceeded(RuntimeError):
    pass


class GuestRateLimitUnavailable(RuntimeError):
    pass


class GuestRateLimiter:
    """Distributed fixed-window limiter for anonymous AI requests."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)

    async def close(self) -> None:
        await self.redis.aclose()

    async def check(self, subject: str) -> None:
        now = datetime.now(UTC)
        minute_key = f"guest-chat:minute:{now:%Y%m%d%H%M}:{subject}"
        hour_key = f"guest-chat:hour:{now:%Y%m%d%H}:{subject}"
        try:
            async with self.redis.pipeline(transaction=True) as pipeline:
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
