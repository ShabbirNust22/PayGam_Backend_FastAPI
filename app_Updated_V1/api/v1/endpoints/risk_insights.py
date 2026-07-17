from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.risk_monitoring import RiskAlert
from app.schemas.risk_monitoring import RiskEventIn, RiskAlertOut, DeviceAggregationOut
from app.services import risk_monitoring_service

router = APIRouter(prefix="/risk-insights", tags=["TapSign — Risk Monitoring (analytics only)"])


@router.post("/events", status_code=201)
def ingest_event(payload: RiskEventIn, db: Session = Depends(get_db)):
    """
    Connector-delivered event ingestion (per manifest item #1/#7). Purely
    additive: appends an event, then runs the read-only rule monitors.
    Never returns anything that blocks the caller's action.
    """
    event = risk_monitoring_service.emit_event(
        db, event_type=payload.event_type, device_ref=payload.device_ref,
        subject_ref=payload.subject_ref, metadata=payload.metadata,
    )
    alerts = risk_monitoring_service.run_all_monitors_for_event(db, event)
    return {"status": "recorded", "event_id": event.id, "alerts_raised": len(alerts)}


@router.get("/aggregations/{device_ref}", response_model=DeviceAggregationOut)
def get_aggregations(device_ref: str, window_hours: int = 24, db: Session = Depends(get_db)):
    return risk_monitoring_service.aggregate_for_device(db, device_ref, window_hours)


@router.get("/alerts", response_model=list[RiskAlertOut])
def list_alerts(acknowledged: bool | None = None, db: Session = Depends(get_db)):
    q = db.query(RiskAlert)
    if acknowledged is not None:
        q = q.filter(RiskAlert.acknowledged == acknowledged)
    return q.order_by(RiskAlert.raised_at.desc()).limit(100).all()
