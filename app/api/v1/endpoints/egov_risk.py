from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.citizen_risk import CitizenRiskFeatures, CitizenRiskScoreOut
from app.services import citizen_risk_service

router = APIRouter(prefix="/egov/risk-score", tags=["eGov — Citizen Risk Assessment ML"])


@router.post("", response_model=CitizenRiskScoreOut)
def score_citizen(
    payload: CitizenRiskFeatures,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Compatibility wrapper around the internal risk-score contract.
    JWT-protected for interactive /docs use. Prefer POST /internal/risk-score
    for Java service-to-service callers.
    """
    _ = current_user
    return citizen_risk_service.score_and_persist(payload, db)
