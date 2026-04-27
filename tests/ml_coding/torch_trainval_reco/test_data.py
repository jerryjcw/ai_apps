"""Tests for data loading, splitting, and negative sampling.

We use tiny tab/pipe-separated fixtures written to a tmp dir so these tests
run hermetically. The real MovieLens download is covered by the end-to-end
script; here we verify the parsing + reindexing + sampling logic.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src import config as C
from src.data import (
    DatasetBundle,
    InteractionDataset,
    build_dataset,
    load_item_genres,
    load_ratings,
)


def _write_ratings(dir_path: Path, rows: list[tuple[int, int, int, int]]) -> None:
    path = dir_path / C.MOVIELENS_RATINGS_FILE
    path.write_text("\n".join(f"{u}\t{i}\t{r}\t{t}" for u, i, r, t in rows))


def _write_items(dir_path: Path, items: list[tuple[int, list[int]]]) -> None:
    path = dir_path / C.MOVIELENS_ITEMS_FILE
    lines = []
    for item_id, genres in items:
        assert len(genres) == C.MOVIELENS_NUM_GENRES
        fields = [str(item_id), f"title_{item_id}", "01-Jan-2000", "", "http://x"]
        fields.extend(str(g) for g in genres)
        lines.append("|".join(fields))
    path.write_text("\n".join(lines))


def test_load_ratings_parses_tab_file(tmp_path: Path) -> None:
    _write_ratings(tmp_path, [(1, 101, 5, 1000), (2, 102, 4, 1001)])
    df = load_ratings(tmp_path)
    assert list(df.columns) == ["user_raw", "item_raw", "rating", "timestamp"]
    assert len(df) == 2
    assert df.iloc[0]["user_raw"] == 1


def test_load_item_genres_parses_pipe_file(tmp_path: Path) -> None:
    genres_a = [1] + [0] * 18
    genres_b = [0, 1] + [0] * 17
    _write_items(tmp_path, [(10, genres_a), (11, genres_b)])
    df = load_item_genres(tmp_path)
    assert len(df) == 2
    assert df.iloc[0]["genre_0"] == 1
    assert df.iloc[1]["genre_1"] == 1


def test_build_dataset_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    extracted = tmp_path / C.MOVIELENS_SUBDIR
    extracted.mkdir()
    # 3 users x 3 items; user 0 rates item 0@t=1 then 1@t=3; user 1 rates 1@t=2 and 2@t=4; user 2 rates 0,1@t=5,6.
    _write_ratings(
        extracted,
        [
            (0, 0, 5, 1),
            (0, 1, 4, 3),
            (1, 1, 5, 2),
            (1, 2, 3, 4),
            (2, 0, 5, 5),
            (2, 1, 5, 6),
        ],
    )
    empty_genres = [0] * C.MOVIELENS_NUM_GENRES
    _write_items(extracted, [(0, empty_genres), (1, empty_genres), (2, empty_genres)])

    # Bypass the network download and point at our fixture.
    monkeypatch.setattr("src.data.download_movielens", lambda _dir: extracted)

    cfg = C.DataConfig(data_dir=tmp_path, min_user_interactions=2, num_eval_negatives=1)
    bundle = build_dataset(cfg)

    assert bundle.num_users == 3
    assert bundle.num_items == 3
    # 2 interactions per user, 1 held out for test -> 1 train per user.
    assert len(bundle.train_users) == 3
    assert len(bundle.test_users) == 3
    # Held-out positives should be the latest by timestamp.
    test_map = dict(zip(bundle.test_users.tolist(), bundle.test_pos_items.tolist()))
    assert test_map[0] == 1
    assert test_map[1] == 2
    assert test_map[2] == 1
    # Negatives must not overlap with any positive the user has seen.
    for u_idx, negs in zip(bundle.test_users, bundle.test_neg_items):
        for n in negs:
            assert int(n) not in bundle.user_positive_set[int(u_idx)]
    # Genres should be present and shaped (num_items, 19).
    assert bundle.item_genres is not None
    assert bundle.item_genres.shape == (3, C.MOVIELENS_NUM_GENRES)


def _tiny_bundle() -> DatasetBundle:
    train_u = np.array([0, 0, 1, 1, 2, 2], dtype=np.int64)
    train_i = np.array([0, 1, 1, 2, 0, 3], dtype=np.int64)
    return DatasetBundle(
        num_users=3,
        num_items=5,
        num_genres=C.MOVIELENS_NUM_GENRES,
        train_users=train_u,
        train_items=train_i,
        test_users=np.array([0, 1, 2], dtype=np.int64),
        test_pos_items=np.array([4, 0, 4], dtype=np.int64),
        test_neg_items=np.array([[2], [3], [1]], dtype=np.int64),
        user_positive_set={0: {0, 1, 4}, 1: {0, 1, 2}, 2: {0, 3, 4}},
        item_genres=None,
    )


def test_interaction_dataset_negatives_are_unseen() -> None:
    bundle = _tiny_bundle()
    ds = InteractionDataset(bundle, num_negatives=2, seed=0)
    # Positive count = 6, negatives = 12, total 18.
    assert len(ds) == 6 * 3
    neg_mask = ds._labels == 0
    for u, i in zip(ds._users[neg_mask], ds._items[neg_mask]):
        assert int(i) not in bundle.user_positive_set[int(u)]


def test_resample_negatives_changes_items() -> None:
    bundle = _tiny_bundle()
    ds = InteractionDataset(bundle, num_negatives=4, seed=123)
    first = ds._items.copy()
    ds._rng = np.random.default_rng(999)
    ds.resample_negatives()
    # Overwhelmingly unlikely that all 30 items come out identical.
    assert not np.array_equal(first, ds._items)
