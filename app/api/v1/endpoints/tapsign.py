from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.user import User, BiometricTemplate
from app.schemas.tapsign import TapSignEnrollRequest, TapSignVerifyRequest, TapSignVerifyResult
from app.services import tapsign_service

router = APIRouter(prefix="/tapsign", tags=["TapSign — Biometric Auth"])


@router.post("/enroll", status_code=201)
def enroll(
    payload: TapSignEnrollRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Register a fingerprint for the authenticated user. `feature_vector` is
    produced client-side by the CNN feature extractor — the raw fingerprint
    image never reaches this endpoint.
    """
    existing = db.query(BiometricTemplate).filter(BiometricTemplate.user_id == current_user.id).first()
    encrypted = tapsign_service.enroll_template(payload.feature_vector)

    if existing:
        existing.encrypted_template = encrypted
    else:
        db.add(BiometricTemplate(user_id=current_user.id, encrypted_template=encrypted))

    current_user.tapsign_enrolled = True
    db.commit()
    return {"status": "enrolled"}


@router.post("/verify", response_model=TapSignVerifyResult)
def verify(
    payload: TapSignVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Verify a one-tap fingerprint scan against the user's enrolled template.
    This is the check that gates a payment authorization (see payments.py).
    """
    template = db.query(BiometricTemplate).filter(BiometricTemplate.user_id == current_user.id).first()
    if not template:
        raise HTTPException(status_code=400, detail="No fingerprint enrolled for this account")

    return tapsign_service.verify(
        stored_encrypted_template=template.encrypted_template,
        incoming_vector=payload.feature_vector,
        liveness_score=payload.liveness_score,
    )
