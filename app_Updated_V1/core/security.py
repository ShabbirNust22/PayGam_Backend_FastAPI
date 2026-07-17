"""
PayGam Backend — Security utilities
--------------------------------------
- Password hashing (bcrypt) for standard login
- JWT issuing / verification for session tokens
- Symmetric encryption helper for storing biometric templates at rest
  (TapSign never stores raw fingerprint images — only encrypted feature
  vectors produced by the on-device/CNN feature extractor)
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt, JWTError
from passlib.context import CryptContext
from cryptography.fernet import Fernet

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# NOTE: In production this key is pulled from a secrets manager (e.g. AWS KMS,
# HashiCorp Vault) and rotated periodically — never hard-coded like this.
_FERNET_KEY = Fernet.generate_key()
_fernet = Fernet(_FERNET_KEY)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode: dict[str, Any] = {"sub": subject, "exp": expire}
    if extra_claims:
        to_encode.update(extra_claims)
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


def encrypt_template(raw_bytes: bytes) -> bytes:
    """Encrypt a biometric feature-vector template before persisting it."""
    return _fernet.encrypt(raw_bytes)


def decrypt_template(token: bytes) -> bytes:
    return _fernet.decrypt(token)
