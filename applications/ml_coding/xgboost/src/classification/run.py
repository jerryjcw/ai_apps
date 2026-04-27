"""End-to-end runnable: download → train → evaluate → save model + report.

Run from inside ``applications/ml_coding/xgboost/``:

    ../.venv/bin/python -m src.classification.run
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import config
from .data import load_adult_splits
from .model import build_classifier, evaluate, feature_importance_table, train


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train XGBoost on UCI Adult Income.")
    parser.add_argument("--max-depth", type=int, default=None)
    parser.add_argument("--learning-rate", type=float, default=None)
    parser.add_argument("--n-estimators", type=int, default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--report-path",
        type=Path,
        default=config.REPORT_DIR / "adult_report.json",
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=config.MODEL_DIR / "adult_xgb.json",
    )
    args = parser.parse_args(argv)

    overrides: dict = {}
    if args.max_depth is not None:
        overrides["max_depth"] = args.max_depth
    if args.learning_rate is not None:
        overrides["learning_rate"] = args.learning_rate
    if args.n_estimators is not None:
        overrides["n_estimators"] = args.n_estimators

    splits = load_adult_splits()
    print(
        f"Train {splits.X_train.shape} | Val {splits.X_val.shape} | "
        f"Test {splits.X_test.shape}"
    )

    model = build_classifier(overrides)
    train(model, splits.X_train, splits.y_train, splits.X_val, splits.y_val,
          verbose=args.verbose)

    val_report = evaluate(model, splits.X_val, splits.y_val)
    test_report = evaluate(model, splits.X_test, splits.y_test)

    print("\nValidation:", val_report.to_dict())
    print("Test      :", test_report.to_dict())

    top = feature_importance_table(
        model, feature_names=list(splits.X_train.columns), top_k=15,
    )
    print("\nTop features by gain:")
    print(top.to_string(index=False))

    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.model_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps({
        "val": val_report.to_dict(),
        "test": test_report.to_dict(),
        "top_features": top.to_dict(orient="records"),
        "best_iteration": getattr(model, "best_iteration", None),
    }, indent=2))
    model.save_model(str(args.model_path))

    print(f"\nSaved model → {args.model_path}")
    print(f"Saved report → {args.report_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
