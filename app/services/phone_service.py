"""
Phone service authenticity
------------------------------
Mobile money fraud very often comes through SIM-swap attacks: an attacker
gets the victim's number reassigned to a new SIM, then intercepts OTPs.
This service checks a phone number's registration status with the mobile
network operator and flags a *recent* SIM swap as a risk signal.

`call_telco_api()` is a stub with a realistic contract (the same pattern
as `egov_service.py`) — point it at a real telco/HLR-lookup provider
(e.g. an aggregator API) to go live.
"""

from datetime import datetime, timedelta, timezone

from app.schemas.phone import PhoneVerifyResult

SIM_SWAP_RISK_WINDOW_HOURS = 72


async def call_telco_api(phone_number: str) -> dict:
    # --- Real integration: call a telco / HLR-lookup provider here ---
    # async with httpx.AsyncClient() as client:
    #     resp = await client.get(f"{TELCO_API_BASE}/lookup", params={"msisdn": phone_number})
    #     return resp.json()

    # --- Mock branch until a telco provider is provisioned ---
    valid_format = phone_number.startswith("+") and len(phone_number) >= 8
    return {
        "registered": valid_format,
        "carrier": "Africell GM" if valid_format else None,
        # Demo: no swap on record. Wire this to the real provider's
        # `last_sim_change_at` field once available.
        "last_sim_swap_at": None,
    }


async def verify_phone(phone_number: str) -> PhoneVerifyResult:
    data = await call_telco_api(phone_number)

    if not data["registered"]:
        return PhoneVerifyResult(
            verified=False,
            carrier=None,
            sim_swap_recent=False,
            risk_flag=True,
            reason="Phone number not found with any carrier (mock lookup).",
        )

    sim_swap_recent = False
    if data.get("last_sim_swap_at"):
        swap_time = datetime.fromisoformat(data["last_sim_swap_at"])
        sim_swap_recent = (datetime.now(timezone.utc) - swap_time) < timedelta(hours=SIM_SWAP_RISK_WINDOW_HOURS)

    return PhoneVerifyResult(
        verified=True,
        carrier=data["carrier"],
        sim_swap_recent=sim_swap_recent,
        risk_flag=sim_swap_recent,
        reason="Recent SIM swap detected — treat as elevated risk." if sim_swap_recent else None,
    )
