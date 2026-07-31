"""
PayGam Backend — FastAPI application entrypoint
====================================================
Run locally:
    uvicorn main:app --reload

Interactive API docs (Swagger UI): http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.deps import get_current_user
from app.api.v1.api import api_router
from app.api.v1.endpoints import internal_risk, partners
from app.core.config import settings
from app.db.database import check_db_connection, get_db, init_db_for_dev_or_test
from app.models import user, transaction, citizen_risk, risk_monitoring  # noqa: F401
from app.models.user import BiometricTemplate, FaceTemplate, User
from app.schemas.citizen_risk import CitizenRiskFeatures
from app.schemas.member_auth import MemberAuthenticateRequest
from app.schemas.tapsign import TapSignVerifyResult
from app.services import citizen_risk_service, device_auth_service, face_service, phone_service, pin_service, tapsign_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("paygam")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.validate_for_environment()
    if not settings.is_production:
        init_db_for_dev_or_test()
        logger.info("dev/test schema bootstrap complete")
    else:
        logger.info("production mode — expecting Alembic migrations already applied")
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Backend API for PayGam — e-wallet payments secured by TapSign "
        "with EGOV identity verification and Citizen Risk Assessment ML."
    ),
    version="1.3.0",
    docs_url="/docs" if settings.DOCS_ENABLED and not settings.is_production else None,
    redoc_url="/redoc" if settings.DOCS_ENABLED and not settings.is_production else None,
    openapi_url="/openapi.json" if settings.DOCS_ENABLED and not settings.is_production else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
app.include_router(internal_risk.router)
app.include_router(partners.router)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "-")
    logger.exception("unhandled_error request_id=%s path=%s", request_id, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


@app.get("/health", tags=["Health"])
def health_check():
    db_ok = check_db_connection()
    status = "ok" if db_ok else "degraded"
    code = 200 if db_ok else 503
    return JSONResponse(
        status_code=code,
        content={"status": status, "service": settings.PROJECT_NAME, "database": db_ok},
    )


def match_customer_fingerprint(
    db: Session, user_id: str, feature_vector: list[float], liveness_score: float
) -> TapSignVerifyResult:
    template = db.query(BiometricTemplate).filter(BiometricTemplate.user_id == user_id).first()
    if not template:
        raise HTTPException(status_code=400, detail="No fingerprint enrolled for this customer")
    return tapsign_service.verify(template.encrypted_template, feature_vector, liveness_score)


def test_fingerprint_protocol() -> dict:
    return device_auth_service.self_test()


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
            "correct": correct,
            "attempts_remaining": remaining,
            "locked": locked,
            "locked_until": locked_until.isoformat() if locked_until else None,
        }

    phone_sim_swap_recent = bool(member.phone_last_sim_swap_at)
    if phone_number is not None:
        import asyncio

        phone_result = asyncio.run(phone_service.verify_phone(phone_number))
        phone_sim_swap_recent = phone_result.sim_swap_recent
        results["factors"]["phone"] = phone_result.model_dump()

    risk_features = CitizenRiskFeatures(
        subject_ref=user_id,
        org_type="BANK",
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
    return evaluate_member_authentication(
        db,
        current_user.id,
        fingerprint_vector=payload.fingerprint_vector,
        fingerprint_liveness=payload.fingerprint_liveness,
        pin=payload.pin,
        phone_number=payload.phone_number,
    )


@app.get("/api/v1/auth/member/protocol-selftest", tags=["Member Authentication"])
def protocol_selftest():
    if settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    return test_fingerprint_protocol()
