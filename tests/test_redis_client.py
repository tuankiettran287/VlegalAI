from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from redis.asyncio.cluster import RedisCluster

from app.core.config import Settings
from app.core.redis_client import GoogleIAMCredentialProvider, create_async_redis


def test_memorystore_cluster_client_uses_tls_ca(tmp_path) -> None:
    ca_file = tmp_path / "server-ca.pem"
    ca_file.write_text("test certificate is parsed only when a connection opens", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        redis_url="rediss://10.170.0.3:6379/0",
        redis_cluster_mode=True,
        redis_iam_auth=False,
        redis_ca_certs=str(ca_file),
    )

    client = create_async_redis(settings)

    assert isinstance(client, RedisCluster)
    assert client.connection_kwargs["ssl_ca_certs"] == str(ca_file)
    assert client.connection_kwargs["ssl_cert_reqs"] == "required"
    asyncio.run(client.aclose())


def test_memorystore_cluster_rejects_nonzero_database(tmp_path) -> None:
    ca_file = tmp_path / "server-ca.pem"
    ca_file.touch()
    settings = Settings(
        _env_file=None,
        redis_url="rediss://10.170.0.3:6379/1",
        redis_cluster_mode=True,
        redis_iam_auth=False,
        redis_ca_certs=str(ca_file),
    )

    with pytest.raises(ValueError, match="database 0"):
        create_async_redis(settings)


def test_google_iam_provider_refreshes_and_reuses_token(monkeypatch) -> None:
    class FakeCredentials:
        token = None
        expiry = None
        valid = False

        def __init__(self) -> None:
            self.refresh_count = 0

        def refresh(self, _request) -> None:
            self.refresh_count += 1
            self.token = "short-lived-token"
            self.expiry = datetime.now(UTC) + timedelta(hours=1)
            self.valid = True

    credentials = FakeCredentials()
    monkeypatch.setattr(
        "app.core.redis_client.google.auth.default",
        lambda scopes: (credentials, "test-project"),
    )
    provider = GoogleIAMCredentialProvider()

    assert provider.get_credentials() == ("short-lived-token",)
    assert provider.get_credentials() == ("short-lived-token",)
    assert credentials.refresh_count == 1
