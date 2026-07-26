"""
Citizen Risk Assessment ML — storage model
==============================================
Per Citizen_Risk_Assessment_ML_Module:
  - additive only: never overwrites/modifies any existing rule-based score
  - every stored prediction includes model_version, score_timestamp,
    explanation, decision_source, input_feature_snapshot
  - side-by-side ML vs rule comparison fields for shadow rollout
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, DateTime, JSON, Text
from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class CitizenRiskPrediction(Base):
    __tablename__ = "citizen_risk_predictions"

    id = Column(String, primary_key=True, default=_uuid)

    # Opaque subject reference only — this table does not hold PII.
    subject_ref = Column(String, index=True, nullable=False)
    org_type = Column(String, nullable=False)  # BANK | POLICE | COURT | ...

    risk_score = Column(Float, nullable=False)  # authoritative score returned to caller
    risk_level = Column(String, nullable=False)  # LOW | MEDIUM | HIGH
    top_reasons = Column(JSON, nullable=False)  # [{feature, contribution}, ...]

    model_version = Column(String, nullable=False)
    decision_source = Column(String, nullable=False)  # ML | RULE_BASED_FALLBACK | BOTH

    input_feature_snapshot = Column(JSON, nullable=False)
    score_timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Side-by-side / safety audit fields
    ml_score = Column(Float, nullable=True)
    rule_score = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    rollout_mode = Column(String, nullable=True)  # DISABLED | SHADOW | ML_ASSISTED
    fallback_reason = Column(Text, nullable=True)
    model_metrics = Column(JSON, nullable=True)
