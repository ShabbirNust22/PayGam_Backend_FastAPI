from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.transaction import TransactionStatus, TransactionType
from app.schemas.tapsign import TapSignVerifyRequest


class PaymentRequest(BaseModel):
    """A payment/send-money request authorized via a TapSign fingerprint tap."""

    receiver_phone_number: str
    amount: Decimal = Field(..., gt=0, max_digits=18, decimal_places=2)
    type: TransactionType = TransactionType.SEND
    tapsign: TapSignVerifyRequest


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: TransactionType
    amount: Decimal
    currency: str
    status: TransactionStatus
    risk_score: Decimal | float | None
    tapsign_verified: str | None
    idempotency_key: str | None = None
