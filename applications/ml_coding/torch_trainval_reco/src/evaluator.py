"""HR@K and NDCG@K under the leave-one-out protocol (NCF, He et al. 2017).

For each test user we have 1 positive item and 99 sampled negatives. We
rank the 100 candidates by model score; HR@K is 1 if the positive lands in
the top-K, and NDCG@K = 1 / log2(rank + 1) when it does.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import torch

from .data import DatasetBundle
from .model import TwoTowerModel


@dataclass
class EvalResult:
    hr_at_k: float
    ndcg_at_k: float
    k: int

    def as_dict(self) -> dict[str, float]:
        return {f"HR@{self.k}": self.hr_at_k, f"NDCG@{self.k}": self.ndcg_at_k}


def _dcg_gain(rank: int) -> float:
    # rank is 0-indexed; NDCG formula from the NCF paper.
    return 1.0 / math.log2(rank + 2.0)


@torch.no_grad()
def evaluate(
    model: TwoTowerModel,
    bundle: DatasetBundle,
    k: int = 10,
    device: str = "cpu",
    batch_size: int = 256,
) -> EvalResult:
    """Score (pos + 99 negatives) per test user and compute HR@K, NDCG@K."""
    model.eval()
    users = bundle.test_users
    pos_items = bundle.test_pos_items
    neg_items = bundle.test_neg_items  # (num_test, 99)

    num_test = len(users)
    num_candidates = 1 + neg_items.shape[1]
    hits = 0
    ndcg_sum = 0.0

    for start in range(0, num_test, batch_size):
        end = min(start + batch_size, num_test)
        u = torch.as_tensor(users[start:end], dtype=torch.long, device=device)
        pos = torch.as_tensor(pos_items[start:end], dtype=torch.long, device=device).unsqueeze(1)
        neg = torch.as_tensor(neg_items[start:end], dtype=torch.long, device=device)
        cand = torch.cat([pos, neg], dim=1)  # (B, 100); index 0 is the positive

        # Broadcast user across candidates, score in one shot.
        u_rep = u.unsqueeze(1).expand_as(cand)
        scores = model(u_rep.reshape(-1), cand.reshape(-1)).view(cand.shape)

        # Rank of the positive among the 100 candidates.
        # argsort desc; count how many candidates outrank the positive.
        pos_score = scores[:, 0:1]
        rank = (scores > pos_score).sum(dim=1)
        # Ties broken in favor of the positive — matches common NCF eval code.
        rank_np = rank.cpu().numpy()
        for r in rank_np:
            if r < k:
                hits += 1
                ndcg_sum += _dcg_gain(int(r))

    return EvalResult(hr_at_k=hits / num_test, ndcg_at_k=ndcg_sum / num_test, k=k)


def top_k_for_user(
    model: TwoTowerModel,
    user_id: int,
    num_items: int,
    exclude: set[int] | None = None,
    k: int = 10,
    device: str = "cpu",
) -> list[tuple[int, float]]:
    """Score every item for one user and return the top-K (item_id, logit) pairs.

    This is the 'inference' path the demo shows in its README — the kind of
    call a retrieval service would make against a trained model.
    """
    model.eval()
    with torch.no_grad():
        user_t = torch.as_tensor([user_id], dtype=torch.long, device=device)
        item_t = torch.arange(num_items, dtype=torch.long, device=device)
        scores = model.score_user_against_items(user_t.squeeze(0), item_t)

    scores_np = scores.cpu().numpy()
    if exclude:
        mask_idx = np.fromiter(exclude, dtype=np.int64)
        scores_np[mask_idx] = -np.inf
    top = np.argpartition(-scores_np, kth=min(k, num_items - 1))[:k]
    top = top[np.argsort(-scores_np[top])]
    return [(int(i), float(scores_np[i])) for i in top]
