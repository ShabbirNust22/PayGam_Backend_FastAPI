"""
Org-segmented Logistic Regression registry for Citizen Risk Assessment.

Training uses deterministic synthetic data (development-only). Swap
`_make_synthetic_training_set` / load path for real CitizenCreditScore
platform extracts when the Java data pipeline is wired.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from app.schemas.citizen_risk import ModelMetricsOut, RiskReason
from app.services.citizen_risk_features import FEATURE_LABELS, FEATURE_NAMES, normalize_org_segment

MODEL_FAMILY = "logistic_regression"
MODEL_VERSION_PREFIX = "v1.0.0-synth"

# Per-org weight emphasis so BANK / POLICE / COURT learn different patterns.
_ORG_WEIGHTS = {
    "BANK": np.array([0.40, 0.35, 0.05, 0.08, 0.30, 0.18, 0.40]),
    "POLICE": np.array([0.15, 0.10, 0.12, 0.35, 0.45, 0.25, 0.30]),
    "COURT": np.array([0.25, 0.20, 0.08, 0.15, 0.50, 0.22, 0.28]),
    "DEFAULT": np.array([0.35, 0.30, 0.05, 0.10, 0.40, 0.20, 0.45]),
}

_ORG_SEEDS = {"BANK": 11, "POLICE": 22, "COURT": 33, "DEFAULT": 42}


def _make_synthetic_training_set(org_segment: str, n: int = 2000) -> tuple[np.ndarray, np.ndarray]:
    """
    DEVELOPMENT ONLY — synthetic-but-plausible labeled rows.
    Replace with a query against CitizenCreditScore / ServiceRequest /
    Location / Compliance tables when platform data is available.
    """
    seed = _ORG_SEEDS.get(org_segment, 42)
    weights = _ORG_WEIGHTS.get(org_segment, _ORG_WEIGHTS["DEFAULT"])
    rng = np.random.default_rng(seed)
    X = np.column_stack([
        rng.poisson(1.2, n),
        rng.poisson(0.8, n),
        rng.poisson(4, n),
        rng.poisson(2, n) + 1,
        rng.poisson(0.5, n),
        rng.poisson(0.3, n),
        rng.integers(0, 2, n),
    ]).astype(float)
    logits = X @ weights - 2.2 + rng.normal(0, 0.5, n)
    probs = 1 / (1 + np.exp(-logits))
    y = (rng.random(n) < probs).astype(int)
    return X, y


@dataclass
class SegmentModel:
    org_segment: str
    version: str
    scaler: StandardScaler
    model: LogisticRegression
    metrics: ModelMetricsOut

    def predict(self, feature_vector: list[float]) -> tuple[float, float, list[RiskReason]]:
        x = np.array(feature_vector, dtype=float).reshape(1, -1)
        x_scaled = self.scaler.transform(x)
        proba = float(self.model.predict_proba(x_scaled)[0, 1])
        confidence = abs(proba - 0.5)
        contributions = self.model.coef_[0] * x_scaled[0]
        reasons = sorted(
            (
                RiskReason(
                    feature=FEATURE_LABELS.get(name, name),
                    contribution=round(float(c), 4),
                )
                for name, c in zip(FEATURE_NAMES, contributions)
            ),
            key=lambda r: abs(r.contribution),
            reverse=True,
        )[:3]
        return proba, confidence, reasons


def _evaluate(model: LogisticRegression, scaler: StandardScaler, X: np.ndarray, y: np.ndarray) -> ModelMetricsOut:
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=7, stratify=y)
    # Re-fit on train split for honest holdout metrics (caller already fitted on full set;
    # we train a twin for evaluation only).
    eval_scaler = StandardScaler().fit(X_train)
    X_train_s = eval_scaler.transform(X_train)
    X_test_s = eval_scaler.transform(X_test)
    eval_model = LogisticRegression(max_iter=500, random_state=7).fit(X_train_s, y_train)
    proba = eval_model.predict_proba(X_test_s)[:, 1]
    preds = (proba >= 0.5).astype(int)
    auc = float(roc_auc_score(y_test, proba)) if len(np.unique(y_test)) > 1 else None
    f1 = float(f1_score(y_test, preds, zero_division=0))
    brier = float(brier_score_loss(y_test, proba))
    # Touch calibration_curve so calibration tooling is exercised in CI.
    if len(np.unique(y_test)) > 1:
        calibration_curve(y_test, proba, n_bins=5)
    return ModelMetricsOut(
        auc_roc=round(auc, 4) if auc is not None else None,
        f1=round(f1, 4),
        brier_score=round(brier, 4),
        training_data="synthetic_dev_only",
    )


def _train_segment(org_segment: str) -> SegmentModel:
    X, y = _make_synthetic_training_set(org_segment)
    scaler = StandardScaler().fit(X)
    X_scaled = scaler.transform(X)
    model = LogisticRegression(max_iter=500, random_state=_ORG_SEEDS.get(org_segment, 42)).fit(X_scaled, y)
    metrics = _evaluate(model, scaler, X, y)
    version = f"{MODEL_VERSION_PREFIX}-{org_segment.lower()}-{MODEL_FAMILY}"
    return SegmentModel(
        org_segment=org_segment,
        version=version,
        scaler=scaler,
        model=model,
        metrics=metrics,
    )


class ModelRegistry:
    """Loads one Logistic Regression per org segment at process start."""

    def __init__(self) -> None:
        self._models: dict[str, SegmentModel] = {
            segment: _train_segment(segment) for segment in ("BANK", "POLICE", "COURT", "DEFAULT")
        }
        self._force_failure = False  # test hook

    def get(self, org_type: str) -> SegmentModel:
        if self._force_failure:
            raise RuntimeError("Forced model failure (test hook)")
        segment = normalize_org_segment(org_type)
        return self._models[segment]

    def force_failure(self, enabled: bool = True) -> None:
        self._force_failure = enabled


_REGISTRY = ModelRegistry()


def get_registry() -> ModelRegistry:
    return _REGISTRY
