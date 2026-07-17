import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    AUTHORIZED = "authorized"        # TapSign passed, risk score OK
    REQUIRES_REVIEW = "requires_review"  # risk score borderline
    BLOCKED = "blocked"              # risk score too high, or TapSign failed
    COMPLETED = "completed"
    FAILED = "failed"


class TransactionType(str, enum.Enum):
    TOPUP = "topup"
    SEND = "send"
    PAYMENT = "payment"
    WITHDRAWAL = "withdrawal"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True, default=_uuid)
    sender_id = Column(String, ForeignKey("users.id"), nullable=True)
    receiver_id = Column(String, ForeignKey("users.id"), nullable=True)

    type = Column(Enum(TransactionType), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="GMD")

    status = Column(Enum(TransactionStatus), default=TransactionStatus.PENDING)
    risk_score = Column(Float, nullable=True)
    tapsign_verified = Column(String, nullable=True)  # "match" | "no_match" | "liveness_failed" | None

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])
