#!/usr/bin/env python
"""Offline trainer for citizen-risk model artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.services.citizen_risk_model import SEGMENTS, save_segment, train_segment


def main() -> None:
    parser = argparse.ArgumentParser(description="Train citizen-risk Logistic Regression artifacts")
    parser.add_argument("--model-dir", default="model_artifacts/citizen_risk")
    parser.add_argument(
        "--segments",
        nargs="*",
        default=list(SEGMENTS),
        help="Org segments to train (default: all)",
    )
    args = parser.parse_args()
    out = Path(args.model_dir)
    out.mkdir(parents=True, exist_ok=True)
    for segment in args.segments:
        model = train_segment(segment.upper())
        path = save_segment(model, out)
        print(f"saved {segment}: {path} version={model.version}")


if __name__ == "__main__":
    main()
