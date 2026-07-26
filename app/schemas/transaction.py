from pydantic import BaseModel, Field

from app.models.transaction import TransactionStatus, TransactionType
from app.schemas.tapsign import TapSignVerifyRequest


class PaymentRequest(BaseModel):
    """A payment/send-money request authorized via a TapSign fingerprint tap."""
    receiver_phone_number: str
    amount: float = Field(..., gt=0)
    type: TransactionType = TransactionType.SEND
    tapsign: TapSignVerifyRequest


class TransactionOut(BaseModel):
    id: str
    type: TransactionType
    amount: float
    currency: str
    status: TransactionStatus
    risk_score: float | None
    tapsign_verified: str | None

    class Config:
        from_attributes = True
