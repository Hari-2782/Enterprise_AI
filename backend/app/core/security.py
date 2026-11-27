from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings


_BEARER_SCHEME = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    """Verified caller identity and authorization claims."""

    user_id: UUID
    email: str
    department: str
    roles: frozenset[str] = frozenset()


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 and a random 16-byte salt."""
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        100_000,
    )
    return f"{salt.hex()}:{derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2-HMAC-SHA256 hash."""
    try:
        salt_hex, digest_hex = stored_hash.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False

    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        100_000,
    )
    return hmac.compare_digest(derived, expected)


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


def create_access_token(
    user: AuthenticatedUser,
    *,
    ttl_minutes: int | None = None,
) -> str:
    """Create an HMAC-SHA256 signed bearer token."""
    ttl = ttl_minutes if ttl_minutes is not None else settings.auth_token_ttl_minutes
    now = int(time.time())
    payload = {
        "sub": str(user.user_id),
        "email": user.email,
        "department": user.department,
        "roles": sorted(user.roles),
        "iat": now,
        "exp": now + ttl * 60,
    }
    header_b64 = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode("utf-8"))
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    secret = settings.auth_secret_key.get_secret_value().encode("utf-8")
    signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64encode(signature)}"


def decode_access_token(token: str) -> AuthenticatedUser:
    """Verify and decode an HMAC-SHA256 bearer token."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed token")

    header_b64, payload_b64, sig_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    secret = settings.auth_secret_key.get_secret_value().encode("utf-8")
    expected_sig = hmac.new(secret, signing_input, hashlib.sha256).digest()

    try:
        actual_sig = _b64decode(sig_b64)
        payload = json.loads(_b64decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise ValueError("Invalid token encoding") from exc

    if not hmac.compare_digest(actual_sig, expected_sig):
        raise ValueError("Invalid token signature")

    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Token expired")

    return AuthenticatedUser(
        user_id=UUID(payload["sub"]),
        email=str(payload["email"]),
        department=str(payload["department"]),
        roles=frozenset(payload.get("roles") or []),
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_BEARER_SCHEME),
) -> AuthenticatedUser:
    """FastAPI dependency enforcing valid bearer authentication."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_roles(*allowed_roles: str):
    """FastAPI dependency enforcing RBAC role membership."""
    allowed = frozenset(allowed_roles)

    def _dependency(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if not (user.roles & allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions",
            )
        return user

    return _dependency
