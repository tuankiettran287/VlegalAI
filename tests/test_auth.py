from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi import HTTPException

from app import auth
from app.core.config import Settings
from app.core.security import decode_session_token
from app.models import User


class _TokenResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {"id_token": "google-id-token"}


class _OidcClient:
    async def __aenter__(self) -> _OidcClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def post(self, *_: object, **__: object) -> _TokenResponse:
        return _TokenResponse()


class _Session:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.added: list[object] = []
        self.rolled_back = False

    async def scalar(self, _: object) -> None:
        if self.fail:
            raise RuntimeError("database unavailable")
        return None

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        user = next(value for value in self.added if isinstance(value, User))
        user.id = uuid.uuid4()

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        self.rolled_back = True


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "public_url": "http://localhost:8000",
        "frontend_url": "http://localhost:5173",
        "oidc_client_id": "client-id",
        "oidc_client_secret": "client-secret",
        "oidc_redirect_uri": "",
        "session_secret": "test-session-secret-that-is-long-enough",
        "cookie_secure": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _install_oidc_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    async def metadata(_: Settings) -> dict[str, str]:
        return {"token_endpoint": "https://accounts.google.com/token"}

    async def claims(*_: object) -> dict[str, object]:
        return {
            "sub": "google-subject",
            "iss": "https://accounts.google.com",
            "email": "user@example.com",
            "email_verified": True,
            "name": "Local User",
            "picture": "https://example.com/avatar.png",
        }

    monkeypatch.setattr(
        auth,
        "decode_oidc_transaction",
        lambda *_: {"verifier": "verifier", "nonce": "nonce", "return_to": "/contracts"},
    )
    monkeypatch.setattr(auth, "_oidc_metadata", metadata)
    monkeypatch.setattr(auth, "_decode_id_token", claims)
    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **_: _OidcClient())


def test_oidc_callback_url_is_derived_from_public_runtime_url() -> None:
    settings = _settings(public_url="https://api.example.com", api_prefix="/v1")

    assert settings.oidc_callback_url == "https://api.example.com/v1/auth/google/callback"


def test_oidc_callback_sets_backend_cookie_and_redirects_to_frontend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_oidc_stubs(monkeypatch)
    settings = _settings()
    db = _Session()

    response = asyncio.run(
        auth.callback(
            request=None,  # type: ignore[arg-type]
            code="authorization-code",
            state="signed-state",
            db=db,  # type: ignore[arg-type]
            settings=settings,
        )
    )

    assert response.status_code == 302
    assert response.headers["location"] == "http://localhost:5173/contracts"
    assert "session_callback" not in response.headers["location"]
    cookie = response.headers["set-cookie"]
    assert "vlegal_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" not in cookie

    token = cookie.split("vlegal_session=", 1)[1].split(";", 1)[0]
    payload = decode_session_token(token, settings)
    user = next(value for value in db.added if isinstance(value, User))
    assert payload["sub"] == str(user.id)


def test_oidc_callback_does_not_issue_session_when_user_persistence_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_oidc_stubs(monkeypatch)
    db = _Session(fail=True)

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            auth.callback(
                request=None,  # type: ignore[arg-type]
                code="authorization-code",
                state="signed-state",
                db=db,  # type: ignore[arg-type]
                settings=_settings(),
            )
        )

    assert error.value.status_code == 503
    assert db.rolled_back is True
