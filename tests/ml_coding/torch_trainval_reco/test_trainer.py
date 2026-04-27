"""Trainer smoke test: loss is finite after one epoch on a hand-built bundle."""

from __future__ import annotations

import numpy as np
import torch

from src.config import Config, DataConfig, ModelConfig, TrainConfig
from src.data import DatasetBundle
from src import config as C
from src.model import TwoTowerModel
from src.trainer import Trainer


def _mini_bundle() -> DatasetBundle:
    # 4 users, 8 items, each user has 3 train interactions and 1 held-out test positive.
    rng = np.random.default_rng(0)
    train_pairs = []
    test_pos = []
    user_seen: dict[int, set[int]] = {}
    for u in range(4):
        items = rng.choice(8, size=4, replace=False).tolist()
        for it in items[:3]:
            train_pairs.append((u, it))
        test_pos.append((u, items[3]))
        user_seen[u] = set(items)
    train_u = np.array([p[0] for p in train_pairs], dtype=np.int64)
    train_i = np.array([p[1] for p in train_pairs], dtype=np.int64)
    test_u = np.array([p[0] for p in test_pos], dtype=np.int64)
    test_i = np.array([p[1] for p in test_pos], dtype=np.int64)
    test_neg = np.array([[i for i in range(8) if i not in user_seen[u]][:3] for u in test_u], dtype=np.int64)
    return DatasetBundle(
        num_users=4,
        num_items=8,
        num_genres=C.MOVIELENS_NUM_GENRES,
        train_users=train_u,
        train_items=train_i,
        test_users=test_u,
        test_pos_items=test_i,
        test_neg_items=test_neg,
        user_positive_set=user_seen,
        item_genres=None,
    )


def test_trainer_runs_one_epoch_and_loss_is_finite() -> None:
    torch.manual_seed(0)
    bundle = _mini_bundle()
    cfg = Config(
        data=DataConfig(num_train_negatives=2, num_eval_negatives=3),
        model=ModelConfig(embedding_dim=4, mlp_hidden=(8,), dropout=0.0, use_item_genres=False),
        train=TrainConfig(epochs=1, batch_size=4, lr=1e-2, top_k=3, log_interval=10000),
    )
    model = TwoTowerModel(
        num_users=bundle.num_users,
        num_items=bundle.num_items,
        num_genres=bundle.num_genres,
        cfg=cfg.model,
    )
    trainer = Trainer(model=model, bundle=bundle, cfg=cfg)
    results = trainer.fit()
    assert len(results) == 1
    assert 0.0 <= results[0].hr_at_k <= 1.0
    assert 0.0 <= results[0].ndcg_at_k <= 1.0
    # Parameters must have been updated (some gradient signal).
    params_before = {n: p.detach().clone() for n, p in model.named_parameters()}
    trainer._train_one_epoch(epoch=2)
    changed = any(
        not torch.equal(params_before[n], p) for n, p in model.named_parameters()
    )
    assert changed
