"""Tests for UserTower, ItemTower, and TwoTowerModel."""

from __future__ import annotations

import torch

from src.config import ModelConfig
from src.model import ItemTower, TwoTowerModel, UserTower


def test_user_tower_output_shape() -> None:
    cfg = ModelConfig(embedding_dim=16, mlp_hidden=(32,), dropout=0.0)
    tower = UserTower(num_users=10, cfg=cfg)
    out = tower(torch.tensor([0, 3, 9]))
    assert out.shape == (3, 16)


def test_item_tower_with_and_without_genres() -> None:
    cfg = ModelConfig(embedding_dim=8, mlp_hidden=(16,), dropout=0.0, use_item_genres=True)
    genres = torch.zeros(5, 19)
    genres[1, 0] = 1.0
    tower = ItemTower(num_items=5, num_genres=19, cfg=cfg, item_genres=genres)
    assert tower.use_genres
    out = tower(torch.tensor([0, 1, 4]))
    assert out.shape == (3, 8)

    cfg2 = ModelConfig(embedding_dim=8, mlp_hidden=(16,), dropout=0.0, use_item_genres=False)
    tower2 = ItemTower(num_items=5, num_genres=19, cfg=cfg2, item_genres=None)
    assert not tower2.use_genres
    out2 = tower2(torch.tensor([0, 1, 4]))
    assert out2.shape == (3, 8)


def test_two_tower_forward_returns_scalar_per_pair() -> None:
    cfg = ModelConfig(embedding_dim=8, mlp_hidden=(16,), dropout=0.0, use_item_genres=False)
    model = TwoTowerModel(num_users=7, num_items=5, num_genres=19, cfg=cfg)
    users = torch.tensor([0, 1, 2, 3])
    items = torch.tensor([4, 0, 1, 2])
    logits = model(users, items)
    assert logits.shape == (4,)
    assert torch.isfinite(logits).all()


def test_score_user_against_items_shape() -> None:
    cfg = ModelConfig(embedding_dim=8, mlp_hidden=(16,), dropout=0.0, use_item_genres=False)
    model = TwoTowerModel(num_users=3, num_items=6, num_genres=19, cfg=cfg)
    scores = model.score_user_against_items(
        torch.tensor(1, dtype=torch.long), torch.arange(6, dtype=torch.long)
    )
    assert scores.shape == (6,)
