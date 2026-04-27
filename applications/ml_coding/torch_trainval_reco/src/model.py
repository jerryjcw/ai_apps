"""Two-Tower recommender.

The Two-Tower architecture is the de-facto industry standard for retrieval /
candidate-generation at large-scale search and recommendation systems
(YouTube, Google Play, Pinterest, TikTok). A user tower and an item tower
each produce an embedding; the score is their dot product, which makes the
model ANN-friendly for production serving.

We keep the towers as independent `nn.Module`s so you can swap either side
without touching the rest of the pipeline (e.g. add text features to the
item tower, or a sequence encoder to the user tower).
"""

from __future__ import annotations

import torch
import torch.nn as nn

from . import config as C


def _build_mlp(in_dim: int, hidden: tuple[int, ...], out_dim: int, dropout: float) -> nn.Sequential:
    """Simple feed-forward stack used by both towers."""
    layers: list[nn.Module] = []
    prev = in_dim
    for h in hidden:
        layers += [nn.Linear(prev, h), nn.ReLU(), nn.Dropout(dropout)]
        prev = h
    layers.append(nn.Linear(prev, out_dim))
    return nn.Sequential(*layers)


class UserTower(nn.Module):
    """Maps a user id to a dense embedding."""

    def __init__(self, num_users: int, cfg: C.ModelConfig) -> None:
        super().__init__()
        self.embedding = nn.Embedding(num_users, cfg.embedding_dim)
        self.mlp = _build_mlp(cfg.embedding_dim, cfg.mlp_hidden, cfg.embedding_dim, cfg.dropout)
        nn.init.normal_(self.embedding.weight, std=0.01)

    def forward(self, user_ids: torch.Tensor) -> torch.Tensor:
        return self.mlp(self.embedding(user_ids))


class ItemTower(nn.Module):
    """Maps an item id (optionally + genre multi-hot) to a dense embedding."""

    def __init__(
        self,
        num_items: int,
        num_genres: int,
        cfg: C.ModelConfig,
        item_genres: torch.Tensor | None = None,
    ) -> None:
        super().__init__()
        self.embedding = nn.Embedding(num_items, cfg.embedding_dim)
        nn.init.normal_(self.embedding.weight, std=0.01)

        self.use_genres = cfg.use_item_genres and item_genres is not None
        if self.use_genres:
            # Static multi-hot feature stored as a buffer so it moves with .to(device).
            assert item_genres is not None
            self.register_buffer("item_genres", item_genres)
            in_dim = cfg.embedding_dim + num_genres
        else:
            in_dim = cfg.embedding_dim

        self.mlp = _build_mlp(in_dim, cfg.mlp_hidden, cfg.embedding_dim, cfg.dropout)

    def forward(self, item_ids: torch.Tensor) -> torch.Tensor:
        emb = self.embedding(item_ids)
        if self.use_genres:
            genres = self.item_genres[item_ids]
            emb = torch.cat([emb, genres], dim=-1)
        return self.mlp(emb)


class TwoTowerModel(nn.Module):
    """User tower + item tower with dot-product scoring.

    `score(u, i) = user_tower(u) . item_tower(i)` — a scalar per pair.
    BCE loss with a sigmoid applied outside the model (via BCEWithLogitsLoss).
    """

    def __init__(
        self,
        num_users: int,
        num_items: int,
        num_genres: int,
        cfg: C.ModelConfig,
        item_genres: torch.Tensor | None = None,
    ) -> None:
        super().__init__()
        self.user_tower = UserTower(num_users, cfg)
        self.item_tower = ItemTower(num_items, num_genres, cfg, item_genres=item_genres)

    def forward(self, user_ids: torch.Tensor, item_ids: torch.Tensor) -> torch.Tensor:
        u = self.user_tower(user_ids)
        i = self.item_tower(item_ids)
        return (u * i).sum(dim=-1)

    @torch.no_grad()
    def score_user_against_items(
        self, user_id: torch.Tensor, item_ids: torch.Tensor
    ) -> torch.Tensor:
        """Score one user against a batch of candidate items.

        `user_id` is a scalar long tensor; `item_ids` is shape (N,).
        Returns logits of shape (N,) — apply sigmoid if you need probabilities.
        """
        u = self.user_tower(user_id.unsqueeze(0))  # (1, D)
        i = self.item_tower(item_ids)              # (N, D)
        return (u * i).sum(dim=-1)
