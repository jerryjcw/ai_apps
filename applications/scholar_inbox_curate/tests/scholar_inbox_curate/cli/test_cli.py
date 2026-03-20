"""Tests for src.cli — wired CLI commands."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from src.cli import cli
from src.db import init_db


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cli_config(tmp_path, monkeypatch):
    """Create minimal config.toml + .env and return (config_path, env_path, db_path).

    Uses monkeypatch to set env vars so they are automatically cleaned up
    after the test, preventing pollution of other tests.
    """
    db_path = str(tmp_path / "test.db")
    profile_dir = str(tmp_path / "browser_profile")
    config_content = f"""\
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
"""
    config_path = tmp_path / "config.toml"
    config_path.write_text(config_content)

    # Set env vars via monkeypatch (auto-reverted after test)
    monkeypatch.setenv("SCHOLAR_INBOX_EMAIL", "test@example.com")
    monkeypatch.setenv("SCHOLAR_INBOX_PASSWORD", "testpass")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-key")

    # Initialize DB so tests that access it directly will work
    init_db(db_path)

    return str(config_path), db_path, profile_dir


def _invoke(runner, cli_config, args):
    """Invoke CLI with config pointing to temp dir."""
    config_path, _, _ = cli_config
    return runner.invoke(cli, ["--config", config_path] + args)


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats_empty_db(self, runner, cli_config):
        result = _invoke(runner, cli_config, ["stats"])
        assert result.exit_code == 0
        assert "Total papers: 0" in result.output
        assert "active: 0" in result.output

    def test_stats_with_papers(self, runner, cli_config):
        from src.db import get_connection, upsert_paper, now_utc

        _, db_path, _ = cli_config
        with get_connection(db_path) as conn:
            upsert_paper(conn, {
                "id": "p1", "title": "Paper 1", "authors": [],
                "ingested_at": now_utc(),
            })
            upsert_paper(conn, {
                "id": "p2", "title": "Paper 2", "authors": [],
                "ingested_at": now_utc(), "status": "promoted",
            })

        result = _invoke(runner, cli_config, ["stats"])
        assert result.exit_code == 0
        assert "Total papers: 2" in result.output


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------

class TestIngest:
    def test_successful_ingest(self, runner, cli_config):
        mock_result = {"papers_found": 5, "papers_ingested": 3, "run_id": 1}
        with patch(
            "src.ingestion.orchestrate.run_ingest",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = _invoke(runner, cli_config, ["ingest"])
        assert result.exit_code == 0
        assert "5 found" in result.output
        assert "3 new" in result.output


# ---------------------------------------------------------------------------
# poll-citations
# ---------------------------------------------------------------------------

class TestPollCitations:
    def test_successful_poll(self, runner, cli_config):
        with patch(
            "src.citations.poller.run_citation_poll",
            new_callable=AsyncMock,
            return_value=10,
        ):
            result = _invoke(runner, cli_config, ["poll-citations"])
        assert result.exit_code == 0
        assert "10 papers processed" in result.output


# ---------------------------------------------------------------------------
# prune
# ---------------------------------------------------------------------------

class TestPrune:
    def test_prune_empty_db(self, runner, cli_config):
        result = _invoke(runner, cli_config, ["prune"])
        assert result.exit_code == 0
        assert "Pruned 0" in result.output
        assert "promoted 0" in result.output

    def test_prune_dry_run(self, runner, cli_config):
        from src.db import get_connection, upsert_paper

        _, db_path, _ = cli_config
        with get_connection(db_path) as conn:
            upsert_paper(conn, {
                "id": "old",
                "title": "Old Paper",
                "authors": [],
                "ingested_at": "2024-01-01T00:00:00+00:00",
                "citation_count": 1,
                "citation_velocity": 0.1,
            })

        result = _invoke(runner, cli_config, ["prune", "--dry-run"])
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.output
        assert "prune 1" in result.output

        # Verify paper was NOT actually pruned
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT status FROM papers WHERE id = 'old'"
            ).fetchone()
            assert row["status"] == "active"

    def test_prune_actually_prunes(self, runner, cli_config):
        from src.db import get_connection, upsert_paper

        _, db_path, _ = cli_config
        with get_connection(db_path) as conn:
            upsert_paper(conn, {
                "id": "old",
                "title": "Old Paper",
                "authors": [],
                "ingested_at": "2024-01-01T00:00:00+00:00",
                "citation_count": 1,
                "citation_velocity": 0.1,
            })

        result = _invoke(runner, cli_config, ["prune"])
        assert result.exit_code == 0
        assert "Pruned 1" in result.output

        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT status FROM papers WHERE id = 'old'"
            ).fetchone()
            assert row["status"] == "pruned"


# ---------------------------------------------------------------------------
# backfill
# ---------------------------------------------------------------------------

class TestBackfill:
    def test_backfill_no_missing(self, runner, cli_config):
        from src.ingestion.backfill import BackfillResult

        mock_result = BackfillResult(dates_checked=0, dates_scraped=0)
        with patch(
            "src.ingestion.backfill.run_backfill",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = _invoke(runner, cli_config, ["backfill"])
        assert result.exit_code == 0
        assert "Dates checked:" in result.output
        assert "Papers re-resolved:" in result.output


# ---------------------------------------------------------------------------
# reset-session
# ---------------------------------------------------------------------------

class TestLogin:
    def test_successful_login(self, runner, cli_config):
        with patch(
            "src.ingestion.scraper.manual_login",
            new_callable=AsyncMock,
            return_value=[{"name": "session", "value": "abc", "domain": ""}],
        ):
            result = _invoke(runner, cli_config, ["login"])
        assert result.exit_code == 0
        assert "Login successful" in result.output


class TestResetSession:
    def test_reset_deletes_cookies_and_profile(self, runner, cli_config):
        _, db_path, profile_dir = cli_config
        data_dir = Path(db_path).parent

        # Create cookies file and browser profile with contents
        cookies_file = data_dir / "cookies.json"
        cookies_file.write_text('[{"name": "session", "value": "old"}]')
        Path(profile_dir).mkdir(exist_ok=True)
        (Path(profile_dir) / "state.txt").write_text("data")

        result = _invoke(runner, cli_config, ["reset-session", "--yes"])
        assert result.exit_code == 0
        assert "Cookies deleted" in result.output
        assert "Browser profile deleted" in result.output
        assert "Browser session cleared" in result.output
        assert not cookies_file.exists()
        assert not Path(profile_dir).exists()

    def test_reset_no_cookies_no_profile(self, runner, cli_config):
        _, _, profile_dir = cli_config
        # Remove the profile dir created by ensure_data_dir
        if Path(profile_dir).exists():
            shutil.rmtree(profile_dir)

        result = _invoke(runner, cli_config, ["reset-session", "--yes"])
        assert result.exit_code == 0
        assert "Browser session cleared" in result.output
