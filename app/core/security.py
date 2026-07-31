"""
PayGam Backend — Security utilities
--------------------------------------
- Password hashing (bcrypt) for standard login
- JWT issuing / verification for session tokens
- Symmetric encryption helper for storing biometric templates at rest
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = (settings.TEMPLATE_ENCRYPTION_KEY or "").strip()
    if not key:
        if settings.is_production:
            raise RuntimeError("TEMPLATE_ENCRYPTION_KEY is required in production")
        # Dev-only ephemeral key — biometrics will not survive restarts.
        key = Fernet.generate_key().decode()
    if isinstance(key, str):
        key_bytes = key.encode()
    else:
        key_bytes = key
    return Fernet(key_bytes)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }
    if extra_claims:
        to_encode.update(extra_claims)
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )
    except JWTError:
        return None


def encrypt_template(raw_bytes: bytes) -> bytes:
    """Encrypt a biometric feature-vector template before persisting it."""
    return _fernet().encrypt(raw_bytes)


def decrypt_template(token: bytes) -> bytes:
    try:
        return _fernet().decrypt(token)
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt biometric template with current key") from exc
