"""
TapSign ML Monitoring — storage models
==========================================
Per `TapSign_ML.pdf` (monitoring build manifest). THE ONE RULE THAT
OVERRIDES EVERYTHING: this layer is monitoring & analytics only. It never
blocks, never enforces, never writes to trust/wallet/approval state — it
only appends events and raises alerts for the tenant (PayGam) to act on.

- device/subject refs only, no PII, no secrets
- append-only event log
- alerts are advisory records, not actions
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, JSON, Boolean
from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class RiskEvent(Base):
    """Append-only. One row per source event (login, approval requested/
    consumed/denied, recovery attempt, identity-verification attempt,
    device bind/unbind, tapsign enable/disable, sensitive operation)."""
    __tablename__ = "risk_events"

    id = Column(String, primary_key=True, default=_uuid)
    tenant_id = Column(String, index=True, nullable=False, default="paygam")
    device_ref = Column(String, index=True, nullable=True)
    subject_ref = Column(String, index=True, nullable=True)  # opaque, not PII
    event_type = Column(String, index=True, nullable=False)
    metadata_json = Column(JSON, nullable=True)  # counts/flags only — no PII/secrets
    occurred_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RiskAlert(Base):
    """An advisory alert raised by a rule monitor. Never blocks anything —
    it's insight for the tenant admin to act on (or not)."""
    __tablename__ = "risk_alerts"

    id = Column(String, primary_key=True, default=_uuid)
    tenant_id = Column(String, index=True, nullable=False, default="paygam")
    monitor = Column(String, index=True, nullable=False)  # e.g. "tapsign_bypass"
    subject_ref = Column(String, index=True, nullable=True)
    device_ref = Column(String, index=True, nullable=True)
    severity = Column(String, default="INFO")  # INFO | WARNING | HIGH
    message = Column(String, nullable=False)
    details = Column(JSON, nullable=True)
    acknowledged = Column(Boolean, default=False)
    raised_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
