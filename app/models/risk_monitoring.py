"""
TapSign ML Monitoring — storage models
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB

from app.db.database import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id = Column(String, primary_key=True, default=_uuid)
    tenant_id = Column(String, index=True, nullable=False, default="paygam")
    device_ref = Column(String, index=True, nullable=True)
    subject_ref = Column(String, index=True, nullable=True)
    event_type = Column(String, index=True, nullable=False)
    metadata_json = Column(JsonType, nullable=True)
    occurred_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class RiskAlert(Base):
    __tablename__ = "risk_alerts"

    id = Column(String, primary_key=True, default=_uuid)
    tenant_id = Column(String, index=True, nullable=False, default="paygam")
    monitor = Column(String, index=True, nullable=False)
    subject_ref = Column(String, index=True, nullable=True)
    device_ref = Column(String, index=True, nullable=True)
    severity = Column(String, default="INFO")
    message = Column(String, nullable=False)
    details = Column(JsonType, nullable=True)
    acknowledged = Column(Boolean, default=False)
    raised_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
