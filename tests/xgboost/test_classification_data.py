"""Unit tests for the data-preprocessing layer.

These tests do **not** hit the network: we build a tiny synthetic frame that
mimics the OpenML Adult schema and exercise the pure functions.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.classification import config
from src.classification.data import AdultSplits, make_splits, preprocess


@pytest.fixture
def fake_adult_frame() -> pd.DataFrame:
    """Small frame that mirrors the OpenML Adult schema."""
    return pd.DataFrame(
        {
            "age": [25, 38, 52, 28, 45, 31, 60, 22, 41, 35],
            "workclass": [
                "Private", "Self-emp", "?", "Private", "Gov",
                "Private", "Private", "?", "Gov", "Private",
            ],
            "fnlwgt": [226_802, 89_814, 160_323, 104_338, 198_693,
                       209_642, 130_707, 227_026, 151_336, 249_409],
            "education": [
                "HS-grad", "Bachelors", "Masters", "HS-grad", "Bachelors",
                "Bachelors", "HS-grad", "HS-grad", "Masters", "Bachelors",
            ],
            "education-num": [9, 13, 14, 9, 13, 13, 9, 9, 14, 13],
            "marital-status": [
                "Never-married", "Married", "Divorced", "Married", "Married",
                "Never-married", "Married", "Never-married", "Divorced", "Married",
            ],
            "occupation": [
                "Sales", "Exec", "?", "Craft", "Prof",
                "Sales", "Transport", "?", "Prof", "Exec",
            ],
            "relationship": [
                "Not-in-family", "Husband", "Unmarried", "Husband", "Wife",
                "Own-child", "Husband", "Own-child", "Not-in-family", "Wife",
            ],
            "race": ["White"] * 10,
            "sex": ["Male", "Male", "Female", "Male", "Female",
                    "Male", "Male", "Female", "Male", "Female"],
            "capital-gain": [0, 0, 0, 0, 5000, 0, 0, 0, 0, 0],
            "capital-loss": [0] * 10,
            "hours-per-week": [40, 50, 45, 40, 38, 30, 45, 20, 50, 42],
            "native-country": ["United-States"] * 10,
            "class": [
                "<=50K", ">50K", ">50K", "<=50K", ">50K",
                "<=50K", "<=50K", "<=50K", ">50K", ">50K",
            ],
        }
    )


def test_preprocess_produces_category_dtypes(fake_adult_frame: pd.DataFrame) -> None:
    X, _ = preprocess(fake_adult_frame)
    for col in config.CATEGORICAL_COLUMNS:
        assert isinstance(X[col].dtype, pd.CategoricalDtype), (
            f"{col!r} should be a pandas category dtype"
        )


def test_preprocess_binarises_target(fake_adult_frame: pd.DataFrame) -> None:
    _, y = preprocess(fake_adult_frame)
    assert set(y.unique()) <= {0, 1}
    # 5 of 10 rows are ">50K" in the fixture
    assert y.sum() == 5
    assert y.name == "income_gt_50k"


def test_preprocess_handles_trailing_period_in_target(fake_adult_frame: pd.DataFrame) -> None:
    # The UCI 'adult.test' file labels rows with a trailing period (e.g. '>50K.').
    frame = fake_adult_frame.copy()
    frame["class"] = frame["class"].str.replace(">50K", ">50K.").str.replace("<=50K", "<=50K.")
    _, y = preprocess(frame)
    assert y.sum() == 5


def test_preprocess_converts_question_marks_to_na(fake_adult_frame: pd.DataFrame) -> None:
    X, _ = preprocess(fake_adult_frame)
    # The fixture has 2 '?' in workclass and 2 in occupation.
    assert X["workclass"].isna().sum() == 2
    assert X["occupation"].isna().sum() == 2


def test_preprocess_drops_target_from_features(fake_adult_frame: pd.DataFrame) -> None:
    X, _ = preprocess(fake_adult_frame)
    assert config.TARGET_COLUMN not in X.columns


def test_make_splits_shapes_and_stratification(fake_adult_frame: pd.DataFrame) -> None:
    X, y = preprocess(fake_adult_frame)
    splits = make_splits(X, y, test_size=0.2, val_size=0.25, random_state=0)
    assert isinstance(splits, AdultSplits)
    total = (
        len(splits.X_train) + len(splits.X_val) + len(splits.X_test)
    )
    assert total == len(X)
    # Stratification keeps class balance within ~1 row on tiny data.
    train_pos_rate = splits.y_train.mean()
    overall_pos_rate = y.mean()
    assert abs(train_pos_rate - overall_pos_rate) <= 0.25


def test_make_splits_is_deterministic(fake_adult_frame: pd.DataFrame) -> None:
    X, y = preprocess(fake_adult_frame)
    a = make_splits(X, y, random_state=42)
    b = make_splits(X, y, random_state=42)
    pd.testing.assert_frame_equal(a.X_train, b.X_train)
    pd.testing.assert_series_equal(a.y_test, b.y_test)
