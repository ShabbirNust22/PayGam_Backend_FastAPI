from pydantic import BaseModel


class DeviceRegisterRequest(BaseModel):
    """`public_key_pem` is the device's public key (Ed25519), generated
    on-device — the matching private key never leaves the device."""
    device_id: str
    public_key_pem: str


class ChallengeRequest(BaseModel):
    device_id: str
    action: str  # e.g. "login", "payment:<transaction_id>"


class ChallengeOut(BaseModel):
    challenge_id: str
    nonce: str
    action: str
    expires_at: str


class ChallengeVerifyRequest(BaseModel):
    challenge_id: str
    device_id: str
    signature_b64: str  # base64-encoded Ed25519 signature over the nonce


class ChallengeVerifyResult(BaseModel):
    verified: bool
    reason: str | None = None
