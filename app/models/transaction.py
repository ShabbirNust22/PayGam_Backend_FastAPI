import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import relationship

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    REQUIRES_REVIEW = "requires_review"
    BLOCKED = "blocked"
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

    type = Column(Enum(TransactionType, name="transaction_type", native_enum=False), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String, default="GMD")

    status = Column(
        Enum(TransactionStatus, name="transaction_status", native_enum=False),
        default=TransactionStatus.PENDING,
    )
    risk_score = Column(Numeric(8, 4), nullable=True)
    tapsign_verified = Column(String, nullable=True)
    idempotency_key = Column(String, unique=True, index=True, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)

    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])
