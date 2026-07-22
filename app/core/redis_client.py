from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit

import google.auth
from google.auth.transport.requests import Request
from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster
from redis.credentials import CredentialProvider

from app.core.config import Settings


GOOGLE_CLOUD_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class GoogleIAMCredentialProvider(CredentialProvider):
    """Refresh an ADC access token before Redis opens a new connection."""

    def __init__(self, refresh_margin: timedelta = timedelta(minutes=5)) -> None:
        self._credentials, _ = google.auth.default(scopes=[GOOGLE_CLOUD_SCOPE])
        self._request = Request()
        self._refresh_margin = refresh_margin
        self._lock = threading.Lock()

    def _needs_refresh(self) -> bool:
        if not self._credentials.token:
            return True
        expiry = self._credentials.expiry
        if expiry is None:
            return not self._credentials.valid
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        return expiry <= datetime.now(UTC) + self._refresh_margin

    def get_credentials(self) -> tuple[str]:
        with self._lock:
            if self._needs_refresh():
                self._credentials.refresh(self._request)
            token = self._credentials.token
            if not token:
                raise RuntimeError("Google ADC did not return an access token for Redis IAM authentication")
            # Memorystore IAM authentication expects the OAuth access token as
            # the only AUTH argument. It does not use a Redis username.
            return (str(token),)

    async def get_credentials_async(self) -> tuple[str]:
        return await asyncio.to_thread(self.get_credentials)


def _cluster_endpoint(settings: Settings) -> tuple[str, int, bool, str | None, str | None]:
    parsed = urlsplit(settings.redis_url)
    if parsed.scheme not in {"redis", "rediss"}:
        raise ValueError("REDIS_URL must use redis:// or rediss://")
    if not parsed.hostname:
        raise ValueError("REDIS_URL must include a host")
    if parsed.path not in {"", "/", "/0"}:
        raise ValueError("Memorystore for Redis Cluster only supports database 0")
    if settings.redis_iam_auth and parsed.scheme != "rediss":
        raise ValueError("Redis IAM authentication must use rediss:// with TLS enabled")

    ca_certs: str | None = None
    if settings.redis_ca_certs:
        ca_path = Path(settings.redis_ca_certs).expanduser()
        if not ca_path.is_file():
            raise FileNotFoundError(f"Redis CA certificate not found: {ca_path}")
        ca_certs = str(ca_path)
    elif parsed.scheme == "rediss" and settings.redis_iam_auth:
        raise ValueError("REDIS_CA_CERTS is required when Redis IAM authentication and TLS are enabled")

    return (
        parsed.hostname,
        parsed.port or 6379,
        parsed.scheme == "rediss",
        unquote(parsed.username) if parsed.username else None,
        unquote(parsed.password) if parsed.password else None,
    )


def create_async_redis(settings: Settings, *, decode_responses: bool = True) -> Redis | RedisCluster:
    """Create the local Redis client or the GCP Memorystore cluster client."""

    credential_provider = GoogleIAMCredentialProvider() if settings.redis_iam_auth else None
    if settings.redis_cluster_mode:
        host, port, use_tls, username, password = _cluster_endpoint(settings)
        if settings.redis_iam_auth and (username or password):
            raise ValueError("Do not put a username or password in REDIS_URL when REDIS_IAM_AUTH=true")
        return RedisCluster(
            host=host,
            port=port,
            require_full_coverage=False,
            credential_provider=credential_provider,
            username=None if settings.redis_iam_auth else username,
            password=None if settings.redis_iam_auth else password,
            decode_responses=decode_responses,
            ssl=use_tls,
            ssl_ca_certs=settings.redis_ca_certs or None,
            ssl_cert_reqs="required",
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )

    options: dict[str, object] = {
        "decode_responses": decode_responses,
        "socket_connect_timeout": 5,
        "socket_keepalive": True,
        "health_check_interval": 30,
    }
    if credential_provider is not None:
        options["credential_provider"] = credential_provider
    if settings.redis_url.startswith("rediss://") and settings.redis_ca_certs:
        options["ssl_ca_certs"] = settings.redis_ca_certs
        options["ssl_cert_reqs"] = "required"
    return Redis.from_url(settings.redis_url, **options)
