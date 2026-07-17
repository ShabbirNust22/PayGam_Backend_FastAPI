from pydantic import BaseModel


class CitizenRiskFeatures(BaseModel):
    """Behavior-pattern features — matches the data sources table in the
    spec (credit/payment history, service usage, location, compliance)."""
    subject_ref: str
    org_type: str  # BANK | POLICE | COURT | ...
    late_payments: int = 0
    overdue_services: int = 0
    service_requests_30d: int = 0
    distinct_locations_30d: int = 1
    compliance_flags: int = 0
    account_age_days: int = 0
    # Optional signal from the auth factors implemented alongside this module
    pin_failed_attempts: int = 0
    phone_sim_swap_recent: bool = False


class RiskReason(BaseModel):
    feature: str
    contribution: float


class CitizenRiskScoreOut(BaseModel):
    risk_score: float
    risk_level: str          # LOW | MEDIUM | HIGH
    org_type: str
    top_reasons: list[RiskReason]
    model_version: str
    decision_source: str     # ML | RULE_BASED_FALLBACK
