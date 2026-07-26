from pydantic import BaseModel


class MemberAuthenticateRequest(BaseModel):
    fingerprint_vector: list[float] | None = None
    fingerprint_liveness: float | None = None
    pin: str | None = None
    phone_number: str | None = None
