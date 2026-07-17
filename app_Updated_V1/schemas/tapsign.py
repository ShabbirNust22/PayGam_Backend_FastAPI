from pydantic import BaseModel, Field


class TapSignEnrollRequest(BaseModel):
    """
    `feature_vector` is produced ON-DEVICE (or by the CNN feature-extraction
    service) from a fingerprint scan — the raw fingerprint image itself is
    never transmitted to or stored by the backend.
    """
    feature_vector: list[float] = Field(..., min_length=64, max_length=512)


class TapSignVerifyRequest(BaseModel):
    feature_vector: list[float] = Field(..., min_length=64, max_length=512)
    liveness_score: float = Field(..., ge=0.0, le=1.0)
    transaction_id: str | None = None


class TapSignVerifyResult(BaseModel):
    match: bool
    similarity: float
    liveness_passed: bool
    reason: str | None = None
