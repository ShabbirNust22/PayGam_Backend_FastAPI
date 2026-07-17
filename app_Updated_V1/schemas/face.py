from pydantic import BaseModel, Field


class FaceEnrollRequest(BaseModel):
    """`embedding` is produced by an on-device/model facial feature
    extractor — the raw photo is never sent to or stored by the backend."""
    embedding: list[float] = Field(..., min_length=64, max_length=512)


class FaceVerifyRequest(BaseModel):
    embedding: list[float] = Field(..., min_length=64, max_length=512)
    liveness_score: float = Field(..., ge=0.0, le=1.0)


class FaceVerifyResult(BaseModel):
    match: bool
    similarity: float
    liveness_passed: bool
    reason: str | None = None
