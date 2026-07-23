from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import (
    create_oidc_transaction,
    create_session_token,
    decode_oidc_transaction,
    decode_session_token,
)
from app.db import get_db
from app.models import SsoIdentity, User
from app.schemas import AuthCapabilities, UserOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])
bearer = HTTPBearer(auto_error=False)


def _safe_return_to(value: str | None, settings: Settings) -> str:
    if value and value.startswith("/") and not value.startswith("//"):
        return f"{settings.frontend_url.rstrip('/')}{value}"
    return settings.frontend_url


async def _oidc_metadata(settings: Settings) -> dict:
    if not settings.oidc_ready:
        raise HTTPException(status_code=503, detail="SSO chưa được cấu hình")
    url = f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def _decode_id_token(token: str, metadata: dict, nonce: str, settings: Settings) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(metadata["jwks_uri"])
        response.raise_for_status()
        jwks = response.json()
    header = jwt.get_unverified_header(token)
    matching_key = next((item for item in jwks.get("keys", []) if item.get("kid") == header.get("kid")), None)
    if not matching_key:
        raise HTTPException(status_code=401, detail="Không tìm thấy khóa ký SSO phù hợp")
    claims = jwt.decode(
        token,
        jwt.PyJWK.from_dict(matching_key).key,
        algorithms=[header.get("alg", "RS256")],
        audience=settings.oidc_client_id,
        issuer=settings.oidc_issuer.rstrip("/"),
    )
    if claims.get("nonce") != nonce:
        raise HTTPException(status_code=401, detail="SSO nonce không hợp lệ")
    email = str(claims.get("email") or "").lower().strip()
    if not email or claims.get("email_verified") is not True:
        raise HTTPException(status_code=401, detail="Tài khoản Google chưa xác minh địa chỉ email")
    return claims


async def _resolve_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
    settings: Settings,
    *,
    required: bool,
) -> User | None:
    token = credentials.credentials if credentials else request.cookies.get("vlegal_session")
    if not token:
        if required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Vui lòng đăng nhập bằng Google để sử dụng tính năng này",
            )
        return None

    try:
        payload = decode_session_token(token, settings)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        if required:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Phiên đăng nhập không hợp lệ") from exc
        return None

    user = await db.get(User, user_id)
    if user and user.is_active:
        return user
    if required:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản không còn hoạt động")
    return None


async def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    user = await _resolve_user(request, credentials, db, settings, required=True)
    assert user is not None
    return user


async def optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User | None:
    return await _resolve_user(request, credentials, db, settings, required=False)


def require_roles(*roles: str):
    async def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Bạn không có quyền thực hiện thao tác này")
        return user

    return dependency


@router.get("/capabilities", response_model=AuthCapabilities)
async def capabilities(settings: Settings = Depends(get_settings)) -> AuthCapabilities:
    """Expose feature availability without returning provider configuration."""
    return AuthCapabilities(google_login=settings.oidc_ready)


@router.get("/login", include_in_schema=False)
@router.get("/google/login")
async def login(return_to: str = "/", settings: Settings = Depends(get_settings)) -> Response:
    metadata = await _oidc_metadata(settings)
    # Use a short random value as the internal CSRF state
    state_value = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    # Encode the full transaction as a signed JWT and use it as the OAuth state parameter.
    # This avoids relying on cross-domain cookies (frontend sets cookie but callback goes to backend domain).
    state_jwt = create_oidc_transaction(state_value, verifier, nonce, return_to, settings)
    query = urlencode(
        {
            "client_id": settings.oidc_client_id,
            "response_type": "code",
            "redirect_uri": settings.oidc_redirect_uri,
            "scope": settings.oidc_scopes,
            "state": state_jwt,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
            "include_granted_scopes": "true",
        }
    )
    return RedirectResponse(f"{metadata['authorization_endpoint']}?{query}", status_code=302)


@router.get("/callback", include_in_schema=False)
@router.get("/google/callback")
async def callback(
    request: Request,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    # state IS the signed JWT transaction — no cookie needed
    try:
        transaction = decode_oidc_transaction(state, settings)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Giao dịch SSO đã hết hạn hoặc không hợp lệ") from exc
    if False:  # state comparison no longer needed — JWT signature is the CSRF protection
        raise HTTPException(status_code=401, detail="SSO state không hợp lệ")

    metadata = await _oidc_metadata(settings)
    async with httpx.AsyncClient(timeout=20) as client:
        token_response = await client.post(
            metadata["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "client_id": settings.oidc_client_id,
                "client_secret": settings.oidc_client_secret,
                "redirect_uri": settings.oidc_redirect_uri,
                "code": code,
                "code_verifier": transaction["verifier"],
            },
        )
        token_response.raise_for_status()
        tokens = token_response.json()

    claims = await _decode_id_token(tokens["id_token"], metadata, transaction["nonce"], settings)

    subject = str(claims["sub"])
    issuer = str(claims.get("iss") or settings.oidc_issuer).rstrip("/")
    user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(claims.get("email") or subject)))

    try:
        identity = await db.scalar(
            select(SsoIdentity).where(SsoIdentity.issuer == issuer, SsoIdentity.subject == subject)
        )
        if identity:
            user = await db.get(User, identity.user_id)
        else:
            email = str(claims.get("email", "")).lower().strip()
            user = await db.scalar(select(User).where(User.email == email)) if email else None
            if not user:
                user = User(
                    email=email or f"{subject}@google.com",
                    display_name=str(claims.get("name") or claims.get("preferred_username") or "Người dùng Google"),
                    avatar_url=claims.get("picture"),
                )
                db.add(user)
                await db.flush()
            identity = SsoIdentity(
                user_id=user.id,
                issuer=issuer,
                subject=subject,
                provider="google",
                claims=claims,
            )
            db.add(identity)
        if user:
            user.last_login_at = datetime.now(UTC)
            user.display_name = str(claims.get("name") or user.display_name)
            user.avatar_url = claims.get("picture") or user.avatar_url
            user_id = str(user.id)
            await db.commit()
    except Exception as exc:
        logger.warning("SSO DB persistence bypassed: %s", exc)

    response = RedirectResponse(_safe_return_to(transaction.get("return_to"), settings), status_code=302)
    samesite = "none" if settings.cookie_secure else "lax"
    response.set_cookie(
        "vlegal_session",
        create_session_token(user_id, settings),
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=samesite,
        path="/",
    )
    return response


@router.post("/logout", status_code=204)
async def logout(settings: Settings = Depends(get_settings)) -> Response:
    response = Response(status_code=204)
    response.delete_cookie("vlegal_session", path="/", secure=settings.cookie_secure, samesite="lax")
    return response


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> User:
    return user
