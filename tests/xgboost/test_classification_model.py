"""Unit tests for the model layer.

We train on a tiny synthetic numeric dataset so each test runs in well under a
second. The goal is to verify contracts (types, metric ranges, ordering),
not to re-benchmark XGBoost.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import xgboost as xgb
from sklearn.datasets import make_classification

from src.classification import config
from src.classification.model import (
    EvalReport,
    build_classifier,
    evaluate,
    feature_importance_table,
    predict_with_threshold,
    train,
)


@pytest.fixture
def tiny_dataset() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    X_arr, y_arr = make_classification(
        n_samples=400,
        n_features=6,
        n_informative=4,
        n_redundant=0,
        random_state=0,
    )
    cols = [f"feat_{i}" for i in range(X_arr.shape[1])]
    X = pd.DataFrame(X_arr, columns=cols)
    y = pd.Series(y_arr, name="y")
    X_train, X_val, X_test = X.iloc[:240], X.iloc[240:320], X.iloc[320:]
    y_train, y_val, y_test = y.iloc[:240], y.iloc[240:320], y.iloc[320:]
    return X_train, y_train, X_val, y_val, X_test, y_test


def test_build_classifier_returns_xgb_classifier() -> None:
    model = build_classifier()
    assert isinstance(model, xgb.XGBClassifier)
    assert model.get_params()["objective"] == config.DEFAULT_XGB_PARAMS["objective"]


def test_build_classifier_merges_overrides() -> None:
    model = build_classifier({"max_depth": 3, "learning_rate": 0.2})
    params = model.get_params()
    assert params["max_depth"] == 3
    assert params["learning_rate"] == 0.2
    # Non-overridden defaults remain in place.
    assert params["n_estimators"] == config.DEFAULT_XGB_PARAMS["n_estimators"]


def test_train_runs_early_stopping(tiny_dataset) -> None:
    X_train, y_train, X_val, y_val, _, _ = tiny_dataset
    model = build_classifier({"n_estimators": 200, "max_depth": 3})
    train(model, X_train, y_train, X_val, y_val, verbose=False)
    # Early stopping should pick a best_iteration strictly before the cap.
    assert model.best_iteration is not None
    assert 0 <= model.best_iteration < 200


def test_evaluate_returns_metrics_in_valid_ranges(tiny_dataset) -> None:
    X_train, y_train, X_val, y_val, X_test, y_test = tiny_dataset
    model = build_classifier({"n_estimators": 100, "max_depth": 3})
    train(model, X_train, y_train, X_val, y_val)
    report = evaluate(model, X_test, y_test)

    assert isinstance(report, EvalReport)
    for metric in ("accuracy", "roc_auc", "pr_auc", "f1"):
        value = getattr(report, metric)
        assert 0.0 <= value <= 1.0, f"{metric} out of range: {value}"
    assert report.log_loss >= 0.0
    # A well-separable synthetic problem should beat random.
    assert report.roc_auc > 0.7


def test_feature_importance_table_is_sorted_and_named(tiny_dataset) -> None:
    X_train, y_train, X_val, y_val, _, _ = tiny_dataset
    model = build_classifier({"n_estimators": 60, "max_depth": 3})
    train(model, X_train, y_train, X_val, y_val)

    table = feature_importance_table(model, feature_names=list(X_train.columns))
    assert list(table.columns) == ["feature", "gain"]
    assert not table.empty
    # Sorted descending.
    assert np.all(np.diff(table["gain"].values) <= 0)
    # Every reported name belongs to the real feature set (not f0/f1/...).
    assert set(table["feature"]).issubset(set(X_train.columns))


def test_feature_importance_table_top_k_limits_rows(tiny_dataset) -> None:
    X_train, y_train, X_val, y_val, _, _ = tiny_dataset
    model = build_classifier({"n_estimators": 40, "max_depth": 3})
    train(model, X_train, y_train, X_val, y_val)
    table = feature_importance_table(
        model, feature_names=list(X_train.columns), top_k=3,
    )
    assert len(table) <= 3


def test_predict_with_threshold_changes_positive_rate(tiny_dataset) -> None:
    X_train, y_train, X_val, y_val, X_test, _ = tiny_dataset
    model = build_classifier({"n_estimators": 60, "max_depth": 3})
    train(model, X_train, y_train, X_val, y_val)
    low = predict_with_threshold(model, X_test, threshold=0.1).mean()
    high = predict_with_threshold(model, X_test, threshold=0.9).mean()
    assert low >= high  # a higher threshold cannot produce more positives
