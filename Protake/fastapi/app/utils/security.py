"""Password hashing and JWT access/refresh token utilities.

Uses the `bcrypt` library directly rather than passlib's CryptContext:
passlib 1.7.4 (its last release) does a startup self-test against the
bcrypt backend that is incompatible with bcrypt>=4.1's stricter 72-byte
enforcement, raising on every hash/verify call. Calling bcrypt directly
sidesteps that unmaintained compatibility shim entirely.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt

from app.config import get_settings

settings = get_settings()

_BCRYPT_MAX_BYTES = 72


def hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


def _create_token(subject: str, expires_delta: timedelta, token_type: Literal["access", "refresh"]) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int) -> str:
    return _create_token(
        subject=str(user_id),
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        token_type="access",
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        subject=str(user_id),
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
        token_type="refresh",
    )


class TokenError(Exception):
    pass


def decode_token(token: str, expected_type: Literal["access", "refresh"] = "access") -> int:
    """Decode a JWT and return the user id encoded in `sub`.

    Raises TokenError on any invalid/expired/mismatched-type token.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Invalid token") from exc

    if payload.get("type") != expected_type:
        raise TokenError(f"Expected a {expected_type} token")

    subject = payload.get("sub")
    if subject is None:
        raise TokenError("Token missing subject")

    return int(subject)
