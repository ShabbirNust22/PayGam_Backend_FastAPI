from pydantic import BaseModel


class RiskEventIn(BaseModel):
    """Generic event ingestion — mirrors RiskEventV1 in the manifest.
    device_ref/subject_ref are opaque references only, never PII."""
    device_ref: str | None = None
    subject_ref: str | None = None
    event_type: str  # login | approval_requested | approval_consumed | approval_denied
                      # | recovery_attempt | identity_verify_attempt | device_bind
                      # | device_unbind | tapsign_enable | tapsign_disable | sensitive_operation
    metadata: dict = {}


class RiskAlertOut(BaseModel):
    id: str
    monitor: str
    subject_ref: str | None
    device_ref: str | None
    severity: str
    message: str
    details: dict | None
    acknowledged: bool

    class Config:
        from_attributes = True


class DeviceAggregationOut(BaseModel):
    device_ref: str
    login_attempts: int
    approvals_requested: int
    approvals_consumed: int
    approvals_denied: int
    recovery_attempts: int
    identity_verify_attempts: int
