from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.user import User, DeviceKey, AuthChallenge
from app.schemas.device import (
    DeviceRegisterRequest, ChallengeRequest, ChallengeOut,
    ChallengeVerifyRequest, ChallengeVerifyResult,
)
from app.services import device_auth_service

router = APIRouter(prefix="/device", tags=["Device — Challenge-Response Protocol"])


@router.post("/register", status_code=201)
def register_device(
    payload: DeviceRegisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Register a device's PUBLIC key. The private key never leaves the device."""
    existing = db.query(DeviceKey).filter(DeviceKey.device_id == payload.device_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Device already registered")

    db.add(DeviceKey(user_id=current_user.id, device_id=payload.device_id, public_key_pem=payload.public_key_pem))
    db.commit()
    return {"status": "registered"}


@router.post("/challenge", response_model=ChallengeOut)
def issue_challenge(payload: ChallengeRequest, db: Session = Depends(get_db)):
    """Issue a one-time, action-bound nonce for the device to sign."""
    device = db.query(DeviceKey).filter(DeviceKey.device_id == payload.device_id, DeviceKey.revoked == False).first()  # noqa: E712
    if not device:
        raise HTTPException(status_code=404, detail="Unknown or revoked device")

    nonce = device_auth_service.generate_nonce()
    expires_at = device_auth_service.new_challenge_expiry()

    challenge = AuthChallenge(device_id=payload.device_id, nonce=nonce, action=payload.action, expires_at=expires_at)
    db.add(challenge)
    db.commit()
    db.refresh(challenge)

    return ChallengeOut(
        challenge_id=challenge.id, nonce=nonce, action=payload.action,
        expires_at=expires_at.isoformat(),
    )


@router.post("/verify", response_model=ChallengeVerifyResult)
def verify_challenge(payload: ChallengeVerifyRequest, db: Session = Depends(get_db)):
    """Verify the device's signature over the previously-issued nonce, then
    consume the challenge so it can never be replayed."""
    challenge = db.query(AuthChallenge).filter(AuthChallenge.id == payload.challenge_id).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Unknown challenge")
    if challenge.consumed:
        return ChallengeVerifyResult(verified=False, reason="Challenge already used (replay attempt).")
    if device_auth_service.is_expired(challenge.expires_at):
        return ChallengeVerifyResult(verified=False, reason="Challenge expired.")
    if challenge.device_id != payload.device_id:
        return ChallengeVerifyResult(verified=False, reason="Device mismatch.")

    device = db.query(DeviceKey).filter(DeviceKey.device_id == payload.device_id, DeviceKey.revoked == False).first()  # noqa: E712
    if not device:
        return ChallengeVerifyResult(verified=False, reason="Unknown or revoked device.")

    verified, reason = device_auth_service.verify_signature(device.public_key_pem, challenge.nonce, payload.signature_b64)

    # Consume regardless of outcome — a failed attempt should not be retryable
    # against the same nonce either.
    challenge.consumed = True
    db.commit()

    return ChallengeVerifyResult(verified=verified, reason=reason)


@router.get("/selftest")
def selftest():
    """Runnable evaluation of the sign/verify protocol with a throwaway
    in-memory keypair — see device_auth_service.self_test()."""
    return device_auth_service.self_test()
