"""
EGOV service layer
---------------------
Wraps calls to the (external, government-operated) EGOV identity
verification API. PayGam does not own or store the authoritative
citizen record — it submits a verification request and receives a
verified/not-verified decision plus the fields needed for KYC.

`call_egov_api()` below is a stub with the real, documented request/
response contract, so it can be pointed at the live EGOV endpoint by
filling in `settings.EGOV_API_BASE_URL` / `settings.EGOV_API_KEY` and
removing the mock branch.
"""

import httpx

from app.core.config import settings
from app.schemas.egov import EgovVerificationRequest, EgovVerificationResult


async def call_egov_api(request: EgovVerificationRequest) -> EgovVerificationResult:
    payload = {
        "national_id_number": request.national_id_number,
        "full_name": request.full_name,
        "date_of_birth": request.date_of_birth,
    }
    headers = {"Authorization": f"Bearer {settings.EGOV_API_KEY}"}

    # --- Real integration (uncomment once EGOV credentials are provisioned) ---
    # async with httpx.AsyncClient(timeout=settings.EGOV_TIMEOUT_SECONDS) as client:
    #     resp = await client.post(
    #         f"{settings.EGOV_API_BASE_URL}/identity/verify",
    #         json=payload,
    #         headers=headers,
    #     )
    #     resp.raise_for_status()
    #     data = resp.json()
    #     return EgovVerificationResult(**data)

    # --- Mock branch: used until the government API is provisioned/whitelisted ---
    mock_verified = len(request.national_id_number) >= 8
    return EgovVerificationResult(
        verified=mock_verified,
        matched_name=mock_verified,
        matched_dob=mock_verified,
        id_status="active" if mock_verified else "not_found",
        reason=None if mock_verified else "National ID not found in EGOV registry (mock response).",
    )
