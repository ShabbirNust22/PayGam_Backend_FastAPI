"""
Citizen Risk Assessment ML module — public orchestrator
=========================================================
Scores a subject using org-segmented Logistic Regression alongside the
fixed-rule baseline, applies rollout policy, and optionally persists an
additive audit row. Never overwrites existing CitizenCreditScore data.
"""

from sqlalchemy.orm import Session

from app.models.citizen_risk import CitizenRiskPrediction
from app.schemas.citizen_risk import CitizenRiskFeatures, CitizenRiskScoreOut
from app.services.citizen_risk_policy import decide


def score_citizen(features: CitizenRiskFeatures) -> CitizenRiskScoreOut:
    """Pure scoring — no DB side effects."""
    return decide(features).response


def score_and_persist(features: CitizenRiskFeatures, db: Session) -> CitizenRiskScoreOut:
    """
    Score then append an audit prediction. Additive only — does not touch
    any existing rule-based credit-score records.
    """
    bundle = decide(features)
    result = bundle.response
    db.add(
        CitizenRiskPrediction(
            subject_ref=features.subject_ref,
            org_type=features.org_type,
            risk_score=result.risk_score,
            risk_level=result.risk_level.value if hasattr(result.risk_level, "value") else result.risk_level,
            top_reasons=[r.model_dump() for r in result.top_reasons],
            model_version=result.model_version,
            decision_source=result.decision_source.value if hasattr(result.decision_source, "value") else result.decision_source,
            input_feature_snapshot=features.model_dump(),
            ml_score=bundle.ml_score,
            rule_score=bundle.rule_score,
            confidence=bundle.confidence,
            rollout_mode=bundle.rollout_mode.value if bundle.rollout_mode else None,
            fallback_reason=bundle.fallback_reason,
            model_metrics=bundle.model_metrics.model_dump() if bundle.model_metrics else None,
        )
    )
    db.commit()
    return result
