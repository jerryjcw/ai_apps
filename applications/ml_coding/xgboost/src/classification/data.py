"""Dataset download and preprocessing for the UCI Adult Income example.

The Adult dataset is a classic binary-classification benchmark: predict whether
a person earns more than $50K/yr from demographic features. It is used as a
benchmark in the XGBoost paper (Chen & Guestrin, KDD 2016) and is small enough
to iterate on in seconds.

We pull the tidy v2 copy from OpenML via scikit-learn so downloads are cached
automatically and the schema is stable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import pandas as pd
from sklearn.datasets import fetch_openml
from sklearn.model_selection import train_test_split

from . import config


@dataclass(frozen=True)
class AdultSplits:
    """Train / val / test splits as pandas objects."""

    X_train: pd.DataFrame
    y_train: pd.Series
    X_val: pd.DataFrame
    y_val: pd.Series
    X_test: pd.DataFrame
    y_test: pd.Series


def download_adult(cache_dir: Path | None = None) -> pd.DataFrame:
    """Fetch the Adult dataset from OpenML and return a single DataFrame.

    The raw frame contains the target column (config.TARGET_COLUMN). The
    download is cached by scikit-learn under ``cache_dir`` so subsequent
    calls are local.
    """
    cache_dir = Path(cache_dir) if cache_dir is not None else config.DATA_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)

    bundle = fetch_openml(
        name=config.OPENML_NAME,
        version=config.OPENML_VERSION,
        as_frame=True,
        data_home=str(cache_dir),
        parser="auto",
    )
    frame: pd.DataFrame = bundle.frame.copy()
    return frame


def preprocess(frame: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    """Split features/target, coerce categorical dtypes, encode the label.

    XGBoost 1.5+ consumes pandas ``category`` columns directly when the model is
    built with ``enable_categorical=True`` — no one-hot encoding needed. Missing
    values (``'?'`` in the raw data) are converted to ``NaN`` and left alone,
    since XGBoost learns default directions natively (sparsity-aware split).
    """
    df = frame.copy()

    # The OpenML copy encodes missing values as the string "?"; make them NaN.
    df = df.replace("?", pd.NA)

    # Make every declared categorical column a pandas ``category``.
    for col in config.CATEGORICAL_COLUMNS:
        if col in df.columns:
            df[col] = df[col].astype("category")

    # Split X / y, and binarise the target to {0, 1}.
    y_raw = df[config.TARGET_COLUMN].astype(str).str.strip().str.rstrip(".")
    y = (y_raw == config.POSITIVE_LABEL).astype(int)
    y.name = "income_gt_50k"

    X = df.drop(columns=[config.TARGET_COLUMN])
    return X, y


def make_splits(
    X: pd.DataFrame,
    y: pd.Series,
    test_size: float = config.TEST_SIZE,
    val_size: float = config.VAL_SIZE,
    random_state: int = config.RANDOM_STATE,
) -> AdultSplits:
    """Deterministic train/val/test split with stratification on the target."""
    X_trainval, X_test, y_trainval, y_test = train_test_split(
        X, y,
        test_size=test_size,
        random_state=random_state,
        stratify=y,
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_trainval, y_trainval,
        test_size=val_size,
        random_state=random_state,
        stratify=y_trainval,
    )
    return AdultSplits(X_train, y_train, X_val, y_val, X_test, y_test)


def load_adult_splits(cache_dir: Path | None = None) -> AdultSplits:
    """Convenience: download, preprocess, split — one call."""
    frame = download_adult(cache_dir=cache_dir)
    X, y = preprocess(frame)
    return make_splits(X, y)
