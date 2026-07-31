"""
Safety-focused tests for production readiness + citizen risk.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

# Isolate tests before importing app modules
os.environ["ENVIRONMENT"] = "development"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["INTERNAL_SERVICE_KEY"] = "test-internal-key"
os.environ["SECRET_KEY"] = "test-secret-key-with-enough-length-32"
os.environ["ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"
os.environ["ALLOWED_ORIGINS"] = "http://testserver"
os.environ["DOCS_ENABLED"] = "true"
os.environ["EGOV_USE_MOCK"] = "true"
os.environ["TELCO_USE_MOCK"] = "true"
os.environ["CITIZEN_RISK_ROLLOUT"] = "BANK=SHADOW,POLICE=DISABLED,COURT=ML_ASSISTED,DEFAULT=SHADOW"
os.environ["CITIZEN_RISK_MIN_CONFIDENCE_MARGIN"] = "0.08"
os.environ["CITIZEN_RISK_DEVELOPMENT_ONLY"] = "true"
os.environ["CITIZEN_RISK_ALLOW_SYNTHETIC_TRAIN_ON_BOOT"] = "true"
os.environ["CITIZEN_RISK_MODEL_DIR"] = "model_artifacts/citizen_risk_test"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.database import Base, get_db
from app.models.citizen_risk import CitizenRiskPrediction, PartnerRiskEvent
from app.models.user import User, Wallet
from app.schemas.citizen_risk import CitizenRiskFeatures, DecisionSource, RolloutMode
from app.services import citizen_risk_service
from app.services.citizen_risk_model import get_registry
from app.services.citizen_risk_policy import decide
from app.services.citizen_risk_rules import rule_based_score
from app.services.partner_feature_builder import build_features_from_partners, ingest_partner_event
from app.core.security import create_access_token, hash_password

import main as main_module

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


def _auth_header_for_user(db) -> dict:
    user = User(
        full_name="Test User",
        phone_number="+2201000001",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    db.flush()
    db.add(Wallet(user_id=user.id, balance=Decimal("1000.00")))
    db.commit()
    token = create_access_token(subject=user.id)
    return {"Authorization": f"Bearer {token}"}, user


def test_production_config_fail_closed():
    s = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="CHANGE_ME_IN_PRODUCTION_USE_ENV_VAR",
        DATABASE_URL="sqlite:///./x.db",
        EGOV_USE_MOCK=True,
        TELCO_USE_MOCK=True,
        CITIZEN_RISK_ALLOW_SYNTHETIC_TRAIN_ON_BOOT=True,
    )
    try:
        s.validate_for_environment()
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "SECRET_KEY" in str(exc)
        assert "DATABASE_URL" in str(exc)


def test_deterministic_rule_score():
    score, reasons = rule_based_score(_features())
    assert score >= 0.7
    assert reasons


def test_shadow_returns_both_with_rule_authoritative():
    bundle = decide(_features(org_type="BANK"))
    assert bundle.rollout_mode == RolloutMode.SHADOW
    assert bundle.response.decision_source in (DecisionSource.BOTH, DecisionSource.RULE_BASED_FALLBACK)
    if bundle.response.decision_source == DecisionSource.BOTH:
        assert bundle.response.risk_score == bundle.response.rule_score


def test_explanation_shape():
    out = citizen_risk_service.score_citizen(_features())
    assert out.top_reasons
    assert out.model_version
    assert out.decision_source in DecisionSource


def test_low_confidence_fallback_in_ml_assisted(monkeypatch):
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


def test_internal_endpoint_contract():
    resp = client.post(
        "/internal/risk-score",
        json=_features().model_dump(),
        headers={"X-Internal-Service-Key": "test-internal-key"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for key in ("risk_score", "risk_level", "org_type", "top_reasons", "model_version", "decision_source"):
        assert key in data


def test_internal_endpoint_rejects_bad_key():
    resp = client.post(
        "/internal/risk-score",
        json=_features().model_dump(),
        headers={"X-Internal-Service-Key": "wrong"},
    )
    assert resp.status_code == 401


def test_risk_insights_requires_auth():
    resp = client.post("/api/v1/risk-insights/events", json={"event_type": "login"})
    assert resp.status_code == 401
    resp_ok = client.post(
        "/api/v1/risk-insights/events",
        json={"event_type": "login", "device_ref": "d1"},
        headers={"X-Internal-Service-Key": "test-internal-key"},
    )
    assert resp_ok.status_code == 201


def test_partner_event_builds_features():
    db = TestingSessionLocal()
    try:
        ingest_partner_event(
            db,
            event_id="evt-1",
            partner_code="BANK_XYZ",
            subject_ref="subj-partner",
            event_type="payment_overdue",
            occurred_at=datetime.now(timezone.utc),
            payload={"amount_gmd": 100},
        )
        ingest_partner_event(
            db,
            event_id="evt-2",
            partner_code="AFRICELL",
            subject_ref="subj-partner",
            event_type="sim_swap",
            occurred_at=datetime.now(timezone.utc),
            payload={},
        )
        features = build_features_from_partners(db, "subj-partner", org_type="BANK")
        assert features.late_payments >= 1
        assert features.phone_sim_swap_recent is True
    finally:
        db.close()

    resp = client.post(
        "/internal/partners/BANK_XYZ/events",
        json={
            "event_id": "evt-http-1",
            "subject_ref": "subj-http",
            "event_type": "utility_overdue",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {},
        },
        headers={"X-Internal-Service-Key": "test-internal-key"},
    )
    assert resp.status_code == 200
    assert resp.json()["duplicate"] is False


def test_append_only_audit_writes():
    db = TestingSessionLocal()
    try:
        before = db.query(CitizenRiskPrediction).count()
        citizen_risk_service.score_and_persist(_features(subject_ref="audit-a"), db)
        citizen_risk_service.score_and_persist(_features(subject_ref="audit-a"), db)
        after = db.query(CitizenRiskPrediction).count()
        assert after == before + 2
    finally:
        db.close()


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code in (200, 503)
    assert "database" in resp.json()
