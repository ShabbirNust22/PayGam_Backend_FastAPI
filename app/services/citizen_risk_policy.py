"""
Rollout decision policy for Citizen Risk Assessment.

Modes:
  DISABLED     — rules only
  SHADOW       — compute ML + rules; return rule score with decision_source=BOTH
  ML_ASSISTED  — return ML when healthy/confident; otherwise rule fallback
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import settings
from app.schemas.citizen_risk import (
    CitizenRiskFeatures,
    CitizenRiskScoreOut,
    DecisionSource,
    ModelMetricsOut,
    RiskLevel,
    RiskReason,
    RolloutMode,
)
from app.services.citizen_risk_features import to_feature_vector
from app.services.citizen_risk_model import SegmentModel, get_registry
from app.services.citizen_risk_rules import rule_based_score

logger = logging.getLogger("citizen_risk")


@dataclass
class ScoreBundle:
    response: CitizenRiskScoreOut
    ml_score: float | None
    rule_score: float
    confidence: float | None
    rollout_mode: RolloutMode
    fallback_reason: str | None
    model_metrics: ModelMetricsOut | None
    model_version: str


def risk_level_for(score: float) -> RiskLevel:
    if score >= 0.7:
        return RiskLevel.HIGH
    if score >= 0.4:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _parse_rollout(org_type: str) -> RolloutMode:
    raw = settings.rollout_mode_for_org(org_type)
    try:
        return RolloutMode(raw)
    except ValueError:
        return RolloutMode.SHADOW


def _try_ml(features: CitizenRiskFeatures) -> tuple[SegmentModel | None, float | None, float | None, list[RiskReason] | None, str | None]:
    try:
        segment = get_registry().get(features.org_type)
        vector = to_feature_vector(features)
        proba, confidence, reasons = segment.predict(vector)
        return segment, proba, confidence, reasons, None
    except Exception as exc:
        logger.warning(
            "citizen_risk_ml_unavailable subject_ref=%s org_type=%s reason=%s",
            features.subject_ref,
            features.org_type,
            str(exc),
        )
        return None, None, None, None, f"ml_unavailable:{exc}"


def decide(features: CitizenRiskFeatures) -> ScoreBundle:
    rollout = _parse_rollout(features.org_type)
    # Never silently train synthetic models for assisted decisions in production.
    if settings.is_production and rollout == RolloutMode.ML_ASSISTED:
        if not get_registry().has_models() or settings.CITIZEN_RISK_DEVELOPMENT_ONLY:
            rollout = RolloutMode.SHADOW
            logger.warning(
                "citizen_risk_forced_shadow subject_ref=%s org_type=%s reason=no_prod_artifacts",
                features.subject_ref,
                features.org_type,
            )

    rule_score, rule_reasons = rule_based_score(features)
    segment, ml_score, confidence, ml_reasons, ml_error = _try_ml(features)
    model_version = segment.version if segment else "rules-only"
    metrics = segment.metrics if segment else None
    margin = settings.CITIZEN_RISK_MIN_CONFIDENCE_MARGIN

    fallback_reason: str | None = None
    decision_source: DecisionSource
    risk_score: float
    top_reasons: list[RiskReason]

    if rollout == RolloutMode.DISABLED:
        decision_source = DecisionSource.RULE_BASED_FALLBACK
        risk_score = rule_score
        top_reasons = rule_reasons
        fallback_reason = "rollout_disabled"
        logger.warning(
            "citizen_risk_fallback subject_ref=%s org_type=%s reason=%s",
            features.subject_ref,
            features.org_type,
            fallback_reason,
        )
    elif rollout == RolloutMode.SHADOW:
        # Always compute both when ML works; rules remain authoritative.
        if ml_error or ml_score is None or confidence is None:
            decision_source = DecisionSource.RULE_BASED_FALLBACK
            risk_score = rule_score
            top_reasons = rule_reasons
            fallback_reason = ml_error or "ml_unavailable"
            logger.warning(
                "citizen_risk_fallback subject_ref=%s org_type=%s reason=%s",
                features.subject_ref,
                features.org_type,
                fallback_reason,
            )
        else:
            decision_source = DecisionSource.BOTH
            risk_score = rule_score
            top_reasons = rule_reasons
            if confidence < margin:
                fallback_reason = "low_confidence_shadow"
                logger.warning(
                    "citizen_risk_low_confidence subject_ref=%s org_type=%s confidence=%.4f",
                    features.subject_ref,
                    features.org_type,
                    confidence,
                )
    else:  # ML_ASSISTED
        if ml_error or ml_score is None or confidence is None:
            decision_source = DecisionSource.RULE_BASED_FALLBACK
            risk_score = rule_score
            top_reasons = rule_reasons
            fallback_reason = ml_error or "ml_unavailable"
            logger.warning(
                "citizen_risk_fallback subject_ref=%s org_type=%s reason=%s",
                features.subject_ref,
                features.org_type,
                fallback_reason,
            )
        elif confidence < margin:
            decision_source = DecisionSource.RULE_BASED_FALLBACK
            risk_score = rule_score
            top_reasons = rule_reasons
            fallback_reason = "low_confidence"
            logger.warning(
                "citizen_risk_fallback subject_ref=%s org_type=%s reason=%s confidence=%.4f",
                features.subject_ref,
                features.org_type,
                fallback_reason,
                confidence,
            )
        else:
            decision_source = DecisionSource.ML
            risk_score = round(ml_score, 4)
            top_reasons = ml_reasons or rule_reasons

    response = CitizenRiskScoreOut(
        risk_score=round(risk_score, 4),
        risk_level=risk_level_for(risk_score),
        org_type=features.org_type,
        top_reasons=top_reasons,
        model_version=model_version,
        decision_source=decision_source,
        confidence=round(confidence, 4) if confidence is not None else None,
        rollout_mode=rollout,
        fallback_reason=fallback_reason,
        ml_score=round(ml_score, 4) if ml_score is not None else None,
        rule_score=rule_score,
        model_metrics=metrics,
        development_only=settings.CITIZEN_RISK_DEVELOPMENT_ONLY,
    )
    return ScoreBundle(
        response=response,
        ml_score=response.ml_score,
        rule_score=rule_score,
        confidence=response.confidence,
        rollout_mode=rollout,
        fallback_reason=fallback_reason,
        model_metrics=metrics,
        model_version=model_version,
    )
