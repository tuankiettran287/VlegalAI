from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings


def _encryption_key(settings: Settings) -> bytes:
    if settings.message_encryption_key:
        try:
            key = base64.urlsafe_b64decode(settings.message_encryption_key + "===")
            if len(key) == 32:
                return key
        except ValueError:
            pass
    return hashlib.sha256(settings.session_secret.encode("utf-8")).digest()


def encrypt_text(value: str, settings: Settings) -> str:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_encryption_key(settings)).encrypt(nonce, value.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_text(value: str, settings: Settings) -> str:
    payload = base64.urlsafe_b64decode(value.encode("ascii"))
    return AESGCM(_encryption_key(settings)).decrypt(payload[:12], payload[12:], None).decode("utf-8")


def create_session_token(user_id: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(seconds=settings.session_ttl_seconds),
        "iss": settings.public_url,
        "aud": "vlegal-web",
        "type": "session",
    }
    return jwt.encode(payload, settings.session_secret, algorithm="HS256")


def decode_session_token(token: str, settings: Settings) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.session_secret,
        algorithms=["HS256"],
        issuer=settings.public_url,
        audience="vlegal-web",
    )


def create_guest_token(guest_id: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": guest_id,
            "iat": now,
            "exp": now + timedelta(days=1),
            "iss": settings.public_url,
            "aud": "vlegal-guest",
            "type": "guest",
        },
        settings.session_secret,
        algorithm="HS256",
    )


def decode_guest_token(token: str, settings: Settings) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.session_secret,
        algorithms=["HS256"],
        issuer=settings.public_url,
        audience="vlegal-guest",
    )


def create_oidc_transaction(state: str, verifier: str, nonce: str, return_to: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "state": state,
            "verifier": verifier,
            "nonce": nonce,
            "return_to": return_to,
            "iat": now,
            "exp": now + timedelta(minutes=10),
            "type": "oidc_transaction",
        },
        settings.session_secret,
        algorithm="HS256",
    )


def decode_oidc_transaction(token: str, settings: Settings) -> dict[str, Any]:
    return jwt.decode(token, settings.session_secret, algorithms=["HS256"])


def json_hash(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
