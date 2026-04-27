"""Training loop for the Two-Tower model.

Training paradigm: BCE loss with random negative sampling. This is the
canonical recipe popularised by the NCF paper and is still the most common
starting point in industry retrieval-model tutorials because it is easy to
implement, easy to debug, and composes cleanly with any pair-scoring model.

The trainer keeps itself minimal — a single file you can read top to bottom
and modify. Swap the loss (e.g. for BPR or in-batch softmax) by replacing
`self.loss_fn`; swap the optimizer by passing one in; swap the sampler by
swapping the dataset.
"""

from __future__ import annotations

import time
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from . import config as C
from .data import DatasetBundle, InteractionDataset
from .evaluator import EvalResult, evaluate
from .model import TwoTowerModel


class Trainer:
    def __init__(
        self,
        model: TwoTowerModel,
        bundle: DatasetBundle,
        cfg: C.Config,
        loss_fn: nn.Module | None = None,
        optimizer: torch.optim.Optimizer | None = None,
    ) -> None:
        self.model = model.to(cfg.train.device)
        self.bundle = bundle
        self.cfg = cfg
        self.loss_fn = loss_fn or nn.BCEWithLogitsLoss()
        self.optimizer = optimizer or torch.optim.Adam(
            self.model.parameters(),
            lr=cfg.train.lr,
            weight_decay=cfg.train.weight_decay,
        )
        self.train_dataset = InteractionDataset(
            bundle=bundle,
            num_negatives=cfg.data.num_train_negatives,
            seed=cfg.data.seed,
        )

    def _loader(self) -> DataLoader:
        return DataLoader(
            self.train_dataset,
            batch_size=self.cfg.train.batch_size,
            shuffle=True,
            num_workers=self.cfg.train.num_workers,
            pin_memory=False,
        )

    def _train_one_epoch(self, epoch: int) -> float:
        self.model.train()
        # Resample negatives each epoch so the model sees fresh pairs.
        self.train_dataset.resample_negatives()
        loader = self._loader()
        total_loss = 0.0
        total_count = 0
        t0 = time.time()
        for step, batch in enumerate(loader):
            users = batch["user"].to(self.cfg.train.device, non_blocking=True)
            items = batch["item"].to(self.cfg.train.device, non_blocking=True)
            labels = batch["label"].to(self.cfg.train.device, non_blocking=True)

            logits = self.model(users, items)
            loss = self.loss_fn(logits, labels)

            self.optimizer.zero_grad(set_to_none=True)
            loss.backward()
            self.optimizer.step()

            total_loss += loss.item() * users.size(0)
            total_count += users.size(0)

            if (step + 1) % self.cfg.train.log_interval == 0:
                avg = total_loss / total_count
                print(f"  epoch {epoch} step {step + 1}/{len(loader)} loss={avg:.4f}")

        elapsed = time.time() - t0
        avg = total_loss / max(total_count, 1)
        print(f"[train] epoch {epoch} avg_loss={avg:.4f} time={elapsed:.1f}s")
        return avg

    def fit(self) -> list[EvalResult]:
        results: list[EvalResult] = []
        for epoch in range(1, self.cfg.train.epochs + 1):
            self._train_one_epoch(epoch)
            if epoch % self.cfg.train.eval_every == 0:
                res = evaluate(
                    self.model,
                    self.bundle,
                    k=self.cfg.train.top_k,
                    device=self.cfg.train.device,
                )
                print(
                    f"[eval]  epoch {epoch} HR@{res.k}={res.hr_at_k:.4f} "
                    f"NDCG@{res.k}={res.ndcg_at_k:.4f}"
                )
                results.append(res)
        return results

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "model_state": self.model.state_dict(),
                "num_users": self.bundle.num_users,
                "num_items": self.bundle.num_items,
                "num_genres": self.bundle.num_genres,
            },
            path,
        )
        print(f"[save]  checkpoint -> {path}")
