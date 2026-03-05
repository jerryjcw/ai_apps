import os
from pathlib import Path

import pytest

from src.config import (
    AppConfig,
    BrowserConfig,
    CitationConfig,
    ConfigError,
    IngestionConfig,
    PromotionConfig,
    PruningConfig,
    SecretsConfig,
    load_config,
)


class TestDefaultConfig:
    """Test that default dataclass values are correct."""

    def test_ingestion_defaults(self):
        cfg = IngestionConfig()
        assert cfg.score_threshold == 0.60
        assert cfg.schedule_cron == "0 8 * * 1"
        assert cfg.backfill_score_threshold == 0.60
        assert cfg.backfill_lookback_days == 30

    def test_citation_defaults(self):
        cfg = CitationConfig()
        assert cfg.semantic_scholar_batch_size == 100
        assert cfg.poll_schedule_cron == "0 6 * * 3"

    def test_pruning_defaults(self):
        cfg = PruningConfig()
        assert cfg.min_age_months == 6
        assert cfg.min_citations == 10
        assert cfg.min_velocity == 1.0

    def test_promotion_defaults(self):
        cfg = PromotionConfig()
        assert cfg.citation_threshold == 50
        assert cfg.velocity_threshold == 10.0

    def test_browser_defaults(self):
        cfg = BrowserConfig()
        assert cfg.profile_dir == "data/browser_profile"
        assert cfg.headed_fallback is True

    def test_secrets_defaults(self):
        cfg = SecretsConfig()
        assert cfg.scholar_inbox_email == ""
        assert cfg.scholar_inbox_password == ""
        assert cfg.semantic_scholar_api_key == ""

    def test_app_config_defaults(self):
        cfg = AppConfig()
        assert cfg.db_path == "data/scholar_curate.db"
        assert isinstance(cfg.ingestion, IngestionConfig)

    def test_frozen_dataclasses(self):
        cfg = IngestionConfig()
        with pytest.raises(AttributeError):
            cfg.score_threshold = 50  # type: ignore[misc]


class TestLoadConfig:
    """Test loading config from TOML and env files."""

    def test_load_from_toml_and_env(self, app_config):
        assert app_config.ingestion.score_threshold == 0.60  # Decimal scale
        assert app_config.citations.semantic_scholar_batch_size == 100
        assert app_config.pruning.min_age_months == 6
        assert app_config.promotion.citation_threshold == 50
        assert app_config.browser.headed_fallback is True
        assert app_config.secrets.scholar_inbox_email == "test@example.com"
        assert app_config.secrets.scholar_inbox_password == "testpass"
        assert app_config.secrets.semantic_scholar_api_key == "test-key-123"

    def test_load_with_missing_toml(self, tmp_path, sample_env_file):
        """When config.toml doesn't exist, defaults are used."""
        config = load_config(
            config_path=str(tmp_path / "nonexistent.toml"),
            env_path=sample_env_file,
        )
        assert config.ingestion.score_threshold == 0.60
        assert config.db_path == "data/scholar_curate.db"

    def test_load_with_missing_env(self, sample_config_toml, tmp_path):
        """When .env doesn't exist, secrets default to empty strings."""
        # Clear any env vars that might be set from other tests
        for key in (
            "SCHOLAR_INBOX_EMAIL",
            "SCHOLAR_INBOX_PASSWORD",
            "SEMANTIC_SCHOLAR_API_KEY",
        ):
            os.environ.pop(key, None)

        config = load_config(
            config_path=sample_config_toml,
            env_path=str(tmp_path / "nonexistent.env"),
        )
        assert config.secrets.scholar_inbox_email == ""

    def test_custom_toml_values(self, tmp_path, sample_env_file):
        """Custom values in TOML override defaults."""
        config_content = """\
[ingestion]
score_threshold = 0.85

[citations]
semantic_scholar_batch_size = 200

[pruning]
min_age_months = 12
min_citations = 20
min_velocity = 2.5

[promotion]
citation_threshold = 100
velocity_threshold = 20.0
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(config_content)

        config = load_config(
            config_path=str(config_path), env_path=sample_env_file
        )
        assert config.ingestion.score_threshold == 0.85
        assert config.citations.semantic_scholar_batch_size == 200
        assert config.pruning.min_age_months == 12
        assert config.promotion.citation_threshold == 100

    def test_env_vars_override_dotenv(self, sample_config_toml, sample_env_file):
        """OS environment variables take precedence over .env file."""
        os.environ["SCHOLAR_INBOX_EMAIL"] = "override@example.com"
        try:
            config = load_config(
                config_path=sample_config_toml, env_path=sample_env_file
            )
            assert config.secrets.scholar_inbox_email == "override@example.com"
        finally:
            del os.environ["SCHOLAR_INBOX_EMAIL"]

    def test_db_path_from_toml(self, tmp_path, sample_env_file):
        """Database path is loaded from [database] section."""
        config_content = """\
[database]
path = "/custom/path/to/db.sqlite"
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(config_content)

        config = load_config(
            config_path=str(config_path), env_path=sample_env_file
        )
        assert config.db_path == "/custom/path/to/db.sqlite"


class TestConfigValidation:
    """Test validation rules in _validate_config."""

    def test_invalid_score_threshold_too_high(self, tmp_path, sample_env_file):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[ingestion]\nscore_threshold = 1.5\n")
        with pytest.raises(ConfigError, match="score_threshold"):
            load_config(config_path=str(config_path), env_path=sample_env_file)

    def test_invalid_score_threshold_negative(self, tmp_path, sample_env_file):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[ingestion]\nscore_threshold = -1\n")
        with pytest.raises(ConfigError, match="score_threshold"):
            load_config(config_path=str(config_path), env_path=sample_env_file)

    def test_invalid_min_age_months_zero(self, tmp_path, sample_env_file):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[pruning]\nmin_age_months = 0\n")
        with pytest.raises(ConfigError, match="min_age_months"):
            load_config(config_path=str(config_path), env_path=sample_env_file)

    def test_invalid_min_citations_negative(self, tmp_path, sample_env_file):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[pruning]\nmin_citations = -5\n")
        with pytest.raises(ConfigError, match="min_citations"):
            load_config(config_path=str(config_path), env_path=sample_env_file)

    def test_invalid_batch_size_too_large(self, tmp_path, sample_env_file):
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            "[citations]\nsemantic_scholar_batch_size = 501\n"
        )
        with pytest.raises(ConfigError, match="semantic_scholar_batch_size"):
            load_config(config_path=str(config_path), env_path=sample_env_file)

    def test_invalid_batch_size_zero(self, tmp_path, sample_env_file):
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            "[citations]\nsemantic_scholar_batch_size = 0\n"
        )
        with pytest.raises(ConfigError, match="semantic_scholar_batch_size"):
            load_config(config_path=str(config_path), env_path=sample_env_file)

    def test_missing_secrets_warns(self, sample_config_toml, tmp_path, caplog):
        """Missing secrets should produce warnings, not errors."""
        for key in (
            "SCHOLAR_INBOX_EMAIL",
            "SCHOLAR_INBOX_PASSWORD",
            "SEMANTIC_SCHOLAR_API_KEY",
        ):
            os.environ.pop(key, None)

        import logging

        with caplog.at_level(logging.WARNING):
            config = load_config(
                config_path=sample_config_toml,
                env_path=str(tmp_path / "nonexistent.env"),
            )

        assert config.secrets.scholar_inbox_email == ""
        assert "SCHOLAR_INBOX_EMAIL not set" in caplog.text
        assert "SCHOLAR_INBOX_PASSWORD not set" in caplog.text

    def test_invalid_backfill_score_threshold_too_high(self, tmp_path, sample_env_file):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[ingestion]\nbackfill_score_threshold = 1.5\n")
        with pytest.raises(ConfigError, match="backfill_score_threshold"):
            load_config(config_path=str(config_path), env_path=sample_env_file)

    def test_invalid_backfill_score_threshold_negative(self, tmp_path, sample_env_file):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[ingestion]\nbackfill_score_threshold = -1\n")
        with pytest.raises(ConfigError, match="backfill_score_threshold"):
            load_config(config_path=str(config_path), env_path=sample_env_file)

    def test_invalid_backfill_lookback_days_zero(self, tmp_path, sample_env_file):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[ingestion]\nbackfill_lookback_days = 0\n")
        with pytest.raises(ConfigError, match="backfill_lookback_days"):
            load_config(config_path=str(config_path), env_path=sample_env_file)

    def test_invalid_backfill_lookback_days_negative(self, tmp_path, sample_env_file):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[ingestion]\nbackfill_lookback_days = -5\n")
        with pytest.raises(ConfigError, match="backfill_lookback_days"):
            load_config(config_path=str(config_path), env_path=sample_env_file)

    def test_boundary_score_threshold_zero(self, tmp_path, sample_env_file):
        """score_threshold=0.0 is valid."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("[ingestion]\nscore_threshold = 0.0\n")
        config = load_config(
            config_path=str(config_path), env_path=sample_env_file
        )
        assert config.ingestion.score_threshold == 0.0

    def test_boundary_score_threshold_100(self, tmp_path, sample_env_file):
        """score_threshold=1.0 is valid (100% threshold)."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("[ingestion]\nscore_threshold = 1.0\n")
        config = load_config(
            config_path=str(config_path), env_path=sample_env_file
        )
        assert config.ingestion.score_threshold == 1.0
