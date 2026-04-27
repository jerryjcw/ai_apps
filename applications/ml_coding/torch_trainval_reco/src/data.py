"""MovieLens-100K loading, leave-one-out split, and torch Datasets.

MovieLens-100K is a real dataset of 100,000 ratings (1-5) from 943 users on
1,682 movies, collected at the University of Minnesota via the MovieLens
website. We treat it as implicit feedback (any rating counts as a positive
interaction), which is the standard protocol for retrieval-style evaluation
used by the NCF (He et al., 2017) line of work.

Evaluation protocol:
    For each user we hold out the most recent interaction as the test
    positive. At eval time we rank the positive against 99 randomly sampled
    items the user has never interacted with, then compute HR@K and NDCG@K.
    This is the NCF paper's protocol and keeps evaluation cheap enough to run
    on CPU.
"""

from __future__ import annotations

import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset

from . import config as C


# -----------------------------------------------------------------------------
# Download / parsing
# -----------------------------------------------------------------------------


def download_movielens(data_dir: Path = C.DATA_DIR) -> Path:
    """Ensure ml-100k is present on disk; return the extracted directory.

    Idempotent: if the extracted folder already exists we do nothing.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    extracted = data_dir / C.MOVIELENS_SUBDIR
    if extracted.exists():
        return extracted

    archive_path = data_dir / C.MOVIELENS_ARCHIVE
    if not archive_path.exists():
        print(f"[data] downloading {C.MOVIELENS_URL} -> {archive_path}")
        urllib.request.urlretrieve(C.MOVIELENS_URL, archive_path)

    with zipfile.ZipFile(archive_path) as zf:
        zf.extractall(data_dir)
    return extracted


def load_ratings(extracted_dir: Path) -> pd.DataFrame:
    """Return a DataFrame with raw user/item IDs and timestamps."""
    path = extracted_dir / C.MOVIELENS_RATINGS_FILE
    df = pd.read_csv(
        path,
        sep="\t",
        header=None,
        names=["user_raw", "item_raw", "rating", "timestamp"],
        engine="c",
    )
    return df


def load_item_genres(extracted_dir: Path) -> pd.DataFrame:
    """Return raw item_id + 19-dim genre multi-hot (last 19 columns of u.item).

    Column layout of u.item (pipe-separated, latin-1):
        movie_id | title | release_date | video_release | imdb_url | 19 genres
    """
    path = extracted_dir / C.MOVIELENS_ITEMS_FILE
    cols = ["item_raw", "title", "release_date", "video_release", "imdb_url"] + [
        f"genre_{i}" for i in range(C.MOVIELENS_NUM_GENRES)
    ]
    df = pd.read_csv(path, sep="|", header=None, names=cols, encoding="latin-1")
    genre_cols = [f"genre_{i}" for i in range(C.MOVIELENS_NUM_GENRES)]
    return df[["item_raw", *genre_cols]]


# -----------------------------------------------------------------------------
# Dataset assembly
# -----------------------------------------------------------------------------


@dataclass
class DatasetBundle:
    """Everything downstream code needs after preprocessing."""

    num_users: int
    num_items: int
    num_genres: int
    # Training interactions as parallel int64 arrays (reindexed).
    train_users: np.ndarray
    train_items: np.ndarray
    # Held-out positive per user (arrays aligned by test_users[i]).
    test_users: np.ndarray
    test_pos_items: np.ndarray
    # Sampled negatives for each test user: shape (num_test, num_eval_negatives).
    test_neg_items: np.ndarray
    # user_id -> set of all items the user has ever interacted with (for negative filtering).
    user_positive_set: dict[int, set[int]]
    # item features: shape (num_items, num_genres) float32, or None if unused.
    item_genres: np.ndarray | None


def _reindex(series: pd.Series) -> tuple[np.ndarray, dict]:
    uniq = np.sort(series.unique())
    mapping = {raw: i for i, raw in enumerate(uniq.tolist())}
    reindexed = series.map(mapping).to_numpy(dtype=np.int64)
    return reindexed, mapping


def build_dataset(cfg: C.DataConfig) -> DatasetBundle:
    """Download, parse, filter, reindex, and split MovieLens-100K."""
    extracted = download_movielens(cfg.data_dir)
    ratings = load_ratings(extracted)

    # Cap users for quick runs. We pick the first N by raw id for determinism.
    if cfg.max_users is not None:
        keep = np.sort(ratings["user_raw"].unique())[: cfg.max_users]
        ratings = ratings[ratings["user_raw"].isin(keep)].copy()

    # Drop low-activity users (NCF-standard filtering).
    counts = ratings.groupby("user_raw").size()
    active = counts[counts >= cfg.min_user_interactions].index
    ratings = ratings[ratings["user_raw"].isin(active)].copy()

    # Contiguous 0..N indexing for embedding tables.
    user_ids, user_map = _reindex(ratings["user_raw"])
    item_ids, item_map = _reindex(ratings["item_raw"])
    ratings = ratings.assign(user=user_ids, item=item_ids)
    num_users = len(user_map)
    num_items = len(item_map)

    # Leave-one-out split: most recent interaction per user goes to test.
    ratings = ratings.sort_values(["user", "timestamp"], kind="stable")
    is_last = ratings.groupby("user")["timestamp"].transform("max") == ratings["timestamp"]
    # Handle ties on timestamp by keeping the final row per user.
    test_mask = is_last & ~ratings.duplicated(subset=["user"], keep="last")
    test_df = ratings[test_mask]
    train_df = ratings[~test_mask]

    user_positive_set: dict[int, set[int]] = {}
    for u, grp in ratings.groupby("user"):
        user_positive_set[int(u)] = set(int(x) for x in grp["item"].tolist())

    # Sample 99 negatives per test user (standard NCF protocol).
    rng = np.random.default_rng(cfg.seed)
    test_users_arr = test_df["user"].to_numpy(dtype=np.int64)
    test_pos_arr = test_df["item"].to_numpy(dtype=np.int64)
    test_neg_arr = np.empty((len(test_users_arr), cfg.num_eval_negatives), dtype=np.int64)
    for row, u in enumerate(test_users_arr):
        seen = user_positive_set[int(u)]
        negs: list[int] = []
        while len(negs) < cfg.num_eval_negatives:
            cand = int(rng.integers(0, num_items))
            if cand not in seen:
                negs.append(cand)
        test_neg_arr[row] = negs

    # Item genre features.
    item_genres: np.ndarray | None = None
    try:
        genre_df = load_item_genres(extracted)
        genre_df = genre_df[genre_df["item_raw"].isin(item_map.keys())].copy()
        genre_df["item"] = genre_df["item_raw"].map(item_map)
        genre_cols = [c for c in genre_df.columns if c.startswith("genre_")]
        item_genres = np.zeros((num_items, len(genre_cols)), dtype=np.float32)
        item_genres[genre_df["item"].to_numpy()] = genre_df[genre_cols].to_numpy(dtype=np.float32)
    except FileNotFoundError:
        item_genres = None

    return DatasetBundle(
        num_users=num_users,
        num_items=num_items,
        num_genres=C.MOVIELENS_NUM_GENRES,
        # .copy() so downstream torch.as_tensor calls aren't on read-only views.
        train_users=train_df["user"].to_numpy(dtype=np.int64).copy(),
        train_items=train_df["item"].to_numpy(dtype=np.int64).copy(),
        test_users=test_users_arr.copy(),
        test_pos_items=test_pos_arr.copy(),
        test_neg_items=test_neg_arr.copy(),
        user_positive_set=user_positive_set,
        item_genres=item_genres,
    )


# -----------------------------------------------------------------------------
# Torch Dataset: positives + on-the-fly random negatives
# -----------------------------------------------------------------------------


class InteractionDataset(Dataset):
    """Yields (user, item, label) with `num_negatives` random negatives per positive.

    Negatives are resampled every time `resample_negatives()` is called,
    which the trainer does once per epoch — this is the standard NCF recipe.
    """

    def __init__(
        self,
        bundle: DatasetBundle,
        num_negatives: int,
        seed: int = 0,
    ) -> None:
        self.bundle = bundle
        self.num_negatives = num_negatives
        self._rng = np.random.default_rng(seed)
        self._users: np.ndarray = np.empty(0, dtype=np.int64)
        self._items: np.ndarray = np.empty(0, dtype=np.int64)
        self._labels: np.ndarray = np.empty(0, dtype=np.float32)
        self.resample_negatives()

    def resample_negatives(self) -> None:
        pos_u = self.bundle.train_users
        pos_i = self.bundle.train_items
        n_pos = len(pos_u)
        k = self.num_negatives
        num_items = self.bundle.num_items
        pos_set = self.bundle.user_positive_set

        neg_u = np.repeat(pos_u, k)
        neg_i = np.empty(n_pos * k, dtype=np.int64)
        # Vectorized candidate draw, then repair collisions per-user.
        cand = self._rng.integers(0, num_items, size=n_pos * k).astype(np.int64)
        for idx in range(n_pos * k):
            u = int(neg_u[idx])
            c = int(cand[idx])
            while c in pos_set[u]:
                c = int(self._rng.integers(0, num_items))
            neg_i[idx] = c

        self._users = np.concatenate([pos_u, neg_u])
        self._items = np.concatenate([pos_i, neg_i])
        self._labels = np.concatenate([
            np.ones(n_pos, dtype=np.float32),
            np.zeros(n_pos * k, dtype=np.float32),
        ])
        perm = self._rng.permutation(len(self._users))
        self._users = self._users[perm]
        self._items = self._items[perm]
        self._labels = self._labels[perm]

    def __len__(self) -> int:
        return len(self._users)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        return {
            "user": torch.as_tensor(self._users[idx], dtype=torch.long),
            "item": torch.as_tensor(self._items[idx], dtype=torch.long),
            "label": torch.as_tensor(self._labels[idx], dtype=torch.float32),
        }
