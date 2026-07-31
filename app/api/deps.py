from __future__ import annotations

import secrets

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.database import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        raise credentials_exception

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_internal_service_key(
    x_internal_service_key: str | None = Header(default=None, alias="X-Internal-Service-Key"),
) -> None:
    """Service-to-service auth for internal endpoints."""
    expected = settings.INTERNAL_SERVICE_KEY
    if settings.is_production and (
        not expected or expected in {"CHANGE_ME", "CHANGE_ME_INTERNAL_SERVICE_KEY"}
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal service authentication is misconfigured",
        )
    if not x_internal_service_key or not secrets.compare_digest(x_internal_service_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Internal-Service-Key",
        )


def require_user_or_internal(
    token: str | None = Depends(oauth2_scheme_optional),
    x_internal_service_key: str | None = Header(default=None, alias="X-Internal-Service-Key"),
    db: Session = Depends(get_db),
) -> User | None:
    """Allow either a valid JWT user or a valid internal service key."""
    if x_internal_service_key:
        require_internal_service_key(x_internal_service_key)
        return None
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return get_current_user(token, db)
