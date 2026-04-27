"""Tests for HR@K, NDCG@K, and the inference helper."""

from __future__ import annotations

import math

import numpy as np
import torch
import torch.nn as nn

from src import config as C
from src.data import DatasetBundle
from src.evaluator import evaluate, top_k_for_user


class _FixedScoreModel(nn.Module):
    """Deterministic scorer used to check HR/NDCG math without training.

    `score(u, i) = lookup[u, i]` — implemented as a 2D parameter so the real
    `TwoTowerModel.forward(user_ids, item_ids)` signature is preserved.
    """

    def __init__(self, scores: torch.Tensor) -> None:
        super().__init__()
        self.scores = nn.Parameter(scores, requires_grad=False)

    def forward(self, users: torch.Tensor, items: torch.Tensor) -> torch.Tensor:
        return self.scores[users, items]

    def score_user_against_items(
        self, user_id: torch.Tensor, item_ids: torch.Tensor
    ) -> torch.Tensor:
        return self.scores[user_id, item_ids]


def _bundle_for_eval(num_users: int, num_items: int) -> DatasetBundle:
    return DatasetBundle(
        num_users=num_users,
        num_items=num_items,
        num_genres=C.MOVIELENS_NUM_GENRES,
        train_users=np.array([], dtype=np.int64),
        train_items=np.array([], dtype=np.int64),
        test_users=np.arange(num_users, dtype=np.int64),
        test_pos_items=np.array([0, 1, 2], dtype=np.int64),
        test_neg_items=np.array(
            [[1, 2, 3], [0, 2, 3], [0, 1, 3]], dtype=np.int64
        ),
        user_positive_set={0: {0}, 1: {1}, 2: {2}},
        item_genres=None,
    )


def test_evaluate_perfect_model_gives_hr_one_ndcg_one() -> None:
    bundle = _bundle_for_eval(num_users=3, num_items=4)
    # Make every positive score higher than every negative.
    scores = torch.full((3, 4), -1.0)
    for u, pos in zip(bundle.test_users, bundle.test_pos_items):
        scores[u, pos] = 10.0
    model = _FixedScoreModel(scores)

    res = evaluate(model, bundle, k=2, device="cpu", batch_size=2)
    assert res.hr_at_k == 1.0
    assert res.ndcg_at_k == 1.0


def test_evaluate_worst_model_gives_zero() -> None:
    bundle = _bundle_for_eval(num_users=3, num_items=4)
    scores = torch.full((3, 4), 1.0)
    # Put positives strictly lowest; k=1 so they can't land in top-1.
    for u, pos in zip(bundle.test_users, bundle.test_pos_items):
        scores[u, pos] = -10.0
    model = _FixedScoreModel(scores)

    res = evaluate(model, bundle, k=1, device="cpu", batch_size=4)
    assert res.hr_at_k == 0.0
    assert res.ndcg_at_k == 0.0


def test_evaluate_mid_rank_ndcg_formula() -> None:
    # One user, positive ranked 2nd of 4 candidates (one negative beats it).
    scores = torch.tensor([[0.5, 1.0, 0.0, -1.0]])
    bundle = DatasetBundle(
        num_users=1,
        num_items=4,
        num_genres=C.MOVIELENS_NUM_GENRES,
        train_users=np.array([], dtype=np.int64),
        train_items=np.array([], dtype=np.int64),
        test_users=np.array([0], dtype=np.int64),
        test_pos_items=np.array([0], dtype=np.int64),
        test_neg_items=np.array([[1, 2, 3]], dtype=np.int64),
        user_positive_set={0: {0}},
        item_genres=None,
    )
    model = _FixedScoreModel(scores)
    res = evaluate(model, bundle, k=2, device="cpu")
    # Rank is 1 (0-indexed), NDCG = 1/log2(1+2) = 1/log2(3)
    assert res.hr_at_k == 1.0
    assert math.isclose(res.ndcg_at_k, 1.0 / math.log2(3.0), rel_tol=1e-6)


def test_top_k_excludes_seen_items() -> None:
    scores = torch.tensor([[5.0, 4.0, 3.0, 2.0, 1.0]])
    model = _FixedScoreModel(scores)
    # Item 0 is seen and should be filtered out even though it has the highest score.
    recs = top_k_for_user(
        model=model, user_id=0, num_items=5, exclude={0}, k=3, device="cpu"
    )
    rec_items = [i for i, _ in recs]
    assert 0 not in rec_items
    assert rec_items == [1, 2, 3]
