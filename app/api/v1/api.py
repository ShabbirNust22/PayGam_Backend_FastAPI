from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth, tapsign, egov, payments,
    face, pin, phone, device, egov_risk, risk_insights,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(tapsign.router)
api_router.include_router(face.router)
api_router.include_router(pin.router)
api_router.include_router(phone.router)
api_router.include_router(device.router)
api_router.include_router(egov.router)
api_router.include_router(egov_risk.router)
api_router.include_router(payments.router)
api_router.include_router(risk_insights.router)
