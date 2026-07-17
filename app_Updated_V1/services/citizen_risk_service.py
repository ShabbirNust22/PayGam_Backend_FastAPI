"""
Citizen Risk Assessment ML module
======================================
Implements the module described in `Citizen_Risk_Assessment_ML_Module.pdf`:
a data-driven risk score that runs ALONGSIDE the existing rule-based
system (never replacing it outright), always includes a plain-English
explanation, and always falls back to the rule-based score if the model
is unavailable or unconfident. Every response is tagged with
`decision_source` so ML vs. fallback usage is fully auditable.

Baseline model: Logistic Regression (per spec §3.4). Candidate models
(Random Forest / XGBoost / LightGBM) are a drop-in swap for
`_MODEL` — the surrounding contract (features in, scored+explained
response out, safe fallback) does not change.

Explainability: per spec, every prediction needs an explanation
("SHAP or equivalent — not optional"). For this linear baseline we use
the standard, exact method for linear models — coefficient x
standardized feature value — which IS the equivalent for a logistic
regression (SHAP's `LinearExplainer` computes the same thing under the
hood). If a tree-based candidate model replaces the baseline, swap this
for `shap.TreeExplainer` — the response schema stays identical.
"""

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from app.schemas.citizen_risk import CitizenRiskFeatures, CitizenRiskScoreOut, RiskReason

MODEL_VERSION = "v1.0.0"
FEATURE_NAMES = [
    "late_payments",
    "overdue_services",
    "service_requests_30d",
    "distinct_locations_30d",
    "compliance_flags",
    "pin_failed_attempts",
    "phone_sim_swap_recent",
]

# Confidence gate: if the model's probability sits too close to 0.5 (i.e.
# it isn't really sure), fall back to the transparent rule-based score
# rather than ship a low-confidence ML number — per the spec's safety
# requirement ("never makes an unreviewed decision without a safety net").
MIN_CONFIDENCE_MARGIN = 0.08


def _make_synthetic_training_set(n: int = 2000, seed: int = 42):
    """
    No historical labeled data is wired up yet (per spec, v1 reuses
    existing platform data — that integration is the next step). This
    generates a synthetic-but-plausible training set from a known rule so
    the module is runnable and testable end-to-end today; swap for a real
    query against CitizenCreditScore/ServiceRequestEventConsumer/etc. when
    that pipeline is built.
    """
    rng = np.random.default_rng(seed)
    X = np.column_stack([
        rng.poisson(1.2, n),          # late_payments
        rng.poisson(0.8, n),          # overdue_services
        rng.poisson(4, n),            # service_requests_30d
        rng.poisson(2, n) + 1,        # distinct_locations_30d
        rng.poisson(0.5, n),          # compliance_flags
        rng.poisson(0.3, n),          # pin_failed_attempts
        rng.integers(0, 2, n),        # phone_sim_swap_recent
    ]).astype(float)

    weights = np.array([0.35, 0.30, 0.05, 0.10, 0.40, 0.20, 0.45])
    logits = X @ weights - 2.2 + rng.normal(0, 0.5, n)
    probs = 1 / (1 + np.exp(-logits))
    y = (rng.random(n) < probs).astype(int)
    return X, y


class _CitizenRiskModel:
    def __init__(self):
        X, y = _make_synthetic_training_set()
        self.scaler = StandardScaler().fit(X)
        X_scaled = self.scaler.transform(X)
        self.model = LogisticRegression().fit(X_scaled, y)

    def predict(self, feature_vector: list[float]) -> tuple[float, list[RiskReason]]:
        x = np.array(feature_vector).reshape(1, -1)
        x_scaled = self.scaler.transform(x)
        proba = float(self.model.predict_proba(x_scaled)[0, 1])

        # Linear-model exact explanation: coefficient * standardized value
        contributions = self.model.coef_[0] * x_scaled[0]
        reasons = sorted(
            (RiskReason(feature=name, contribution=round(float(c), 4))
             for name, c in zip(FEATURE_NAMES, contributions)),
            key=lambda r: abs(r.contribution),
            reverse=True,
        )[:3]
        return proba, reasons


_MODEL = _CitizenRiskModel()  # loaded once at process start


def _rule_based_score(features: CitizenRiskFeatures) -> tuple[float, list[RiskReason]]:
    """Deterministic fallback — same spirit as the existing fixed-rule
    system this module runs alongside (spec §"What This Is")."""
    score = 0.0
    reasons = []

    if features.late_payments >= 5:
        score += 0.35
        reasons.append(RiskReason(feature="late_payments", contribution=0.35))
    elif features.late_payments >= 2:
        score += 0.15
        reasons.append(RiskReason(feature="late_payments", contribution=0.15))

    if features.overdue_services >= 3:
        score += 0.25
        reasons.append(RiskReason(feature="overdue_services", contribution=0.25))

    if features.compliance_flags >= 1:
        score += 0.20
        reasons.append(RiskReason(feature="compliance_flags", contribution=0.20))

    if features.pin_failed_attempts >= 3:
        score += 0.15
        reasons.append(RiskReason(feature="pin_failed_attempts", contribution=0.15))

    if features.phone_sim_swap_recent:
        score += 0.25
        reasons.append(RiskReason(feature="phone_sim_swap_recent", contribution=0.25))

    reasons.sort(key=lambda r: r.contribution, reverse=True)
    return min(score, 1.0), reasons[:3]


def _risk_level(score: float) -> str:
    if score >= 0.7:
        return "HIGH"
    if score >= 0.4:
        return "MEDIUM"
    return "LOW"


def score_citizen(features: CitizenRiskFeatures) -> CitizenRiskScoreOut:
    feature_vector = [
        features.late_payments,
        features.overdue_services,
        features.service_requests_30d,
        features.distinct_locations_30d,
        features.compliance_flags,
        features.pin_failed_attempts,
        int(features.phone_sim_swap_recent),
    ]

    try:
        proba, reasons = _MODEL.predict(feature_vector)
        confident = abs(proba - 0.5) >= MIN_CONFIDENCE_MARGIN
        if not confident:
            raise ValueError("Low-confidence prediction — falling back to rule-based score.")
        decision_source = "ML"
        score = proba
    except Exception:
        score, reasons = _rule_based_score(features)
        decision_source = "RULE_BASED_FALLBACK"

    return CitizenRiskScoreOut(
        risk_score=round(score, 4),
        risk_level=_risk_level(score),
        org_type=features.org_type,
        top_reasons=reasons,
        model_version=MODEL_VERSION,
        decision_source=decision_source,
    )
