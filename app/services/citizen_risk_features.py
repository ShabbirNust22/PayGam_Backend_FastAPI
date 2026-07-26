"""Feature vector helpers for the Citizen Risk Assessment ML module."""

from app.schemas.citizen_risk import CitizenRiskFeatures

FEATURE_NAMES = [
    "late_payments",
    "overdue_services",
    "service_requests_30d",
    "distinct_locations_30d",
    "compliance_flags",
    "pin_failed_attempts",
    "phone_sim_swap_recent",
]

FEATURE_LABELS = {
    "late_payments": "Late payments",
    "overdue_services": "Overdue services",
    "service_requests_30d": "Service requests (30 days)",
    "distinct_locations_30d": "Distinct locations (30 days)",
    "compliance_flags": "Compliance flags",
    "pin_failed_attempts": "Failed PIN attempts",
    "phone_sim_swap_recent": "Recent SIM swap",
}


def to_feature_vector(features: CitizenRiskFeatures) -> list[float]:
    return [
        float(features.late_payments),
        float(features.overdue_services),
        float(features.service_requests_30d),
        float(features.distinct_locations_30d),
        float(features.compliance_flags),
        float(features.pin_failed_attempts),
        float(int(features.phone_sim_swap_recent)),
    ]


def normalize_org_segment(org_type: str) -> str:
    known = {"BANK", "POLICE", "COURT"}
    key = (org_type or "").strip().upper()
    return key if key in known else "DEFAULT"
