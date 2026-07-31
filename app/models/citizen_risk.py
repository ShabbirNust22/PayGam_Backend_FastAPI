"""
Citizen Risk Assessment ML — storage model
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


JsonType = JSON().with_variant(JSONB(), "postgresql")


class CitizenRiskPrediction(Base):
    __tablename__ = "citizen_risk_predictions"

    id = Column(String, primary_key=True, default=_uuid)
    subject_ref = Column(String, index=True, nullable=False)
    org_type = Column(String, nullable=False)

    risk_score = Column(Float, nullable=False)
    risk_level = Column(String, nullable=False)
    top_reasons = Column(JsonType, nullable=False)

    model_version = Column(String, nullable=False)
    decision_source = Column(String, nullable=False)

    input_feature_snapshot = Column(JsonType, nullable=False)
    score_timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    ml_score = Column(Float, nullable=True)
    rule_score = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    rollout_mode = Column(String, nullable=True)
    fallback_reason = Column(Text, nullable=True)
    model_metrics = Column(JsonType, nullable=True)


class PartnerRiskEvent(Base):
    """Append-only partner feed events used to build citizen-risk features."""

    __tablename__ = "partner_risk_events"

    id = Column(String, primary_key=True, default=_uuid)
    event_id = Column(String, unique=True, index=True, nullable=False)
    partner_code = Column(String, index=True, nullable=False)
    subject_ref = Column(String, index=True, nullable=False)
    event_type = Column(String, index=True, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    payload = Column(JsonType, nullable=False, default=dict)
    received_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
