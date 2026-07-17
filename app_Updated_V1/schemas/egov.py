from pydantic import BaseModel


class EgovVerificationRequest(BaseModel):
    national_id_number: str
    full_name: str
    date_of_birth: str  # ISO date, e.g. "1998-04-12"


class EgovVerificationResult(BaseModel):
    verified: bool
    matched_name: bool
    matched_dob: bool
    id_status: str  # "active" | "expired" | "not_found"
    reason: str | None = None
