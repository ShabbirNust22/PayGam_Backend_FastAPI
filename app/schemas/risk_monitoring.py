from pydantic import BaseModel, ConfigDict


class RiskEventIn(BaseModel):
    """Generic event ingestion — mirrors RiskEventV1 in the manifest.
    device_ref/subject_ref are opaque references only, never PII."""
    device_ref: str | None = None
    subject_ref: str | None = None
    event_type: str
    metadata: dict = {}


class RiskAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    monitor: str
    subject_ref: str | None
    device_ref: str | None
    severity: str
    message: str
    details: dict | None
    acknowledged: bool


class DeviceAggregationOut(BaseModel):
    device_ref: str
    login_attempts: int
    approvals_requested: int
    approvals_consumed: int
    approvals_denied: int
    recovery_attempts: int
    identity_verify_attempts: int
