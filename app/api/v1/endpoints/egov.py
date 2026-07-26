from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.egov import EgovVerificationRequest, EgovVerificationResult
from app.services import egov_service

router = APIRouter(prefix="/egov", tags=["EGOV — Identity Verification"])


@router.post("/verify", response_model=EgovVerificationResult)
async def verify_identity(
    payload: EgovVerificationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cross-checks the user's declared national ID / name / DOB against the
    government EGOV registry. On success, marks the account as EGOV-verified
    (required before higher transaction limits are unlocked).
    """
    result = await egov_service.call_egov_api(payload)

    if result.verified:
        current_user.egov_verified = True
        current_user.national_id_number = payload.national_id_number
        db.commit()

    return result
