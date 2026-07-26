"""
Safety-focused tests for the Citizen Risk Assessment ML module.
"""

from __future__ import annotations

import os

# Isolate tests from the developer's local paygam.db
os.environ["DATABASE_URL"] = "sqlite:///./test_citizen_risk.db"
os.environ["INTERNAL_SERVICE_KEY"] = "test-internal-key"
os.environ["CITIZEN_RISK_ROLLOUT"] = "BANK=SHADOW,POLICE=DISABLED,COURT=ML_ASSISTED,DEFAULT=SHADOW"
os.environ["CITIZEN_RISK_MIN_CONFIDENCE_MARGIN"] = "0.08"
os.environ["CITIZEN_RISK_DEVELOPMENT_ONLY"] = "true"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.database import Base, get_db
from app.models.citizen_risk import CitizenRiskPrediction
from app.schemas.citizen_risk import CitizenRiskFeatures, DecisionSource, RolloutMode
from app.services import citizen_risk_service
from app.services.citizen_risk_model import get_registry
from app.services.citizen_risk_policy import decide
from app.services.citizen_risk_rules import rule_based_score

import main as main_module

# In-memory shared SQLite for API tests
_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
Base.metadata.create_all(bind=_engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


main_module.app.dependency_overrides[get_db] = _override_get_db
client = TestClient(main_module.app)


def _features(**overrides) -> CitizenRiskFeatures:
    base = dict(
        subject_ref="subj-1",
        org_type="BANK",
        late_payments=5,
        overdue_services=3,
        service_requests_30d=2,
        distinct_locations_30d=2,
        compliance_flags=1,
        pin_failed_attempts=0,
        phone_sim_swap_recent=False,
    )
    base.update(overrides)
    return CitizenRiskFeatures(**base)


def test_deterministic_rule_score():
    score, reasons = rule_based_score(_features())
    assert score >= 0.7
    assert reasons
    assert all(hasattr(r, "feature") and hasattr(r, "contribution") for r in reasons)


def test_org_segmentation_versions_differ():
    bank = decide(_features(org_type="BANK"))
    police = decide(_features(org_type="POLICE", late_payments=0, overdue_services=0, compliance_flags=0))
    assert "bank" in bank.model_version.lower() or bank.rollout_mode == RolloutMode.SHADOW
    assert police.rollout_mode == RolloutMode.DISABLED
    assert police.response.decision_source == DecisionSource.RULE_BASED_FALLBACK


def test_shadow_returns_both_with_rule_authoritative():
    bundle = decide(_features(org_type="BANK"))
    assert bundle.rollout_mode == RolloutMode.SHADOW
    assert bundle.response.decision_source in (DecisionSource.BOTH, DecisionSource.RULE_BASED_FALLBACK)
    assert bundle.response.rule_score is not None
    # In shadow, returned score is the rule score when ML is available
    if bundle.response.decision_source == DecisionSource.BOTH:
        assert bundle.response.risk_score == bundle.response.rule_score
        assert bundle.ml_score is not None


def test_explanation_shape():
    out = citizen_risk_service.score_citizen(_features())
    assert out.top_reasons
    for reason in out.top_reasons:
        assert isinstance(reason.feature, str) and reason.feature
        assert isinstance(reason.contribution, float)
    assert out.model_version
    assert out.decision_source in DecisionSource
    assert out.development_only is True


def test_low_confidence_fallback_in_ml_assisted(monkeypatch):
    # Force a near-0.5 probability via monkeypatch on SegmentModel.predict
    registry = get_registry()
    segment = registry.get("COURT")

    def low_conf_predict(feature_vector):
        from app.schemas.citizen_risk import RiskReason
        return 0.51, 0.01, [RiskReason(feature="Late payments", contribution=0.1)]

    monkeypatch.setattr(segment, "predict", low_conf_predict)
    bundle = decide(_features(org_type="COURT", late_payments=0, overdue_services=0, compliance_flags=0))
    assert bundle.response.decision_source == DecisionSource.RULE_BASED_FALLBACK
    assert bundle.fallback_reason == "low_confidence"


def test_forced_model_failure_falls_back():
    registry = get_registry()
    registry.force_failure(True)
    try:
        bundle = decide(_features(org_type="COURT"))
        assert bundle.response.decision_source == DecisionSource.RULE_BASED_FALLBACK
        assert bundle.fallback_reason and "ml_unavailable" in bundle.fallback_reason
    finally:
        registry.force_failure(False)


def test_disabled_rollout_rules_only():
    bundle = decide(_features(org_type="POLICE"))
    assert bundle.rollout_mode == RolloutMode.DISABLED
    assert bundle.response.decision_source == DecisionSource.RULE_BASED_FALLBACK
    assert bundle.fallback_reason == "rollout_disabled"


def test_internal_endpoint_contract():
    payload = _features().model_dump()
    resp = client.post(
        "/internal/risk-score",
        json=payload,
        headers={"X-Internal-Service-Key": "test-internal-key"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for key in ("risk_score", "risk_level", "org_type", "top_reasons", "model_version", "decision_source"):
        assert key in data
    assert data["decision_source"] in ("ML", "RULE_BASED_FALLBACK", "BOTH")
    assert data["risk_level"] in ("LOW", "MEDIUM", "HIGH")
    assert isinstance(data["top_reasons"], list)


def test_internal_endpoint_rejects_bad_key():
    resp = client.post(
        "/internal/risk-score",
        json=_features().model_dump(),
        headers={"X-Internal-Service-Key": "wrong"},
    )
    assert resp.status_code == 401


def test_internal_endpoint_rejects_missing_key():
    resp = client.post("/internal/risk-score", json=_features().model_dump())
    assert resp.status_code == 401


def test_append_only_audit_writes():
    db = TestingSessionLocal()
    try:
        before = db.query(CitizenRiskPrediction).count()
        citizen_risk_service.score_and_persist(_features(subject_ref="audit-a"), db)
        citizen_risk_service.score_and_persist(_features(subject_ref="audit-a"), db)
        after = db.query(CitizenRiskPrediction).count()
        assert after == before + 2
        rows = db.query(CitizenRiskPrediction).filter_by(subject_ref="audit-a").all()
        assert len(rows) == 2
        for row in rows:
            assert row.input_feature_snapshot is not None
            assert row.model_version
            assert row.decision_source
            assert row.rule_score is not None
    finally:
        db.close()


def test_settings_rollout_map():
    assert settings.rollout_mode_for_org("BANK") == "SHADOW"
    assert settings.rollout_mode_for_org("POLICE") == "DISABLED"
    assert settings.rollout_mode_for_org("COURT") == "ML_ASSISTED"
    assert settings.rollout_mode_for_org("UNKNOWN") == "SHADOW"
