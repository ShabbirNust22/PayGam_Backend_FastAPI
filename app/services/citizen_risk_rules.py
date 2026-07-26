"""Deterministic rule-based risk baseline (existing eGov-style fixed rules)."""

from app.schemas.citizen_risk import CitizenRiskFeatures, RiskReason
from app.services.citizen_risk_features import FEATURE_LABELS


def rule_based_score(features: CitizenRiskFeatures) -> tuple[float, list[RiskReason]]:
    """Transparent fixed-rule score used as the safety net / shadow authority."""
    score = 0.0
    reasons: list[RiskReason] = []

    if features.late_payments >= 5:
        score += 0.35
        reasons.append(RiskReason(feature=FEATURE_LABELS["late_payments"], contribution=0.35))
    elif features.late_payments >= 2:
        score += 0.15
        reasons.append(RiskReason(feature=FEATURE_LABELS["late_payments"], contribution=0.15))

    if features.overdue_services >= 3:
        score += 0.25
        reasons.append(RiskReason(feature=FEATURE_LABELS["overdue_services"], contribution=0.25))

    if features.compliance_flags >= 1:
        score += 0.20
        reasons.append(RiskReason(feature=FEATURE_LABELS["compliance_flags"], contribution=0.20))

    if features.pin_failed_attempts >= 3:
        score += 0.15
        reasons.append(RiskReason(feature=FEATURE_LABELS["pin_failed_attempts"], contribution=0.15))

    if features.phone_sim_swap_recent:
        score += 0.25
        reasons.append(RiskReason(feature=FEATURE_LABELS["phone_sim_swap_recent"], contribution=0.25))

    if features.distinct_locations_30d >= 8:
        score += 0.10
        reasons.append(RiskReason(feature=FEATURE_LABELS["distinct_locations_30d"], contribution=0.10))

    reasons.sort(key=lambda r: abs(r.contribution), reverse=True)
    return min(round(score, 4), 1.0), reasons[:3]
