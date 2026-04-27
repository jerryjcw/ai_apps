"""MovieLens-100K download + feature engineering for learning-to-rank.

The MovieLens-100K dataset (Harper & Konstan, 2015) contains 100,000 ratings
on a 1–5 scale from 943 users across 1,682 movies. We treat each **user** as a
query and rank their rated movies by predicted preference. Ratings are used
directly as graded relevance labels.

All user- and movie-level aggregate features are computed from the **training
split only** to avoid target leakage.
"""

from __future__ import annotations

import io
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

from . import config


# ---------------------------------------------------------------------------
# Download + raw parse
# ---------------------------------------------------------------------------

def download_movielens_100k(cache_dir: Path | None = None) -> Path:
    """Download and unzip ml-100k into ``cache_dir``; return the extracted dir.

    Idempotent: if the directory already exists we skip the network round-trip.
    """
    cache_dir = Path(cache_dir) if cache_dir is not None else config.DATA_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    extracted = cache_dir / config.ML100K_DIR_NAME
    if extracted.exists() and (extracted / "u.data").exists():
        return extracted

    print(f"Downloading {config.ML100K_URL} ...")
    with urllib.request.urlopen(config.ML100K_URL) as resp:
        payload = resp.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        zf.extractall(cache_dir)
    assert extracted.exists(), f"expected {extracted} after unzip"
    return extracted


def load_ratings(extracted_dir: Path) -> pd.DataFrame:
    """Load u.data (tab-separated: user_id, movie_id, rating, timestamp)."""
    path = extracted_dir / "u.data"
    return pd.read_csv(
        path, sep="\t", header=None, names=list(config.RATINGS_COLUMNS),
        dtype={"user_id": np.int32, "movie_id": np.int32,
               "rating": np.int32, "timestamp": np.int64},
    )


def load_movies(extracted_dir: Path) -> pd.DataFrame:
    """Load u.item (pipe-separated) and extract release year from the title."""
    path = extracted_dir / "u.item"
    frame = pd.read_csv(
        path, sep="|", header=None, names=list(config.MOVIE_COLUMNS),
        encoding="latin-1",
    )
    # ml-100k titles end with " (YYYY)"; extract the year.
    year = frame["title"].str.extract(r"\((\d{4})\)\s*$")[0]
    frame["year"] = pd.to_numeric(year, errors="coerce").astype("Int32")
    return frame


# ---------------------------------------------------------------------------
# Feature engineering + splits
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RankingSplits:
    """Train / val / test splits ready for ``XGBRanker``.

    Each DataFrame has rows sorted by ``user_id`` so that rows belonging to the
    same query (user) are contiguous — a hard requirement of the XGBoost
    ranking API when passing ``qid``.
    """
    X_train: pd.DataFrame
    y_train: pd.Series
    qid_train: np.ndarray

    X_val: pd.DataFrame
    y_val: pd.Series
    qid_val: np.ndarray

    X_test: pd.DataFrame
    y_test: pd.Series
    qid_test: np.ndarray

    feature_columns: tuple[str, ...]


def _per_user_split(
    ratings: pd.DataFrame,
    test_size: float,
    random_state: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-user random split so every user appears in both train and held-out."""
    rng = np.random.default_rng(random_state)
    is_test = np.zeros(len(ratings), dtype=bool)
    # Iterate by user so each user independently gets ``test_size`` of its rows.
    for _, idx in ratings.groupby("user_id", sort=False).indices.items():
        idx = np.asarray(idx)
        k = max(1, int(round(len(idx) * test_size)))
        chosen = rng.choice(idx, size=k, replace=False)
        is_test[chosen] = True
    return ratings.loc[~is_test].copy(), ratings.loc[is_test].copy()


def _compute_stats(train: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate user- and movie-level statistics from the training split only.

    Returned frames are keyed by user_id / movie_id respectively.
    """
    user_stats = train.groupby("user_id")["rating"].agg(
        u_mean="mean", u_count="count", u_std="std",
    ).reset_index()
    user_stats["u_std"] = user_stats["u_std"].fillna(0.0)

    movie_stats = train.groupby("movie_id")["rating"].agg(
        m_mean="mean", m_count="count",
    ).reset_index()
    return user_stats, movie_stats


def _assemble_features(
    ratings: pd.DataFrame,
    movies: pd.DataFrame,
    user_stats: pd.DataFrame,
    movie_stats: pd.DataFrame,
    global_mean: float,
) -> pd.DataFrame:
    """Join per-row features onto a ratings frame.

    Cold-start handling: users or movies missing from the training stats are
    filled with ``global_mean`` / zero counts — a sane fallback that mirrors
    production "new user, new item" behaviour.
    """
    frame = ratings.merge(user_stats, on="user_id", how="left")
    frame = frame.merge(movie_stats, on="movie_id", how="left")
    movie_subset = movies[["movie_id", "year", *config.GENRE_COLUMNS]]
    frame = frame.merge(movie_subset, on="movie_id", how="left")

    # Fill cold-start NaNs.
    frame["u_mean"] = frame["u_mean"].fillna(global_mean)
    frame["u_count"] = frame["u_count"].fillna(0).astype(np.int32)
    frame["u_std"] = frame["u_std"].fillna(0.0)
    frame["m_mean"] = frame["m_mean"].fillna(global_mean)
    frame["m_count"] = frame["m_count"].fillna(0).astype(np.int32)
    # Movie year may be NaN in the raw data; median is a safe constant.
    median_year = frame["year"].median()
    fill_year = int(median_year) if pd.notna(median_year) else 0
    frame["year"] = frame["year"].fillna(fill_year).astype(np.int32)
    return frame


def make_ranking_splits(
    ratings: pd.DataFrame,
    movies: pd.DataFrame,
    *,
    test_size: float = config.TEST_SIZE,
    val_size: float = config.VAL_SIZE,
    random_state: int = config.RANDOM_STATE,
    min_ratings_per_user: int = config.MIN_RATINGS_PER_USER,
) -> RankingSplits:
    """Split ratings into train/val/test with per-user groups + no leakage.

    1. Drop users with fewer than ``min_ratings_per_user`` ratings.
    2. Split **per user** into test and train+val.
    3. Split train+val **per user** into val and train.
    4. Compute user/movie stats from the train fold only.
    5. Assemble features for each split using those train-only stats.
    6. Sort each split by ``user_id`` so XGBoost's qid API sees contiguous groups.
    """
    counts = ratings.groupby("user_id")["rating"].transform("count")
    ratings = ratings.loc[counts >= min_ratings_per_user].reset_index(drop=True)

    feature_cols = (
        "u_mean", "u_count", "u_std",
        "m_mean", "m_count", "year",
        *config.GENRE_COLUMNS,
    )

    if ratings.empty:
        empty_X = pd.DataFrame({c: pd.Series(dtype=np.float32) for c in feature_cols})
        empty_y = pd.Series(dtype=np.int32)
        empty_qid = np.array([], dtype=np.int32)
        return RankingSplits(
            X_train=empty_X.copy(), y_train=empty_y.copy(), qid_train=empty_qid,
            X_val=empty_X.copy(), y_val=empty_y.copy(), qid_val=empty_qid,
            X_test=empty_X.copy(), y_test=empty_y.copy(), qid_test=empty_qid,
            feature_columns=feature_cols,
        )

    trainval, test = _per_user_split(ratings, test_size, random_state)
    train, val = _per_user_split(trainval, val_size, random_state + 1)

    user_stats, movie_stats = _compute_stats(train)
    global_mean = float(train["rating"].mean())

    def prep(split: pd.DataFrame) -> pd.DataFrame:
        feat = _assemble_features(split, movies, user_stats, movie_stats, global_mean)
        return feat.sort_values("user_id", kind="stable").reset_index(drop=True)

    train_f = prep(train)
    val_f = prep(val)
    test_f = prep(test)

    def as_xyq(frame: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series, np.ndarray]:
        X = frame[list(feature_cols)].astype(np.float32)
        y = frame["rating"].astype(np.int32)
        qid = frame["user_id"].to_numpy()
        return X, y, qid

    Xtr, ytr, qtr = as_xyq(train_f)
    Xvl, yvl, qvl = as_xyq(val_f)
    Xte, yte, qte = as_xyq(test_f)

    return RankingSplits(
        X_train=Xtr, y_train=ytr, qid_train=qtr,
        X_val=Xvl, y_val=yvl, qid_val=qvl,
        X_test=Xte, y_test=yte, qid_test=qte,
        feature_columns=feature_cols,
    )


def load_ranking_splits(cache_dir: Path | None = None) -> RankingSplits:
    """Download → parse → split — one call."""
    extracted = download_movielens_100k(cache_dir=cache_dir)
    ratings = load_ratings(extracted)
    movies = load_movies(extracted)
    return make_ranking_splits(ratings, movies)
