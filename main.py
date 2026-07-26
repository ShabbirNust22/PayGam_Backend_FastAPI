"""
PayGam Backend — FastAPI application entrypoint
====================================================
Run locally:
    uvicorn main:app --reload

Interactive API docs (Swagger UI): http://127.0.0.1:8000/docs

------------------------------------------------------------------------
A note on the two authentication models in this codebase
------------------------------------------------------------------------
This backend implements member (fingerprint / face) authentication TWO
ways, on purpose:

1. **Centralized template matching** (`app/services/tapsign_service.py`,
   `face_service.py`) — the coursework/demo model: a feature vector is
   compared, server-side, against an encrypted enrolled template with
   cosine similarity. Simple to reason about and test, but NOT how
   production hardware-backed biometric auth actually works.

2. **Device challenge-response** (`app/services/device_auth_service.py`)
   — the realistic model, matching the public, standards-based pattern
   behind FIDO2/WebAuthn/passkeys/Secure-Enclave-style signing: the
   device holds a private key that never leaves it, the fingerprint/Face
   ID/PIN only unlocks that LOCAL key, and the backend just verifies a
   signed, one-time, action-bound challenge. No biometric data — not
   even a vector — ever reaches this server.

Both are wired up and testable. (1) is what's requested below for
"member authentication / matching customer records with their stored
fingerprints"; (2) is included because it's the technically correct
approach for anything actually handling money, and is worth migrating
toward.
"""

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import Base, engine, get_db
from app.db.migrate_citizen_risk import ensure_citizen_risk_schema
from app.api.deps import get_current_user
from app.api.v1.api import api_router
from app.api.v1.endpoints import internal_risk

# Import ALL models so they register on Base.metadata before create_all()
from app.models import user, transaction, citizen_risk, risk_monitoring  # noqa: F401
from app.models.user import User, BiometricTemplate, FaceTemplate

from app.services import tapsign_service, face_service, pin_service, phone_service
from app.services import device_auth_service, citizen_risk_service
from app.schemas.citizen_risk import CitizenRiskFeatures
from app.schemas.tapsign import TapSignVerifyResult
from app.schemas.member_auth import MemberAuthenticateRequest

Base.metadata.create_all(bind=engine)
ensure_citizen_risk_schema(engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Backend API for PayGam — e-wallet payments secured by TapSign "
        "(fingerprint biometric authorization) with EGOV identity verification. "
        "Includes Citizen Risk Assessment ML (egov-ml-engine) at POST /internal/risk-score."
    ),
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to PayGam's actual app/web origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
app.include_router(internal_risk.router)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "service": settings.PROJECT_NAME}


# ==========================================================================
# Member authentication — fingerprint testing, evaluation, protocol
# handling, and scanning
# ==========================================================================
# These are the orchestration entry points the individual routers
# (app/api/v1/endpoints/tapsign.py, face.py, pin.py, phone.py, device.py)
# call into. They live here, at the top level, so the full member-
# authentication surface is visible in one place.


def match_customer_fingerprint(db: Session, user_id: str, feature_vector: list[float],
                                liveness_score: float) -> TapSignVerifyResult:
    """
    SCANNING + MATCHING: looks up the customer's stored, encrypted
    fingerprint template by user_id and evaluates an incoming scan
    (feature_vector + liveness_score) against it.
    """
    template = db.query(BiometricTemplate).filter(BiometricTemplate.user_id == user_id).first()
    if not template:
        raise HTTPException(status_code=400, detail="No fingerprint enrolled for this customer")
    return tapsign_service.verify(template.encrypted_template, feature_vector, liveness_score)


def test_fingerprint_protocol() -> dict:
    """
    EVALUATION / TESTING: runs the challenge-response protocol
    (device_auth_service) end-to-end with a throwaway in-memory keypair
    and returns whether both the positive case (valid signature accepted)
    and the negative case (tampered nonce rejected) behaved correctly.
    Safe to call repeatedly — it never touches real customer data.
    """
    return device_auth_service.self_test()


def handle_challenge_protocol(db: Session, device_id: str, action: str):
    """
    PROTOCOL HANDLING: thin wrapper documenting/exposing the
    issue-a-challenge step of the three-step protocol (register / issue /
    verify). See app/api/v1/endpoints/device.py for the full HTTP surface
    (including verify + replay protection).
    """
    nonce = device_auth_service.generate_nonce()
    expires_at = device_auth_service.new_challenge_expiry()
    return {"device_id": device_id, "action": action, "nonce": nonce, "expires_at": expires_at.isoformat()}


def evaluate_member_authentication(
    db: Session,
    user_id: str,
    fingerprint_vector: list[float] | None = None,
    fingerprint_liveness: float | None = None,
    face_embedding: list[float] | None = None,
    face_liveness: float | None = None,
    pin: str | None = None,
    phone_number: str | None = None,
) -> dict:
    """
    Composite EVALUATION across every implemented member-authentication
    factor: fingerprint (TapSign), face, PIN, and phone/SIM authenticity —
    then feeds the outcome into the eGov Citizen Risk Assessment ML module
    so these security factors correspond to (i.e. directly inform) the
    eGov risk framework, per the requirement that they "correspond to the
    eGov framework."

    Any factor not supplied is simply skipped (this endpoint is meant to
    be called with whichever factors a given flow actually collected).
    """
    member = db.query(User).filter(User.id == user_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    results: dict = {"user_id": user_id, "factors": {}}

    if fingerprint_vector is not None and fingerprint_liveness is not None:
        try:
            fp_result = match_customer_fingerprint(db, user_id, fingerprint_vector, fingerprint_liveness)
            results["factors"]["fingerprint"] = fp_result.model_dump()
        except HTTPException as exc:
            results["factors"]["fingerprint"] = {"error": exc.detail}

    if face_embedding is not None and face_liveness is not None:
        face_template = db.query(FaceTemplate).filter(FaceTemplate.user_id == user_id).first()
        if face_template:
            face_result = face_service.verify(face_template.encrypted_template, face_embedding, face_liveness)
            results["factors"]["face"] = face_result.model_dump()
        else:
            results["factors"]["face"] = {"error": "No face enrolled for this customer"}

    pin_failed_attempts = member.pin_failed_attempts or 0
    if pin is not None:
        correct, remaining, locked, locked_until = pin_service.verify_pin(member, pin)
        db.commit()
        pin_failed_attempts = member.pin_failed_attempts or 0
        results["factors"]["pin"] = {
            "correct": correct, "attempts_remaining": remaining,
            "locked": locked, "locked_until": locked_until.isoformat() if locked_until else None,
        }

    phone_sim_swap_recent = bool(member.phone_last_sim_swap_at)
    if phone_number is not None:
        import asyncio
        phone_result = asyncio.run(phone_service.verify_phone(phone_number))
        phone_sim_swap_recent = phone_result.sim_swap_recent
        results["factors"]["phone"] = phone_result.model_dump()

    # --- Correspond to the eGov framework: feed these factors into the
    # Citizen Risk Assessment ML module as behavioral/compliance signals ---
    risk_features = CitizenRiskFeatures(
        subject_ref=user_id,
        org_type="BANK",  # PayGam operates as a licensed payment/financial service
        pin_failed_attempts=pin_failed_attempts,
        phone_sim_swap_recent=phone_sim_swap_recent,
    )
    risk_result = citizen_risk_service.score_citizen(risk_features)
    results["egov_risk_assessment"] = risk_result.model_dump()

    return results


@app.post("/api/v1/auth/member/authenticate", tags=["Member Authentication"])
def authenticate_member(
    payload: MemberAuthenticateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Composite endpoint: evaluate whichever member-authentication factors
    are supplied in the request body (fingerprint / PIN / phone — face
    omitted here for brevity, call POST /api/v1/face/verify directly for
    that factor) and return both the per-factor results and the
    resulting eGov risk assessment.
    """
    return evaluate_member_authentication(
        db, current_user.id,
        fingerprint_vector=payload.fingerprint_vector,
        fingerprint_liveness=payload.fingerprint_liveness,
        pin=payload.pin, phone_number=payload.phone_number,
    )


@app.get("/api/v1/auth/member/protocol-selftest", tags=["Member Authentication"])
def protocol_selftest():
    """TESTING/EVALUATION: exercises the challenge-response protocol with
    a throwaway keypair. Returns pass/fail for the positive and negative
    (tamper-detection) cases."""
    return test_fingerprint_protocol()
