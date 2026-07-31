"""Synthetic training data for citizen-risk models — development/CI only."""

from __future__ import annotations

import numpy as np

_ORG_WEIGHTS = {
    "BANK": np.array([0.40, 0.35, 0.05, 0.08, 0.30, 0.18, 0.40]),
    "POLICE": np.array([0.15, 0.10, 0.12, 0.35, 0.45, 0.25, 0.30]),
    "COURT": np.array([0.25, 0.20, 0.08, 0.15, 0.50, 0.22, 0.28]),
    "DEFAULT": np.array([0.35, 0.30, 0.05, 0.10, 0.40, 0.20, 0.45]),
}

_ORG_SEEDS = {"BANK": 11, "POLICE": 22, "COURT": 33, "DEFAULT": 42}


def make_synthetic_training_set(org_segment: str, n: int = 2000) -> tuple[np.ndarray, np.ndarray]:
    seed = _ORG_SEEDS.get(org_segment, 42)
    weights = _ORG_WEIGHTS.get(org_segment, _ORG_WEIGHTS["DEFAULT"])
    rng = np.random.default_rng(seed)
    X = np.column_stack(
        [
            rng.poisson(1.2, n),
            rng.poisson(0.8, n),
            rng.poisson(4, n),
            rng.poisson(2, n) + 1,
            rng.poisson(0.5, n),
            rng.poisson(0.3, n),
            rng.integers(0, 2, n),
        ]
    ).astype(float)
    logits = X @ weights - 2.2 + rng.normal(0, 0.5, n)
    probs = 1 / (1 + np.exp(-logits))
    y = (rng.random(n) < probs).astype(int)
    return X, y
