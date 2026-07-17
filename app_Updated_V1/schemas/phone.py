from pydantic import BaseModel


class PhoneVerifyRequest(BaseModel):
    phone_number: str


class PhoneVerifyResult(BaseModel):
    verified: bool
    carrier: str | None
    sim_swap_recent: bool
    risk_flag: bool
    reason: str | None = None
