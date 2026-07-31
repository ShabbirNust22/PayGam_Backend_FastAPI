import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    full_name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)

    national_id_number = Column(String, unique=True, nullable=True)
    egov_verified = Column(Boolean, default=False)

    tapsign_enrolled = Column(Boolean, default=False)
    face_enrolled = Column(Boolean, default=False)

    pin_hash = Column(String, nullable=True)
    pin_failed_attempts = Column(Integer, default=0)
    pin_locked_until = Column(DateTime(timezone=True), nullable=True)

    phone_verified = Column(Boolean, default=False)
    phone_last_verified_at = Column(DateTime(timezone=True), nullable=True)
    phone_last_sim_swap_at = Column(DateTime(timezone=True), nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    wallet = relationship("Wallet", back_populates="owner", uselist=False)
    biometric_template = relationship("BiometricTemplate", back_populates="owner", uselist=False)
    face_template = relationship("FaceTemplate", back_populates="owner", uselist=False)
    device_keys = relationship("DeviceKey", back_populates="owner")


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    balance = Column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    currency = Column(String, default="GMD")
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="wallet")


class BiometricTemplate(Base):
    """Stores the ENCRYPTED fingerprint feature vector — never the raw image."""

    __tablename__ = "biometric_templates"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    encrypted_template = Column(LargeBinary, nullable=False)
    template_version = Column(String, default="cnn-v1")
    enrolled_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="biometric_template")


class FaceTemplate(Base):
    __tablename__ = "face_templates"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    encrypted_template = Column(LargeBinary, nullable=False)
    template_version = Column(String, default="face-embed-v1")
    enrolled_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="face_template")


class DeviceKey(Base):
    __tablename__ = "device_keys"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    device_id = Column(String, unique=True, index=True, nullable=False)
    public_key_pem = Column(Text, nullable=False)
    revoked = Column(Boolean, default=False)
    registered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="device_keys")


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"

    id = Column(String, primary_key=True, default=_uuid)
    device_id = Column(String, index=True, nullable=False)
    nonce = Column(String, nullable=False)
    action = Column(String, nullable=False)
    issued_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed = Column(Boolean, default=False)
