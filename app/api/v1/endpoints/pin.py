from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.pin import PinSetRequest, PinVerifyRequest, PinVerifyResult
from app.services import pin_service

router = APIRouter(prefix="/pin", tags=["PIN — Accountability"])


@router.post("/set", status_code=201)
def set_pin(
    payload: PinSetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.pin_hash = pin_service.hash_pin(payload.pin)
    current_user.pin_failed_attempts = 0
    current_user.pin_locked_until = None
    db.commit()
    return {"status": "pin_set"}


@router.post("/verify", response_model=PinVerifyResult)
def verify_pin(
    payload: PinVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    correct, attempts_remaining, locked, locked_until = pin_service.verify_pin(current_user, payload.pin)
    db.commit()

    return PinVerifyResult(
        correct=correct,
        attempts_remaining=attempts_remaining,
        locked=locked,
        locked_until=locked_until.isoformat() if locked_until else None,
    )
