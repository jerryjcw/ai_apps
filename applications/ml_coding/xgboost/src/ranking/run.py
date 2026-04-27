"""End-to-end runnable for the MovieLens-100K ranking example.

Run from inside ``applications/ml_coding/xgboost/``:

    ../.venv/bin/python -m src.ranking.run
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import config
from .data import load_ranking_splits
from .model import (
    build_ranker, evaluate, feature_importance_table, rank_candidates, train,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train XGBRanker on MovieLens-100K.")
    parser.add_argument("--objective", type=str, default=None,
                        choices=[None, "rank:ndcg", "rank:pairwise", "rank:map"])
    parser.add_argument("--max-depth", type=int, default=None)
    parser.add_argument("--learning-rate", type=float, default=None)
    parser.add_argument("--n-estimators", type=int, default=None)
    parser.add_argument("--lambdarank-pair-method", type=str, default=None,
                        choices=[None, "mean", "topk"])
    parser.add_argument("--lambdarank-num-pair-per-sample", type=int, default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--report-path", type=Path,
                        default=config.REPORT_DIR / "movielens_report.json")
    parser.add_argument("--model-path", type=Path,
                        default=config.MODEL_DIR / "movielens_xgbranker.json")
    args = parser.parse_args(argv)

    overrides: dict = {}
    for flag, key in [
        ("objective", "objective"),
        ("max_depth", "max_depth"),
        ("learning_rate", "learning_rate"),
        ("n_estimators", "n_estimators"),
        ("lambdarank_pair_method", "lambdarank_pair_method"),
        ("lambdarank_num_pair_per_sample", "lambdarank_num_pair_per_sample"),
    ]:
        v = getattr(args, flag)
        if v is not None:
            overrides[key] = v

    splits = load_ranking_splits()
    print(
        f"Train {splits.X_train.shape} ({len(set(splits.qid_train))} users) | "
        f"Val {splits.X_val.shape} | Test {splits.X_test.shape}"
    )

    model = build_ranker(overrides)
    train(model,
          splits.X_train, splits.y_train, splits.qid_train,
          splits.X_val, splits.y_val, splits.qid_val,
          verbose=args.verbose)
    print(f"best_iteration = {getattr(model, 'best_iteration', None)}")

    val_report = evaluate(model, splits.X_val, splits.y_val, splits.qid_val)
    test_report = evaluate(model, splits.X_test, splits.y_test, splits.qid_test)
    print("\nValidation:", val_report.to_dict())
    print("Test      :", test_report.to_dict())

    top = feature_importance_table(
        model, feature_names=list(splits.X_train.columns), top_k=10,
    )
    print("\nTop features by gain:")
    print(top.to_string(index=False))

    # ----- Inference demo: rank movies for one sample user -----
    sample_user = int(splits.qid_test[0])
    mask = splits.qid_test == sample_user
    user_slice = splits.X_test.loc[mask].copy()
    user_slice["movie_id_row"] = user_slice.index  # placeholder id
    ranked = rank_candidates(
        model, user_slice,
        feature_columns=splits.feature_columns,
        top_k=10,
        id_column="movie_id_row",
    )
    print(f"\nTop-10 ranked candidates for user {sample_user}:")
    print(ranked[["rank", "score", "movie_id_row"]].to_string(index=False))

    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.model_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps({
        "val": val_report.to_dict(),
        "test": test_report.to_dict(),
        "top_features": top.to_dict(orient="records"),
        "best_iteration": getattr(model, "best_iteration", None),
        "params": model.get_params(),
    }, indent=2, default=str))
    model.save_model(str(args.model_path))
    print(f"\nSaved model → {args.model_path}")
    print(f"Saved report → {args.report_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
