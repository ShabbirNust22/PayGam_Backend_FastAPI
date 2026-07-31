"""
Org-segmented Logistic Regression registry for Citizen Risk Assessment.

Loads versioned joblib artifacts when available. Synthetic train-on-boot is
allowed only outside production and only when explicitly enabled.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from app.core.config import settings
from app.schemas.citizen_risk import ModelMetricsOut, RiskReason
from app.services.citizen_risk_data_synthetic import make_synthetic_training_set
from app.services.citizen_risk_features import FEATURE_LABELS, FEATURE_NAMES, normalize_org_segment

logger = logging.getLogger("citizen_risk.model")

MODEL_FAMILY = "logistic_regression"
SEGMENTS = ("BANK", "POLICE", "COURT", "DEFAULT")


@dataclass
class SegmentModel:
    org_segment: str
    version: str
    scaler: StandardScaler
    model: LogisticRegression
    metrics: ModelMetricsOut
    source: str

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


def _evaluate(X: np.ndarray, y: np.ndarray) -> ModelMetricsOut:
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=7, stratify=y
    )
    eval_scaler = StandardScaler().fit(X_train)
    X_train_s = eval_scaler.transform(X_train)
    X_test_s = eval_scaler.transform(X_test)
    eval_model = LogisticRegression(max_iter=500, random_state=7).fit(X_train_s, y_train)
    proba = eval_model.predict_proba(X_test_s)[:, 1]
    preds = (proba >= 0.5).astype(int)
    auc = float(roc_auc_score(y_test, proba)) if len(np.unique(y_test)) > 1 else None
    f1 = float(f1_score(y_test, preds, zero_division=0))
    brier = float(brier_score_loss(y_test, proba))
    if len(np.unique(y_test)) > 1:
        calibration_curve(y_test, proba, n_bins=5)
    return ModelMetricsOut(
        auc_roc=round(auc, 4) if auc is not None else None,
        f1=round(f1, 4),
        brier_score=round(brier, 4),
        training_data="synthetic_dev_only",
    )


def train_segment(org_segment: str) -> SegmentModel:
    X, y = make_synthetic_training_set(org_segment)
    scaler = StandardScaler().fit(X)
    model = LogisticRegression(max_iter=500, random_state=42).fit(scaler.transform(X), y)
    metrics = _evaluate(X, y)
    version = f"v1.0.0-synth-{org_segment.lower()}-{MODEL_FAMILY}"
    return SegmentModel(
        org_segment=org_segment,
        version=version,
        scaler=scaler,
        model=model,
        metrics=metrics,
        source="synthetic",
    )


def artifact_path(org_segment: str, model_dir: str | Path | None = None) -> Path:
    root = Path(model_dir or settings.CITIZEN_RISK_MODEL_DIR)
    return root / f"{org_segment.lower()}_{MODEL_FAMILY}.joblib"


def save_segment(segment: SegmentModel, model_dir: str | Path | None = None) -> Path:
    path = artifact_path(segment.org_segment, model_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "org_segment": segment.org_segment,
            "version": segment.version,
            "scaler": segment.scaler,
            "model": segment.model,
            "metrics": segment.metrics.model_dump(),
            "source": segment.source,
            "feature_names": FEATURE_NAMES,
        },
        path,
    )
    meta = path.with_suffix(".json")
    meta.write_text(
        json.dumps(
            {
                "org_segment": segment.org_segment,
                "version": segment.version,
                "metrics": segment.metrics.model_dump(),
                "source": segment.source,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def load_segment(org_segment: str, model_dir: str | Path | None = None) -> SegmentModel | None:
    path = artifact_path(org_segment, model_dir)
    if not path.exists():
        return None
    payload = joblib.load(path)
    metrics = ModelMetricsOut(**payload.get("metrics", {}))
    return SegmentModel(
        org_segment=payload["org_segment"],
        version=payload["version"],
        scaler=payload["scaler"],
        model=payload["model"],
        metrics=metrics,
        source=payload.get("source", "artifact"),
    )


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, SegmentModel] = {}
        self._force_failure = False
        self._load_or_bootstrap()

    def _load_or_bootstrap(self) -> None:
        for segment in SEGMENTS:
            loaded = load_segment(segment)
            if loaded:
                self._models[segment] = loaded
                continue
            if settings.is_production or not settings.CITIZEN_RISK_ALLOW_SYNTHETIC_TRAIN_ON_BOOT:
                logger.warning(
                    "citizen_risk_artifact_missing segment=%s — ML unavailable until artifacts are trained",
                    segment,
                )
                continue
            trained = train_segment(segment)
            save_segment(trained)
            self._models[segment] = trained

    def get(self, org_type: str) -> SegmentModel:
        if self._force_failure:
            raise RuntimeError("Forced model failure (test hook)")
        segment = normalize_org_segment(org_type)
        model = self._models.get(segment) or self._models.get("DEFAULT")
        if model is None:
            raise RuntimeError(f"No citizen-risk model artifact for segment {segment}")
        return model

    def force_failure(self, enabled: bool = True) -> None:
        self._force_failure = enabled

    def has_models(self) -> bool:
        return bool(self._models)


_REGISTRY: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ModelRegistry()
    return _REGISTRY
