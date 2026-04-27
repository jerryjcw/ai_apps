"""CLI entry point: `python -m src.run` from the project root.

Runs the full pipeline end-to-end on MovieLens-100K:
  1. Download + parse dataset
  2. Build Two-Tower model
  3. Train for N epochs with BCE + negative sampling
  4. Evaluate with HR@10 / NDCG@10
  5. Save checkpoint and print top-10 recommendations for a sample user
"""

from __future__ import annotations

import argparse
from pathlib import Path

import torch

from . import config as C
from .data import build_dataset
from .evaluator import top_k_for_user
from .model import TwoTowerModel
from .trainer import Trainer


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=C.TrainConfig.epochs)
    p.add_argument("--batch-size", type=int, default=C.TrainConfig.batch_size)
    p.add_argument("--lr", type=float, default=C.TrainConfig.lr)
    p.add_argument("--top-k", type=int, default=C.TrainConfig.top_k)
    p.add_argument(
        "--max-users",
        type=int,
        default=None,
        help="Optional cap on #users for quick iteration (full dataset if unset).",
    )
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", type=str, default="cpu")
    p.add_argument(
        "--checkpoint",
        type=Path,
        default=C.CHECKPOINT_DIR / "two_tower.pt",
    )
    p.add_argument("--sample-user", type=int, default=0, help="User id for inference demo.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    torch.manual_seed(args.seed)

    cfg = C.Config()
    cfg.data.seed = args.seed
    cfg.data.max_users = args.max_users
    cfg.train.epochs = args.epochs
    cfg.train.batch_size = args.batch_size
    cfg.train.lr = args.lr
    cfg.train.top_k = args.top_k
    cfg.train.device = args.device

    print("[init] building dataset from MovieLens-100K ...")
    bundle = build_dataset(cfg.data)
    print(
        f"[init] num_users={bundle.num_users} num_items={bundle.num_items} "
        f"train_pairs={len(bundle.train_users)} test_users={len(bundle.test_users)}"
    )

    item_genres = (
        torch.from_numpy(bundle.item_genres) if bundle.item_genres is not None else None
    )
    model = TwoTowerModel(
        num_users=bundle.num_users,
        num_items=bundle.num_items,
        num_genres=bundle.num_genres,
        cfg=cfg.model,
        item_genres=item_genres,
    )
    trainer = Trainer(model=model, bundle=bundle, cfg=cfg)
    trainer.fit()
    trainer.save(args.checkpoint)

    # Tiny inference demo.
    user_id = int(args.sample_user)
    seen = bundle.user_positive_set.get(user_id, set())
    recs = top_k_for_user(
        model=model,
        user_id=user_id,
        num_items=bundle.num_items,
        exclude=seen,
        k=args.top_k,
        device=args.device,
    )
    print(f"[infer] top-{args.top_k} recommendations for user {user_id}:")
    for rank, (item_id, score) in enumerate(recs, 1):
        print(f"  {rank:>2}. item {item_id:>4}  logit={score:+.3f}")


if __name__ == "__main__":
    main()
