import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, ForeignKey, LargeBinary
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

    # EGOV-verified national identity (set once KYC passes)
    national_id_number = Column(String, unique=True, nullable=True)
    egov_verified = Column(Boolean, default=False)

    # TapSign biometric enrolment status
    tapsign_enrolled = Column(Boolean, default=False)
    face_enrolled = Column(Boolean, default=False)

    # --- PIN accountability ---
    pin_hash = Column(String, nullable=True)
    pin_failed_attempts = Column(Integer, default=0)
    pin_locked_until = Column(DateTime, nullable=True)

    # --- Phone service authenticity (SIM / telco checks) ---
    phone_verified = Column(Boolean, default=False)
    phone_last_verified_at = Column(DateTime, nullable=True)
    phone_last_sim_swap_at = Column(DateTime, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    wallet = relationship("Wallet", back_populates="owner", uselist=False)
    biometric_template = relationship("BiometricTemplate", back_populates="owner", uselist=False)
    face_template = relationship("FaceTemplate", back_populates="owner", uselist=False)
    device_keys = relationship("DeviceKey", back_populates="owner")


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    balance = Column(Float, default=0.0)
    currency = Column(String, default="GMD")  # Gambian Dalasi
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="wallet")


class BiometricTemplate(Base):
    """Stores the ENCRYPTED fingerprint feature vector — never the raw image."""
    __tablename__ = "biometric_templates"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    encrypted_template = Column(LargeBinary, nullable=False)
    template_version = Column(String, default="cnn-v1")
    enrolled_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="biometric_template")


class FaceTemplate(Base):
    """Stores the ENCRYPTED facial feature embedding — never the raw photo.
    Same coursework-style matching approach as BiometricTemplate (cosine
    similarity over an embedding vector). See note in face_service.py about
    how this differs from real on-device facial matching (Face ID etc.)."""
    __tablename__ = "face_templates"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    encrypted_template = Column(LargeBinary, nullable=False)
    template_version = Column(String, default="face-embed-v1")
    enrolled_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="face_template")


class DeviceKey(Base):
    """
    A registered device public key, for genuine challenge-response auth
    (the industry-standard pattern behind FIDO2/WebAuthn/passkeys and
    hardware-backed signing generally — see main.py module docstring for
    why this is the more realistic protocol vs. centralized template
    matching). The PRIVATE key never leaves the user's device; we only
    ever see and store the public key here.
    """
    __tablename__ = "device_keys"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    device_id = Column(String, unique=True, index=True, nullable=False)
    public_key_pem = Column(String, nullable=False)
    revoked = Column(Boolean, default=False)
    registered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="device_keys")


class AuthChallenge(Base):
    """A short-lived, one-time nonce issued for the challenge-response
    protocol. Consumed (deleted/marked used) on first successful verify —
    this is what makes a captured signature useless on replay."""
    __tablename__ = "auth_challenges"

    id = Column(String, primary_key=True, default=_uuid)
    device_id = Column(String, index=True, nullable=False)
    nonce = Column(String, nullable=False)
    action = Column(String, nullable=False)  # e.g. "login", "payment:tx_id"
    issued_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)
    consumed = Column(Boolean, default=False)
