"""
Risk scoring service
-----------------------
Rule-weighted risk model for transaction screening (the "Scikit-learn
risk model" referenced in the progress report). This starts as an
interpretable weighted-rule model — the same feature set can be fed
into a trained sklearn classifier (e.g. LogisticRegression /
GradientBoostingClassifier) later without changing the API contract:
swap `score_transaction()`'s body for `model.predict_proba(features)`.
"""

from datetime import datetime, timezone

from app.core.config import settings


def score_transaction(
    amount: float,
    sender_recent_tx_count_1h: int,
    is_new_receiver: bool,
    hour_of_day: int | None = None,
) -> float:
    """Returns a risk score in [0, 1]. Higher = riskier."""
    hour_of_day = hour_of_day if hour_of_day is not None else datetime.now(timezone.utc).hour

    score = 0.0

    # Large amount relative to typical wallet usage
    if amount > 50_000:
        score += 0.45
    elif amount > 10_000:
        score += 0.25
    elif amount > 2_000:
        score += 0.10

    # Velocity — many transactions in a short window is a fraud signal
    if sender_recent_tx_count_1h >= 5:
        score += 0.30
    elif sender_recent_tx_count_1h >= 3:
        score += 0.15

    # First-time payee
    if is_new_receiver:
        score += 0.15

    # Unusual hours (late night / early morning)
    if hour_of_day < 5 or hour_of_day > 23:
        score += 0.10

    return min(round(score, 4), 1.0)


def decision_for_score(score: float) -> str:
    if score >= settings.RISK_SCORE_BLOCK_THRESHOLD:
        return "blocked"
    if score >= settings.RISK_SCORE_REVIEW_THRESHOLD:
        return "requires_review"
    return "authorized"
