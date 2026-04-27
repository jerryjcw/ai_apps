"""Central configuration for the Two-Tower MovieLens demo.

Keep all tunable knobs and path constants here so callers have a single
place to override them (e.g. via `TrainConfig(epochs=1)` in tests).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
CHECKPOINT_DIR = APP_DIR / "checkpoints"

MOVIELENS_URL = "https://files.grouplens.org/datasets/movielens/ml-100k.zip"
MOVIELENS_ARCHIVE = "ml-100k.zip"
MOVIELENS_SUBDIR = "ml-100k"
MOVIELENS_RATINGS_FILE = "u.data"       # user_id \t item_id \t rating \t timestamp
MOVIELENS_ITEMS_FILE = "u.item"         # movie metadata incl. 19 genre flags
MOVIELENS_NUM_GENRES = 19


@dataclass
class DataConfig:
    """Dataset-level settings. Subset fields allow fast iteration."""

    data_dir: Path = DATA_DIR
    min_user_interactions: int = 5
    """Drop users with fewer interactions — standard NCF filtering."""

    num_train_negatives: int = 4
    """Random negatives sampled per positive during training."""

    num_eval_negatives: int = 99
    """Negatives sampled per test positive for ranking eval (standard protocol)."""

    max_users: int | None = None
    """Optional cap on users (for quick debugging); None uses the full set."""

    seed: int = 42


@dataclass
class ModelConfig:
    embedding_dim: int = 32
    mlp_hidden: tuple[int, ...] = (64, 32)
    dropout: float = 0.1
    use_item_genres: bool = True


@dataclass
class TrainConfig:
    epochs: int = 5
    batch_size: int = 1024
    lr: float = 1e-3
    weight_decay: float = 1e-6
    eval_every: int = 1
    top_k: int = 10
    num_workers: int = 0
    device: str = "cpu"
    checkpoint_dir: Path = CHECKPOINT_DIR
    log_interval: int = 50


@dataclass
class Config:
    data: DataConfig = field(default_factory=DataConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    train: TrainConfig = field(default_factory=TrainConfig)
