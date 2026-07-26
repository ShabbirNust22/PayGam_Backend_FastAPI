from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.user import User, Wallet
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.schemas.transaction import PaymentRequest, TransactionOut
from app.services import tapsign_service, risk_service, risk_monitoring_service

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
):
    """
    End-to-end payment flow:
      1. Verify the TapSign fingerprint tap (liveness + template match).
      2. Score the transaction for fraud risk.
      3. Authorize / flag for review / block accordingly.
      4. Move funds and record the transaction.
    """
    # --- Step 1: TapSign biometric authorization ---
    template = db.query(User).filter(User.id == current_user.id).first().biometric_template
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

    # Monitoring-only: record the approval outcome for the TapSign risk
    # dashboard. This NEVER influences the decision above — it's a
    # side-channel observation, per TapSign_ML.pdf's "monitoring only" rule.
    risk_monitoring_service.emit_event(
        db,
        event_type="approval_consumed" if tapsign_status == "match" else "approval_denied",
        subject_ref=current_user.id,
        metadata={"tapsign_status": tapsign_status, "context": "payment"},
    )

    if tapsign_status != "match":
        _record_failed_transaction(db, current_user.id, payload, tapsign_status)
        raise HTTPException(status_code=403, detail=f"TapSign authorization failed: {tapsign_result.reason}")

    # --- Step 2: receiver + balance checks ---
    receiver = db.query(User).filter(User.phone_number == payload.receiver_phone_number).first()
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")

    sender_wallet = db.query(Wallet).filter(Wallet.user_id == current_user.id).first()
    if sender_wallet.balance < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # --- Step 3: risk scoring ---
    recent_tx_count = (
        db.query(Transaction)
        .filter(Transaction.sender_id == current_user.id)
        .count()
    )  # simplified: a real system would filter to the last 1h window
    is_new_receiver = (
        db.query(Transaction)
        .filter(Transaction.sender_id == current_user.id, Transaction.receiver_id == receiver.id)
        .first()
        is None
    )
    risk_score = risk_service.score_transaction(
        amount=payload.amount,
        sender_recent_tx_count_1h=recent_tx_count,
        is_new_receiver=is_new_receiver,
    )
    decision = risk_service.decision_for_score(risk_score)

    tx = Transaction(
        sender_id=current_user.id,
        receiver_id=receiver.id,
        type=payload.type,
        amount=payload.amount,
        risk_score=risk_score,
        tapsign_verified=tapsign_status,
        status=TransactionStatus.PENDING,
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
        return tx  # funds NOT moved yet — held pending manual/automated review

    # --- Step 4: authorized — move funds ---
    receiver_wallet = db.query(Wallet).filter(Wallet.user_id == receiver.id).first()
    sender_wallet.balance -= payload.amount
    receiver_wallet.balance += payload.amount

    tx.status = TransactionStatus.COMPLETED
    tx.completed_at = datetime.now(timezone.utc)
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def _record_failed_transaction(db: Session, sender_id: str, payload: PaymentRequest, tapsign_status: str):
    receiver = db.query(User).filter(User.phone_number == payload.receiver_phone_number).first()
    tx = Transaction(
        sender_id=sender_id,
        receiver_id=receiver.id if receiver else None,
        type=payload.type,
        amount=payload.amount,
        status=TransactionStatus.FAILED,
        tapsign_verified=tapsign_status,
    )
    db.add(tx)
    db.commit()
