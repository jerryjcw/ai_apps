from dataclasses import dataclass, field
from pathlib import Path
import logging
import os
import tomllib

from dotenv import load_dotenv

from src.errors import ConfigError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionConfig:
    score_threshold: float = 0.60  # Ranking score 0.0-1.0 (displayed as 0-100 in Scholar Inbox UI)
    schedule_cron: str = "0 8 * * 1"
    backfill_score_threshold: float = 0.60  # Score threshold for backfill (0.0-1.0 scale)
    backfill_lookback_days: int = 30


@dataclass(frozen=True)
class CitationConfig:
    semantic_scholar_batch_size: int = 100
    poll_schedule_cron: str = "0 6 * * 3"


@dataclass(frozen=True)
class PruningConfig:
    min_age_months: int = 6
    min_citations: int = 10
    min_velocity: float = 1.0


@dataclass(frozen=True)
class PromotionConfig:
    citation_threshold: int = 50
    velocity_threshold: float = 10.0


@dataclass(frozen=True)
class BrowserConfig:
    profile_dir: str = "data/browser_profile"
    headed_fallback: bool = True


@dataclass(frozen=True)
class SecretsConfig:
    scholar_inbox_email: str = ""
    scholar_inbox_password: str = ""
    semantic_scholar_api_key: str = ""


@dataclass(frozen=True)
class AppConfig:
    ingestion: IngestionConfig = field(default_factory=IngestionConfig)
    citations: CitationConfig = field(default_factory=CitationConfig)
    pruning: PruningConfig = field(default_factory=PruningConfig)
    promotion: PromotionConfig = field(default_factory=PromotionConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    secrets: SecretsConfig = field(default_factory=SecretsConfig)
    db_path: str = "data/scholar_curate.db"


def _validate_config(config: AppConfig) -> None:
    """Validate configuration values. Raises ConfigError on invalid values."""
    if not (0.0 <= config.ingestion.score_threshold <= 1.0):
        raise ConfigError(
            f"score_threshold must be between 0.0 and 1.0 (decimal scale), "
            f"got {config.ingestion.score_threshold}"
        )

    if config.pruning.min_age_months <= 0:
        raise ConfigError(
            f"min_age_months must be > 0, got {config.pruning.min_age_months}"
        )

    if config.pruning.min_citations < 0:
        raise ConfigError(
            f"min_citations must be >= 0, got {config.pruning.min_citations}"
        )

    if not (0.0 <= config.ingestion.backfill_score_threshold <= 1.0):
        raise ConfigError(
            f"backfill_score_threshold must be between 0.0 and 1.0 (decimal scale), "
            f"got {config.ingestion.backfill_score_threshold}"
        )

    if config.ingestion.backfill_lookback_days <= 0:
        raise ConfigError(
            f"backfill_lookback_days must be > 0, "
            f"got {config.ingestion.backfill_lookback_days}"
        )

    if not (1 <= config.citations.semantic_scholar_batch_size <= 500):
        raise ConfigError(
            f"semantic_scholar_batch_size must be between 1 and 500, "
            f"got {config.citations.semantic_scholar_batch_size}"
        )

    if not config.secrets.scholar_inbox_email:
        logger.warning(
            "SCHOLAR_INBOX_EMAIL not set — ingestion commands will fail"
        )
    if not config.secrets.scholar_inbox_password:
        logger.warning(
            "SCHOLAR_INBOX_PASSWORD not set — ingestion commands will fail"
        )


def load_config(
    config_path: str = "config.toml", env_path: str = ".env"
) -> AppConfig:
    """Load configuration from TOML file and environment variables.

    Priority: environment variables > .env file > config.toml > defaults.
    """
    load_dotenv(env_path)

    toml_data: dict = {}
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file, "rb") as f:
            toml_data = tomllib.load(f)

    ingestion = IngestionConfig(**toml_data.get("ingestion", {}))
    citations = CitationConfig(**toml_data.get("citations", {}))
    pruning = PruningConfig(**toml_data.get("pruning", {}))
    promotion = PromotionConfig(**toml_data.get("promotion", {}))
    browser = BrowserConfig(**toml_data.get("browser", {}))

    secrets = SecretsConfig(
        scholar_inbox_email=os.getenv("SCHOLAR_INBOX_EMAIL", ""),
        scholar_inbox_password=os.getenv("SCHOLAR_INBOX_PASSWORD", ""),
        semantic_scholar_api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY", ""),
    )

    db_path = toml_data.get("database", {}).get("path", "data/scholar_curate.db")

    config = AppConfig(
        ingestion=ingestion,
        citations=citations,
        pruning=pruning,
        promotion=promotion,
        browser=browser,
        secrets=secrets,
        db_path=db_path,
    )

    _validate_config(config)

    return config
