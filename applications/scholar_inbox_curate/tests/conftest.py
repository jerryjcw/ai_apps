import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.config import AppConfig, load_config
from src.db import init_db_on_conn


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory for test data."""
    return tmp_path


@pytest.fixture
def sample_config_toml(tmp_path):
    """Create a minimal config.toml in a temp directory and return its path."""
    config_content = """\
[database]
path = "{db_path}"

[ingestion]
score_threshold = 0.60
schedule_cron = "0 8 * * 1"
backfill_score_threshold = 0.60
backfill_lookback_days = 30

[citations]
semantic_scholar_batch_size = 100
poll_schedule_cron = "0 6 * * 3"

[pruning]
min_age_months = 6
min_citations = 10
min_velocity = 1.0

[promotion]
citation_threshold = 50
velocity_threshold = 10.0

[browser]
profile_dir = "{profile_dir}"
headed_fallback = true
""".format(
        db_path=str(tmp_path / "test.db"),
        profile_dir=str(tmp_path / "browser_profile"),
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(config_content)
    return str(config_path)


@pytest.fixture
def sample_env_file(tmp_path):
    """Create a .env file in a temp directory and return its path."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        "SCHOLAR_INBOX_EMAIL=test@example.com\n"
        "SCHOLAR_INBOX_PASSWORD=testpass\n"
        "SEMANTIC_SCHOLAR_API_KEY=test-key-123\n"
    )
    return str(env_path)


@pytest.fixture
def app_config(sample_config_toml, sample_env_file):
    """Load a fully populated AppConfig from test fixtures."""
    return load_config(config_path=sample_config_toml, env_path=sample_env_file)


@pytest.fixture
def db_conn():
    """Provide a fresh in-memory database connection for each test."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_db_on_conn(conn)
    yield conn
    conn.close()
