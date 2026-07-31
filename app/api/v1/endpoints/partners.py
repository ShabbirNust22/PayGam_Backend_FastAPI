"""Internal partner feed ingestion for citizen-risk features."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_internal_service_key
from app.db.database import get_db
from app.models.citizen_risk import PartnerRiskEvent
from app.schemas.citizen_risk import CitizenRiskScoreOut
from app.schemas.partner import PartnerEventIn, PartnerEventOut, PartnerFeatureBuildRequest
from app.services import citizen_risk_service
from app.services.partner_feature_builder import build_features_from_partners, ingest_partner_event

router = APIRouter(tags=["Internal — Partner Feeds"])


@router.post(
    "/internal/partners/{partner_code}/events",
    response_model=PartnerEventOut,
    dependencies=[Depends(require_internal_service_key)],
)
def ingest_event(partner_code: str, payload: PartnerEventIn, db: Session = Depends(get_db)):
    existing = db.query(PartnerRiskEvent).filter(PartnerRiskEvent.event_id == payload.event_id).first()
    if existing:
        return PartnerEventOut(status="recorded", event_id=existing.event_id, duplicate=True)
    row = ingest_partner_event(
        db,
        event_id=payload.event_id,
        partner_code=partner_code,
        subject_ref=payload.subject_ref,
        event_type=payload.event_type,
        occurred_at=payload.occurred_at,
        payload=payload.payload,
    )
    return PartnerEventOut(status="recorded", event_id=row.event_id, duplicate=False)


@router.post(
    "/internal/partners/features/build",
    dependencies=[Depends(require_internal_service_key)],
)
def build_and_optional_score(payload: PartnerFeatureBuildRequest, db: Session = Depends(get_db)):
    features = build_features_from_partners(
        db,
        subject_ref=payload.subject_ref,
        org_type=payload.org_type,
        window_days=payload.window_days,
    )
    if not payload.score:
        return {"features": features.model_dump()}
    result: CitizenRiskScoreOut = citizen_risk_service.score_and_persist(features, db)
    return result
