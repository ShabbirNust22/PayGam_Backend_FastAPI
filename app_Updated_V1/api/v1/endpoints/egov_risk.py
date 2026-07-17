from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.models.citizen_risk import CitizenRiskPrediction
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
    Mirrors the spec's `POST /internal/risk-score` contract. Stores the
    prediction additively (never touches any existing rule-based score
    record) with full audit fields, then returns the same JSON shape as
    the example in Citizen_Risk_Assessment_ML_Module.pdf.
    """
    result = citizen_risk_service.score_citizen(payload)

    db.add(CitizenRiskPrediction(
        subject_ref=payload.subject_ref,
        org_type=payload.org_type,
        risk_score=result.risk_score,
        risk_level=result.risk_level,
        top_reasons=[r.model_dump() for r in result.top_reasons],
        model_version=result.model_version,
        decision_source=result.decision_source,
        input_feature_snapshot=payload.model_dump(),
    ))
    db.commit()

    return result
