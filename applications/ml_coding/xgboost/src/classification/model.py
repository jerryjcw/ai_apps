"""Build, train, and evaluate an XGBoost classifier on Adult Income."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    log_loss,
    roc_auc_score,
)

from . import config


@dataclass(frozen=True)
class EvalReport:
    """Held-out metrics for a fitted XGBoost model."""

    accuracy: float
    roc_auc: float
    pr_auc: float
    f1: float
    log_loss: float

    def to_dict(self) -> dict:
        return {
            "accuracy": self.accuracy,
            "roc_auc": self.roc_auc,
            "pr_auc": self.pr_auc,
            "f1": self.f1,
            "log_loss": self.log_loss,
        }


def build_classifier(params: Mapping[str, Any] | None = None) -> xgb.XGBClassifier:
    """Return an ``XGBClassifier`` seeded with our default hyperparameters.

    Overrides in ``params`` are merged on top of the defaults in ``config``.
    """
    merged = dict(config.DEFAULT_XGB_PARAMS)
    if params:
        merged.update(params)
    # early_stopping_rounds lives on the estimator in XGBoost >= 2.x.
    merged.setdefault("early_stopping_rounds", config.EARLY_STOPPING_ROUNDS)
    return xgb.XGBClassifier(**merged)


def train(
    model: xgb.XGBClassifier,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    verbose: bool | int = False,
) -> xgb.XGBClassifier:
    """Fit ``model`` with early stopping driven by the validation split."""
    model.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        verbose=verbose,
    )
    return model


def evaluate(
    model: xgb.XGBClassifier,
    X: pd.DataFrame,
    y: pd.Series,
) -> EvalReport:
    """Compute the standard suite of binary-classification metrics."""
    proba = model.predict_proba(X)[:, 1]
    preds = (proba >= 0.5).astype(int)
    return EvalReport(
        accuracy=float(accuracy_score(y, preds)),
        roc_auc=float(roc_auc_score(y, proba)),
        pr_auc=float(average_precision_score(y, proba)),
        f1=float(f1_score(y, preds)),
        log_loss=float(log_loss(y, proba)),
    )


def feature_importance_table(
    model: xgb.XGBClassifier,
    feature_names: list[str] | None = None,
    importance_type: str = "gain",
    top_k: int | None = None,
) -> pd.DataFrame:
    """Return a DataFrame of feature importances sorted descending.

    ``importance_type`` is one of ``"gain"``, ``"weight"``, ``"cover"``,
    ``"total_gain"``, ``"total_cover"``. ``"gain"`` is usually the most
    informative: average loss reduction contributed by a feature's splits.
    """
    booster = model.get_booster()
    raw = booster.get_score(importance_type=importance_type)

    # XGBoost keys are either original feature names or ``f<index>`` fallbacks.
    if feature_names is not None:
        name_of = {f"f{i}": name for i, name in enumerate(feature_names)}
        raw = {name_of.get(k, k): v for k, v in raw.items()}

    if not raw:
        return pd.DataFrame(columns=["feature", importance_type])

    table = (
        pd.DataFrame({"feature": list(raw.keys()), importance_type: list(raw.values())})
        .sort_values(importance_type, ascending=False)
        .reset_index(drop=True)
    )
    if top_k is not None:
        table = table.head(top_k)
    return table


def predict_with_threshold(
    model: xgb.XGBClassifier,
    X: pd.DataFrame,
    threshold: float = 0.5,
) -> np.ndarray:
    """Return hard 0/1 predictions at a custom probability threshold."""
    proba = model.predict_proba(X)[:, 1]
    return (proba >= threshold).astype(int)
