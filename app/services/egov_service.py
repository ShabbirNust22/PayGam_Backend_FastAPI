"""
EGOV service layer — production-shaped HTTP client with mock only outside production.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import settings
from app.schemas.egov import EgovVerificationRequest, EgovVerificationResult

logger = logging.getLogger("egov_service")


async def call_egov_api(request: EgovVerificationRequest) -> EgovVerificationResult:
    payload = {
        "national_id_number": request.national_id_number,
        "full_name": request.full_name,
        "date_of_birth": request.date_of_birth,
    }

    if settings.EGOV_USE_MOCK:
        if settings.is_production:
            raise RuntimeError("EGOV mock mode is forbidden in production")
        mock_verified = len(request.national_id_number) >= 8
        return EgovVerificationResult(
            verified=mock_verified,
            matched_name=mock_verified,
            matched_dob=mock_verified,
            id_status="active" if mock_verified else "not_found",
            reason=None if mock_verified else "National ID not found in EGOV registry (mock response).",
        )

    headers = {"Authorization": f"Bearer {settings.EGOV_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=settings.EGOV_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{settings.EGOV_API_BASE_URL.rstrip('/')}/identity/verify",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return EgovVerificationResult(
                verified=bool(data.get("verified")),
                matched_name=bool(data.get("matched_name", data.get("verified"))),
                matched_dob=bool(data.get("matched_dob", data.get("verified"))),
                id_status=str(data.get("id_status", "unknown")),
                reason=data.get("reason"),
            )
    except httpx.HTTPError as exc:
        logger.warning("egov_api_failure reason=%s", exc)
        return EgovVerificationResult(
            verified=False,
            matched_name=False,
            matched_dob=False,
            id_status="unavailable",
            reason="EGOV identity service unavailable",
        )
