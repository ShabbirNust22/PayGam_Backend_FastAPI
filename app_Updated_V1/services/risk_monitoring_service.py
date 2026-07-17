"""
TapSign ML risk monitoring service
=======================================
Implements the monitoring layer from `TapSign_ML.pdf`.

THE ONE RULE THAT OVERRIDES EVERYTHING (copied here deliberately, so
anyone editing this file sees it): this module is monitoring & analytics
ONLY. Every function in this file either (a) appends a read-only event
row, (b) computes a read-only aggregation, or (c) raises an advisory
alert. NONE of them return a value that blocks, denies, or modifies
trust/approval/wallet state. Blocking decisions belong to the tenant
(PayGam's own payments/risk_service.py already does that for payments —
this module is deliberately separate from it).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.risk_monitoring import RiskEvent, RiskAlert

TENANT_ID = "paygam"

# --- 1. Event emitter (append-only) -----------------------------------

def emit_event(db: Session, event_type: str, device_ref: str | None = None,
                subject_ref: str | None = None, metadata: dict | None = None) -> RiskEvent:
    event = RiskEvent(
        tenant_id=TENANT_ID,
        device_ref=device_ref,
        subject_ref=subject_ref,
        event_type=event_type,
        metadata_json=metadata or {},
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


# --- 3. Aggregations (read-only queries) -------------------------------

def aggregate_for_device(db: Session, device_ref: str, window_hours: int = 24) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    q = db.query(RiskEvent).filter(
        RiskEvent.device_ref == device_ref,
        RiskEvent.occurred_at >= since,
    )
    events = q.all()

    def count(event_type: str) -> int:
        return sum(1 for e in events if e.event_type == event_type)

    return {
        "device_ref": device_ref,
        "login_attempts": count("login"),
        "approvals_requested": count("approval_requested"),
        "approvals_consumed": count("approval_consumed"),
        "approvals_denied": count("approval_denied"),
        "recovery_attempts": count("recovery_attempt"),
        "identity_verify_attempts": count("identity_verify_attempt"),
    }


# --- 4/5. Rule monitors (deterministic, explainable, alert-only) -------

def monitor_excessive_attempts(db: Session, device_ref: str, threshold: int = 5, window_hours: int = 1) -> RiskAlert | None:
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    attempts = db.query(RiskEvent).filter(
        RiskEvent.device_ref == device_ref,
        RiskEvent.event_type.in_(["login", "approval_requested"]),
        RiskEvent.occurred_at >= since,
    ).count()

    if attempts < threshold:
        return None

    return _raise_alert(
        db, monitor="excessive_attempts", device_ref=device_ref,
        severity="WARNING",
        message=f"{attempts} login/approval attempts from this device in the last {window_hours}h.",
        details={"attempt_count": attempts, "window_hours": window_hours},
    )


def monitor_unusual_device(db: Session, subject_ref: str, device_ref: str) -> RiskAlert | None:
    """Flags a login/approval from a device this subject hasn't used before."""
    seen_before = db.query(RiskEvent).filter(
        RiskEvent.subject_ref == subject_ref,
        RiskEvent.device_ref == device_ref,
        RiskEvent.event_type.in_(["approval_consumed", "device_bind"]),
    ).first()

    if seen_before:
        return None

    return _raise_alert(
        db, monitor="unusual_device", device_ref=device_ref, subject_ref=subject_ref,
        severity="INFO",
        message="Activity from a device not previously associated with this subject.",
        details={},
    )


def monitor_tapsign_bypass(db: Session, subject_ref: str, device_ref: str | None,
                            tapsign_enrolled: bool, had_matching_approval: bool) -> RiskAlert | None:
    """
    THE KEY MONITOR (per manifest §5). Fires when a sensitive operation
    completed for a subject who IS enrolled in TapSign, but with no
    matching approval-consumed event — i.e. the integration let it
    through without a TapSign prompt. This should be impossible if
    configured correctly; the monitor's job is to notice and report the
    configuration hole, never to block the operation itself.
    """
    if not tapsign_enrolled or had_matching_approval:
        return None

    return _raise_alert(
        db, monitor="tapsign_bypass", device_ref=device_ref, subject_ref=subject_ref,
        severity="HIGH",
        message=(
            "This account has TapSign enrolled but a sensitive operation completed "
            "without a matching TapSign approval — verify the user actually disabled "
            "it, or check the integration for a bypass path."
        ),
        details={"tapsign_enrolled": True, "had_matching_approval": False},
    )


def _raise_alert(db: Session, monitor: str, severity: str, message: str, details: dict,
                  device_ref: str | None = None, subject_ref: str | None = None) -> RiskAlert:
    alert = RiskAlert(
        tenant_id=TENANT_ID,
        monitor=monitor,
        subject_ref=subject_ref,
        device_ref=device_ref,
        severity=severity,
        message=message,
        details=details,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def run_all_monitors_for_event(db: Session, event: RiskEvent) -> list[RiskAlert]:
    """Convenience: run the relevant rule monitors after an event is emitted."""
    alerts = []
    if event.device_ref:
        alert = monitor_excessive_attempts(db, event.device_ref)
        if alert:
            alerts.append(alert)
        if event.subject_ref:
            alert = monitor_unusual_device(db, event.subject_ref, event.device_ref)
            if alert:
                alerts.append(alert)
    return alerts
