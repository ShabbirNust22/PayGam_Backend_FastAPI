"""
Citizen Risk Assessment ML — request/response contracts
=========================================================
Matches Citizen_Risk_Assessment_ML_Module: risk_score, risk_level,
org_type, top_reasons, model_version, decision_source on every response.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class DecisionSource(str, Enum):
    ML = "ML"
    RULE_BASED_FALLBACK = "RULE_BASED_FALLBACK"
    BOTH = "BOTH"


class RolloutMode(str, Enum):
    DISABLED = "DISABLED"
    SHADOW = "SHADOW"
    ML_ASSISTED = "ML_ASSISTED"


class OrgType(str, Enum):
    BANK = "BANK"
    POLICE = "POLICE"
    COURT = "COURT"
    OTHER = "OTHER"


class CitizenRiskFeatures(BaseModel):
    """Behavior-pattern features from existing eGov platform data sources
    (credit/payment history, service usage, location, compliance)."""

    subject_ref: str = Field(..., min_length=1)
    org_type: str = Field(..., min_length=1)  # BANK | POLICE | COURT | ...
    late_payments: int = Field(0, ge=0)
    overdue_services: int = Field(0, ge=0)
    service_requests_30d: int = Field(0, ge=0)
    distinct_locations_30d: int = Field(1, ge=0)
    compliance_flags: int = Field(0, ge=0)
    account_age_days: int = Field(0, ge=0)
    pin_failed_attempts: int = Field(0, ge=0)
    phone_sim_swap_recent: bool = False

    @field_validator("org_type")
    @classmethod
    def normalize_org_type(cls, value: str) -> str:
        return value.strip().upper()


class RiskReason(BaseModel):
    feature: str
    contribution: float


class ModelMetricsOut(BaseModel):
    """Development-only evaluation snapshot for the active org segment."""

    auc_roc: float | None = None
    f1: float | None = None
    brier_score: float | None = None
    training_data: str = "synthetic_dev_only"


class CitizenRiskScoreOut(BaseModel):
    risk_score: float
    risk_level: RiskLevel
    org_type: str
    top_reasons: list[RiskReason]
    model_version: str
    decision_source: DecisionSource
    # Extended audit/safety fields (backward-compatible extras)
    confidence: float | None = None
    rollout_mode: RolloutMode | None = None
    fallback_reason: str | None = None
    ml_score: float | None = None
    rule_score: float | None = None
    model_metrics: ModelMetricsOut | None = None
    development_only: bool = True


class CitizenRiskAuditRecord(BaseModel):
    """Internal shape used when persisting an additive prediction row."""

    subject_ref: str
    org_type: str
    risk_score: float
    risk_level: str
    top_reasons: list[dict[str, Any]]
    model_version: str
    decision_source: str
    input_feature_snapshot: dict[str, Any]
    ml_score: float | None = None
    rule_score: float | None = None
    confidence: float | None = None
    rollout_mode: str | None = None
    fallback_reason: str | None = None
    model_metrics: dict[str, Any] | None = None
