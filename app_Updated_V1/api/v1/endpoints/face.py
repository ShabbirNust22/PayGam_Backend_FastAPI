from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.user import User, FaceTemplate
from app.schemas.face import FaceEnrollRequest, FaceVerifyRequest, FaceVerifyResult
from app.services import face_service

router = APIRouter(prefix="/face", tags=["Face — Facial Identity Recognition"])


@router.post("/enroll", status_code=201)
def enroll(
    payload: FaceEnrollRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = db.query(FaceTemplate).filter(FaceTemplate.user_id == current_user.id).first()
    encrypted = face_service.enroll_template(payload.embedding)

    if existing:
        existing.encrypted_template = encrypted
    else:
        db.add(FaceTemplate(user_id=current_user.id, encrypted_template=encrypted))

    current_user.face_enrolled = True
    db.commit()
    return {"status": "enrolled"}


@router.post("/verify", response_model=FaceVerifyResult)
def verify(
    payload: FaceVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    template = db.query(FaceTemplate).filter(FaceTemplate.user_id == current_user.id).first()
    if not template:
        raise HTTPException(status_code=400, detail="No face enrolled for this account")

    return face_service.verify(
        stored_encrypted_template=template.encrypted_template,
        incoming_embedding=payload.embedding,
        liveness_score=payload.liveness_score,
    )
