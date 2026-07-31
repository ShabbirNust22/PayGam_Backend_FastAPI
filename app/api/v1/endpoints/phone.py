from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.phone import PhoneVerifyRequest, PhoneVerifyResult
from app.services import phone_service

router = APIRouter(prefix="/phone", tags=["Phone — Service Authenticity"])


@router.post("/verify", response_model=PhoneVerifyResult)
async def verify_phone(
    request: Request,
    payload: PhoneVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.phone_number != current_user.phone_number:
        raise HTTPException(status_code=403, detail="Phone number must match the authenticated account")

    result = await phone_service.verify_phone(payload.phone_number)
    current_user.phone_verified = result.verified
    current_user.phone_last_verified_at = datetime.now(timezone.utc)
    if result.sim_swap_recent:
        current_user.phone_last_sim_swap_at = datetime.now(timezone.utc)
    db.commit()
    return result
