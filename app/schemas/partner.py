from datetime import datetime

from pydantic import BaseModel, Field


class PartnerEventIn(BaseModel):
    event_id: str = Field(..., min_length=1)
    subject_ref: str = Field(..., min_length=1)
    event_type: str = Field(..., min_length=1)
    occurred_at: datetime
    payload: dict = Field(default_factory=dict)


class PartnerEventOut(BaseModel):
    status: str
    event_id: str
    duplicate: bool = False


class PartnerFeatureBuildRequest(BaseModel):
    subject_ref: str
    org_type: str = "BANK"
    window_days: int = Field(30, ge=1, le=365)
    score: bool = True
