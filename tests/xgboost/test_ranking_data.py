"""Unit tests for ``src.ranking.data``.

We mock MovieLens at a small scale to exercise the preprocessing logic without
hitting the network.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.ranking import config
from src.ranking.data import (
    RankingSplits,
    _assemble_features,
    _compute_stats,
    _per_user_split,
    make_ranking_splits,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_ratings() -> pd.DataFrame:
    """10 users × ~25 ratings each, graded 1-5, deterministic."""
    rng = np.random.default_rng(0)
    rows = []
    for u in range(1, 11):
        n = rng.integers(22, 30)
        for m in rng.choice(np.arange(1, 101), size=n, replace=False):
            rows.append((u, int(m), int(rng.integers(1, 6)), int(rng.integers(10**9, 10**9 + 10**6))))
    return pd.DataFrame(rows, columns=list(config.RATINGS_COLUMNS))


@pytest.fixture
def fake_movies() -> pd.DataFrame:
    """100 movies with title containing year and a few genre flags."""
    rng = np.random.default_rng(1)
    rows = []
    for m in range(1, 101):
        year = int(rng.integers(1950, 2000))
        flags = rng.integers(0, 2, size=len(config.GENRE_COLUMNS))
        rows.append((m, f"Film {m} ({year})", "", "", "", *flags.tolist()))
    frame = pd.DataFrame(rows, columns=list(config.MOVIE_COLUMNS))
    frame["year"] = (
        frame["title"].str.extract(r"\((\d{4})\)")[0].astype("Int32")
    )
    return frame


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def test_per_user_split_keeps_every_user(fake_ratings: pd.DataFrame) -> None:
    train, test = _per_user_split(fake_ratings, test_size=0.2, random_state=0)
    # Every user appears in both parts.
    assert set(train["user_id"]) == set(fake_ratings["user_id"])
    assert set(test["user_id"]) == set(fake_ratings["user_id"])
    # Disjoint rows (index-wise the original index is preserved by .copy()).
    assert len(train.index.intersection(test.index)) == 0


def test_per_user_split_respects_ratio(fake_ratings: pd.DataFrame) -> None:
    train, test = _per_user_split(fake_ratings, test_size=0.25, random_state=0)
    for user, group in fake_ratings.groupby("user_id"):
        n = len(group)
        n_test = (test["user_id"] == user).sum()
        # We use ``round``; accept ±1 row.
        assert abs(n_test - round(n * 0.25)) <= 1, f"user {user}: {n_test}/{n}"


def test_compute_stats_uses_only_given_split(fake_ratings: pd.DataFrame) -> None:
    train, _ = _per_user_split(fake_ratings, test_size=0.2, random_state=0)
    user_stats, movie_stats = _compute_stats(train)
    # Stats are defined for every train user/movie, nothing extra.
    assert set(user_stats["user_id"]) == set(train["user_id"])
    assert set(movie_stats["movie_id"]) == set(train["movie_id"])
    # No NaN in u_std (we fillna with 0).
    assert not user_stats["u_std"].isna().any()


def test_assemble_features_fills_cold_start(
    fake_ratings: pd.DataFrame, fake_movies: pd.DataFrame,
) -> None:
    train, test = _per_user_split(fake_ratings, test_size=0.2, random_state=0)
    user_stats, movie_stats = _compute_stats(train)
    global_mean = float(train["rating"].mean())

    # Force cold-start: invent a completely new movie id in the test split.
    cold = test.iloc[:1].copy()
    cold["movie_id"] = 999_999
    feat = _assemble_features(cold, fake_movies, user_stats, movie_stats, global_mean)
    # The cold row must not have NaN after cold-start fill.
    assert not feat[["u_mean", "m_mean", "year"]].isna().any(axis=None)
    # The cold movie's m_mean falls back to global_mean.
    assert feat["m_mean"].iloc[0] == pytest.approx(global_mean)
    assert feat["m_count"].iloc[0] == 0


# ---------------------------------------------------------------------------
# Top-level make_ranking_splits
# ---------------------------------------------------------------------------

def test_make_ranking_splits_shapes_and_qids(
    fake_ratings: pd.DataFrame, fake_movies: pd.DataFrame,
) -> None:
    splits = make_ranking_splits(
        fake_ratings, fake_movies,
        test_size=0.2, val_size=0.2, random_state=0,
        min_ratings_per_user=20,
    )
    assert isinstance(splits, RankingSplits)
    assert splits.X_train.shape[0] == len(splits.y_train) == len(splits.qid_train)
    assert splits.X_val.shape[0] == len(splits.y_val) == len(splits.qid_val)
    assert splits.X_test.shape[0] == len(splits.y_test) == len(splits.qid_test)
    # All three splits cover the same set of users.
    users = set(splits.qid_train)
    assert set(splits.qid_val) == users
    assert set(splits.qid_test) == users


def _is_contiguous(q: np.ndarray) -> bool:
    seen: set = set()
    prev = object()
    for v in q:
        if v != prev:
            if v in seen:
                return False
            seen.add(v)
            prev = v
    return True


def test_make_ranking_splits_qids_are_contiguous(
    fake_ratings: pd.DataFrame, fake_movies: pd.DataFrame,
) -> None:
    splits = make_ranking_splits(fake_ratings, fake_movies, random_state=0)
    # XGBoost ranking requires rows of the same query to be contiguous.
    assert _is_contiguous(splits.qid_train)
    assert _is_contiguous(splits.qid_val)
    assert _is_contiguous(splits.qid_test)


def test_make_ranking_splits_is_deterministic(
    fake_ratings: pd.DataFrame, fake_movies: pd.DataFrame,
) -> None:
    a = make_ranking_splits(fake_ratings, fake_movies, random_state=42)
    b = make_ranking_splits(fake_ratings, fake_movies, random_state=42)
    pd.testing.assert_frame_equal(a.X_train, b.X_train)
    np.testing.assert_array_equal(a.qid_test, b.qid_test)


def test_make_ranking_splits_drops_sparse_users(
    fake_ratings: pd.DataFrame, fake_movies: pd.DataFrame,
) -> None:
    # Set the cutoff so high that nothing remains — the call must still succeed
    # and produce empty splits rather than blow up.
    splits = make_ranking_splits(
        fake_ratings, fake_movies,
        min_ratings_per_user=10_000, random_state=0,
    )
    assert len(splits.X_train) == 0
    assert len(splits.qid_test) == 0
