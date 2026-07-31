"""
Phone / SIM authenticity — production-shaped telco client.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.schemas.phone import PhoneVerifyResult

logger = logging.getLogger("phone_service")


async def call_telco_api(phone_number: str) -> dict:
    if settings.TELCO_USE_MOCK:
        if settings.is_production:
            raise RuntimeError("Telco mock mode is forbidden in production")
        valid_format = phone_number.startswith("+") and len(phone_number) >= 8
        return {
            "registered": valid_format,
            "carrier": "Africell GM" if valid_format else None,
            "last_sim_swap_at": None,
        }

    headers = {"Authorization": f"Bearer {settings.TELCO_API_KEY}"}
    async with httpx.AsyncClient(timeout=settings.TELCO_TIMEOUT_SECONDS) as client:
        resp = await client.get(
            f"{settings.TELCO_API_BASE_URL.rstrip('/')}/lookup",
            params={"msisdn": phone_number},
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


async def verify_phone(phone_number: str) -> PhoneVerifyResult:
    try:
        data = await call_telco_api(phone_number)
    except Exception as exc:
        logger.warning("telco_api_failure reason=%s", exc)
        return PhoneVerifyResult(
            verified=False,
            carrier=None,
            sim_swap_recent=False,
            risk_flag=True,
            reason="Telco lookup unavailable",
        )

    if not data.get("registered"):
        return PhoneVerifyResult(
            verified=False,
            carrier=None,
            sim_swap_recent=False,
            risk_flag=True,
            reason="Phone number not found with any carrier",
        )

    sim_swap_recent = False
    if data.get("last_sim_swap_at"):
        swap_time = datetime.fromisoformat(str(data["last_sim_swap_at"]).replace("Z", "+00:00"))
        if swap_time.tzinfo is None:
            swap_time = swap_time.replace(tzinfo=timezone.utc)
        window = timedelta(days=settings.TELCO_SIM_SWAP_LOOKBACK_DAYS)
        sim_swap_recent = (datetime.now(timezone.utc) - swap_time) < window

    return PhoneVerifyResult(
        verified=True,
        carrier=data.get("carrier"),
        sim_swap_recent=sim_swap_recent,
        risk_flag=sim_swap_recent,
        reason="Recent SIM swap detected — treat as elevated risk." if sim_swap_recent else None,
    )
