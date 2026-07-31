"""Aggregate partner events into CitizenRiskFeatures snapshots."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.citizen_risk import PartnerRiskEvent
from app.models.user import User
from app.schemas.citizen_risk import CitizenRiskFeatures

LATE_PAYMENT_EVENTS = {"payment_overdue", "loan_arrears", "missed_installment"}
OVERDUE_SERVICE_EVENTS = {"utility_overdue", "license_expired", "service_arrears"}
SERVICE_REQUEST_EVENTS = {"service_request_opened", "service_ticket_created"}
LOCATION_EVENTS = {"location_checkin", "branch_visit", "agent_visit"}
COMPLIANCE_EVENTS = {"compliance_flag", "kyc_fail", "sanctions_hit", "enforcement_flag"}
SIM_SWAP_EVENTS = {"sim_swap", "number_reassigned"}


def ingest_partner_event(
    db: Session,
    *,
    event_id: str,
    partner_code: str,
    subject_ref: str,
    event_type: str,
    occurred_at: datetime,
    payload: dict | None = None,
) -> PartnerRiskEvent:
    existing = db.query(PartnerRiskEvent).filter(PartnerRiskEvent.event_id == event_id).first()
    if existing:
        return existing
    row = PartnerRiskEvent(
        event_id=event_id,
        partner_code=partner_code.upper(),
        subject_ref=subject_ref,
        event_type=event_type,
        occurred_at=occurred_at if occurred_at.tzinfo else occurred_at.replace(tzinfo=timezone.utc),
        payload=payload or {},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def build_features_from_partners(
    db: Session,
    subject_ref: str,
    org_type: str = "BANK",
    window_days: int = 30,
) -> CitizenRiskFeatures:
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    events = (
        db.query(PartnerRiskEvent)
        .filter(PartnerRiskEvent.subject_ref == subject_ref, PartnerRiskEvent.occurred_at >= since)
        .all()
    )

    late_payments = sum(1 for e in events if e.event_type in LATE_PAYMENT_EVENTS)
    overdue_services = sum(1 for e in events if e.event_type in OVERDUE_SERVICE_EVENTS)
    service_requests_30d = sum(1 for e in events if e.event_type in SERVICE_REQUEST_EVENTS)
    locations = {
        str((e.payload or {}).get("location") or (e.payload or {}).get("district") or e.id)
        for e in events
        if e.event_type in LOCATION_EVENTS
    }
    compliance_flags = sum(1 for e in events if e.event_type in COMPLIANCE_EVENTS)
    sim_swap_recent = any(e.event_type in SIM_SWAP_EVENTS for e in events)

    pin_failed_attempts = 0
    user = db.query(User).filter(User.id == subject_ref).first()
    if user:
        pin_failed_attempts = user.pin_failed_attempts or 0
        if user.phone_last_sim_swap_at:
            sim_swap_recent = True

    return CitizenRiskFeatures(
        subject_ref=subject_ref,
        org_type=org_type,
        late_payments=late_payments,
        overdue_services=overdue_services,
        service_requests_30d=service_requests_30d,
        distinct_locations_30d=max(len(locations), 1),
        compliance_flags=compliance_flags,
        pin_failed_attempts=pin_failed_attempts,
        phone_sim_swap_recent=sim_swap_recent,
    )
