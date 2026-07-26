"""
Internal Citizen Risk Assessment endpoint — egov-ml-engine sync interface.

POST /internal/risk-score
Protected by X-Internal-Service-Key for Java microservice callers.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_internal_service_key
from app.db.database import get_db
from app.schemas.citizen_risk import CitizenRiskFeatures, CitizenRiskScoreOut
from app.services import citizen_risk_service

router = APIRouter(tags=["Internal — Citizen Risk Assessment ML"])


@router.post(
    "/internal/risk-score",
    response_model=CitizenRiskScoreOut,
    dependencies=[Depends(require_internal_service_key)],
)
def internal_risk_score(
    payload: CitizenRiskFeatures,
    db: Session = Depends(get_db),
):
    """
    Spec contract: on-demand scoring for the eGov platform.
    Always returns risk_score, risk_level, org_type, top_reasons,
    model_version, decision_source. Persists an additive audit row.
    """
    return citizen_risk_service.score_and_persist(payload, db)
