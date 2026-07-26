from pydantic import BaseModel, Field


class PinSetRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=6, pattern=r"^\d+$")


class PinVerifyRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=6, pattern=r"^\d+$")


class PinVerifyResult(BaseModel):
    correct: bool
    attempts_remaining: int
    locked: bool
    locked_until: str | None = None
