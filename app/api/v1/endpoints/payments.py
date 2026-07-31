from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.database import get_db
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User, Wallet
from app.schemas.transaction import PaymentRequest, TransactionOut
from app.services import risk_monitoring_service, risk_service, tapsign_service

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.get("/wallet")
def get_wallet(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    wallet = db.query(Wallet).filter(Wallet.user_id == current_user.id).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return {"balance": wallet.balance, "currency": wallet.currency}


@router.post("/send", response_model=TransactionOut)
def send_money(
    payload: PaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if settings.PAYMENTS_REQUIRE_EGOV_VERIFIED and not current_user.egov_verified:
        raise HTTPException(status_code=403, detail="EGOV verification required before sending money")

    if idempotency_key:
        existing = db.query(Transaction).filter(Transaction.idempotency_key == idempotency_key).first()
        if existing:
            return existing

    template = current_user.biometric_template
    if not template:
        raise HTTPException(status_code=400, detail="TapSign not enrolled for this account")

    tapsign_result = tapsign_service.verify(
        stored_encrypted_template=template.encrypted_template,
        incoming_vector=payload.tapsign.feature_vector,
        liveness_score=payload.tapsign.liveness_score,
    )

    if not tapsign_result.liveness_passed:
        tapsign_status = "liveness_failed"
    elif not tapsign_result.match:
        tapsign_status = "no_match"
    else:
        tapsign_status = "match"

    risk_monitoring_service.emit_event(
        db,
        event_type="approval_consumed" if tapsign_status == "match" else "approval_denied",
        subject_ref=current_user.id,
        metadata={"tapsign_status": tapsign_status, "context": "payment"},
    )

    if tapsign_status != "match":
        _record_failed_transaction(db, current_user.id, payload, tapsign_status, idempotency_key)
        raise HTTPException(status_code=403, detail="TapSign authorization failed")

    receiver = db.query(User).filter(User.phone_number == payload.receiver_phone_number).first()
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")
    if receiver.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot send money to yourself")

    amount = Decimal(payload.amount)
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    recent_tx_count = (
        db.query(Transaction)
        .filter(Transaction.sender_id == current_user.id, Transaction.created_at >= since)
        .count()
    )
    is_new_receiver = (
        db.query(Transaction)
        .filter(Transaction.sender_id == current_user.id, Transaction.receiver_id == receiver.id)
        .first()
        is None
    )
    risk_score = risk_service.score_transaction(
        amount=float(amount),
        sender_recent_tx_count_1h=recent_tx_count,
        is_new_receiver=is_new_receiver,
    )
    decision = risk_service.decision_for_score(risk_score)

    # Lock wallets in stable order to avoid deadlocks.
    wallet_ids = sorted([current_user.id, receiver.id])
    wallets = {
        w.user_id: w
        for w in db.query(Wallet)
        .filter(Wallet.user_id.in_(wallet_ids))
        .with_for_update()
        .all()
    }
    sender_wallet = wallets.get(current_user.id)
    receiver_wallet = wallets.get(receiver.id)
    if not sender_wallet or not receiver_wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    if Decimal(sender_wallet.balance) < amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    tx = Transaction(
        sender_id=current_user.id,
        receiver_id=receiver.id,
        type=payload.type,
        amount=amount,
        risk_score=risk_score,
        tapsign_verified=tapsign_status,
        status=TransactionStatus.PENDING,
        idempotency_key=idempotency_key,
    )

    if decision == "blocked":
        tx.status = TransactionStatus.BLOCKED
        db.add(tx)
        db.commit()
        db.refresh(tx)
        raise HTTPException(status_code=403, detail="Transaction blocked by fraud risk model")

    if decision == "requires_review":
        tx.status = TransactionStatus.REQUIRES_REVIEW
        db.add(tx)
        db.commit()
        db.refresh(tx)
        return tx

    sender_wallet.balance = Decimal(sender_wallet.balance) - amount
    receiver_wallet.balance = Decimal(receiver_wallet.balance) + amount
    sender_wallet.updated_at = datetime.now(timezone.utc)
    receiver_wallet.updated_at = datetime.now(timezone.utc)

    tx.status = TransactionStatus.COMPLETED
    tx.completed_at = datetime.now(timezone.utc)
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def _record_failed_transaction(
    db: Session,
    sender_id: str,
    payload: PaymentRequest,
    tapsign_status: str,
    idempotency_key: str | None,
):
    receiver = db.query(User).filter(User.phone_number == payload.receiver_phone_number).first()
    tx = Transaction(
        sender_id=sender_id,
        receiver_id=receiver.id if receiver else None,
        type=payload.type,
        amount=Decimal(payload.amount),
        status=TransactionStatus.FAILED,
        tapsign_verified=tapsign_status,
        idempotency_key=idempotency_key,
    )
    db.add(tx)
    db.commit()
