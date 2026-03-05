"""Tests for src.ingestion.backfill — all external I/O is mocked."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db import (
    get_scraped_dates,
    init_db_on_conn,
    record_scraped_date,
)
from src.ingestion.backfill import (
    BackfillResult,
    _date_to_api_format,
    _raw_paper_to_db_dict,
    run_backfill,
)
from src.ingestion.scraper import RawPaper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw_paper(**overrides) -> RawPaper:
    defaults = dict(
        title="Test Paper",
        authors=["Alice", "Bob"],
        abstract="An abstract.",
        score=85.0,
        arxiv_id="2601.12345",
        semantic_scholar_id="abc123hash",
        paper_id=999,
        venue="ArXiv 2026",
        year=2026,
        category="CS",
        scholar_inbox_url="https://www.scholar-inbox.com/paper/2601.12345",
        publication_date="2026-01-14",
    )
    defaults.update(overrides)
    return RawPaper(**defaults)


def _make_config(tmp_path, backfill_threshold=0.60, backfill_lookback=30, score_threshold=0.60):
    config = MagicMock()
    config.db_path = str(tmp_path / "test.db")
    config.ingestion.score_threshold = score_threshold
    config.ingestion.backfill_score_threshold = backfill_threshold
    config.ingestion.backfill_lookback_days = backfill_lookback
    return config


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------

class TestDateToApiFormat:
    def test_basic(self):
        assert _date_to_api_format(date(2026, 2, 25)) == "02-25-2026"

    def test_single_digit_month_day(self):
        assert _date_to_api_format(date(2026, 1, 5)) == "01-05-2026"


class TestRawPaperToDbDict:
    def test_uses_semantic_scholar_id(self):
        paper = _make_raw_paper(semantic_scholar_id="ss_id", arxiv_id="ax_id")
        result = _raw_paper_to_db_dict(paper, "2026-02-25")
        assert result["id"] == "ss_id"

    def test_falls_back_to_arxiv_id(self):
        paper = _make_raw_paper(semantic_scholar_id=None, arxiv_id="ax_id")
        result = _raw_paper_to_db_dict(paper, "2026-02-25")
        assert result["id"] == "ax_id"

    def test_falls_back_to_paper_id(self):
        paper = _make_raw_paper(semantic_scholar_id=None, arxiv_id=None, paper_id=42)
        result = _raw_paper_to_db_dict(paper, "2026-02-25")
        assert result["id"] == "si-42"

    def test_contains_expected_fields(self):
        paper = _make_raw_paper()
        result = _raw_paper_to_db_dict(paper, "2026-02-25")
        assert result["title"] == "Test Paper"
        assert result["authors"] == ["Alice", "Bob"]
        assert result["scholar_inbox_score"] == 85.0
        assert result["arxiv_id"] == "2601.12345"


class TestBackfillResult:
    def test_defaults(self):
        r = BackfillResult()
        assert r.dates_checked == 0
        assert r.dates_scraped == 0
        assert r.total_papers_found == 0
        assert r.total_papers_ingested == 0
        assert r.errors == []


# ---------------------------------------------------------------------------
# Integration tests for run_backfill
# ---------------------------------------------------------------------------

class TestRunBackfill:
    @pytest.mark.asyncio
    @patch("src.ingestion.backfill.scrape_date", new_callable=AsyncMock)
    async def test_no_missing_dates(self, mock_scrape, tmp_path, db_conn):
        """When all dates are scraped, nothing happens."""
        config = _make_config(tmp_path, backfill_lookback=3)

        # Pre-populate scraped_dates via the real DB
        # We patch get_connection to return our test db_conn
        with patch("src.ingestion.backfill.get_connection") as mock_gc:
            mock_gc.return_value.__enter__ = MagicMock(return_value=db_conn)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            # Scrape all weekdays in the last 3 days from a known "today"
            with patch("src.db.date") as mock_date_cls:
                mock_date_cls.today.return_value = date(2026, 2, 25)
                mock_date_cls.side_effect = lambda *a, **kw: date(*a, **kw)

                # Record all possible missing dates
                record_scraped_date(db_conn, "2026-02-24")
                record_scraped_date(db_conn, "2026-02-23")
                record_scraped_date(db_conn, "2026-02-20")

                result = await run_backfill(config, lookback_days=5)

        assert result.dates_checked == 0
        mock_scrape.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.ingestion.backfill.scrape_date", new_callable=AsyncMock)
    async def test_backfill_scrapes_missing_dates(self, mock_scrape, tmp_path, db_conn):
        """Should call scrape_date for each missing date."""
        config = _make_config(tmp_path, backfill_lookback=5)
        mock_scrape.return_value = [_make_raw_paper()]

        with patch("src.ingestion.backfill.get_connection") as mock_gc:
            mock_gc.return_value.__enter__ = MagicMock(return_value=db_conn)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.ingestion.backfill.find_missing_dates") as mock_find:
                mock_find.return_value = ["2026-02-24", "2026-02-25"]

                result = await run_backfill(config)

        assert result.dates_checked == 2
        assert result.dates_scraped == 2
        assert mock_scrape.call_count == 2

    @pytest.mark.asyncio
    @patch("src.ingestion.backfill.scrape_date", new_callable=AsyncMock)
    async def test_backfill_records_papers(self, mock_scrape, tmp_path, db_conn):
        """Papers from scrape_date should be upserted into the DB."""
        config = _make_config(tmp_path)
        mock_scrape.return_value = [
            _make_raw_paper(semantic_scholar_id="paper1"),
            _make_raw_paper(semantic_scholar_id="paper2"),
        ]

        with patch("src.ingestion.backfill.get_connection") as mock_gc:
            mock_gc.return_value.__enter__ = MagicMock(return_value=db_conn)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.ingestion.backfill.find_missing_dates") as mock_find:
                mock_find.return_value = ["2026-02-24"]

                result = await run_backfill(config)

        assert result.total_papers_found == 2
        assert result.total_papers_ingested == 2

    @pytest.mark.asyncio
    @patch("src.ingestion.backfill.scrape_date", new_callable=AsyncMock)
    async def test_backfill_records_scraped_date(self, mock_scrape, tmp_path, db_conn):
        """After scraping, the date should be recorded in scraped_dates."""
        config = _make_config(tmp_path)
        mock_scrape.return_value = []

        with patch("src.ingestion.backfill.get_connection") as mock_gc:
            mock_gc.return_value.__enter__ = MagicMock(return_value=db_conn)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.ingestion.backfill.find_missing_dates") as mock_find:
                mock_find.return_value = ["2026-02-24"]

                await run_backfill(config)

        assert "2026-02-24" in get_scraped_dates(db_conn)

    @pytest.mark.asyncio
    @patch("src.ingestion.backfill.scrape_date", new_callable=AsyncMock)
    async def test_backfill_handles_scrape_error(self, mock_scrape, tmp_path, db_conn):
        """Errors on individual dates should be captured, not raised."""
        config = _make_config(tmp_path)
        mock_scrape.side_effect = Exception("API timeout")

        with patch("src.ingestion.backfill.get_connection") as mock_gc:
            mock_gc.return_value.__enter__ = MagicMock(return_value=db_conn)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.ingestion.backfill.find_missing_dates") as mock_find:
                mock_find.return_value = ["2026-02-24"]

                result = await run_backfill(config)

        assert result.dates_scraped == 0
        assert len(result.errors) == 1
        assert "API timeout" in result.errors[0]

    @pytest.mark.asyncio
    @patch("src.ingestion.backfill.scrape_date", new_callable=AsyncMock)
    async def test_backfill_uses_config_defaults(self, mock_scrape, tmp_path, db_conn):
        """When no overrides given, uses config values."""
        config = _make_config(tmp_path, backfill_threshold=0.55, backfill_lookback=10)
        mock_scrape.return_value = []

        with patch("src.ingestion.backfill.get_connection") as mock_gc:
            mock_gc.return_value.__enter__ = MagicMock(return_value=db_conn)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.ingestion.backfill.find_missing_dates") as mock_find:
                mock_find.return_value = ["2026-02-24"]

                await run_backfill(config)

        # scrape_date should be called with the config's backfill threshold
        mock_scrape.assert_called_once()
        call_kwargs = mock_scrape.call_args
        assert call_kwargs[0][2] == 0.55  # score_threshold positional arg

    @pytest.mark.asyncio
    @patch("src.ingestion.backfill.scrape_date", new_callable=AsyncMock)
    async def test_backfill_override_params(self, mock_scrape, tmp_path, db_conn):
        """Explicit params should override config values."""
        config = _make_config(tmp_path, backfill_threshold=0.55, backfill_lookback=10)
        mock_scrape.return_value = []

        with patch("src.ingestion.backfill.get_connection") as mock_gc:
            mock_gc.return_value.__enter__ = MagicMock(return_value=db_conn)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.ingestion.backfill.find_missing_dates") as mock_find:
                mock_find.return_value = ["2026-02-24"]

                await run_backfill(config, lookback_days=5, score_threshold=0.80)

        call_kwargs = mock_scrape.call_args
        assert call_kwargs[0][2] == 0.80  # overridden threshold

    @pytest.mark.asyncio
    @patch("src.ingestion.backfill.scrape_date", new_callable=AsyncMock)
    async def test_backfill_deduplicates_papers(self, mock_scrape, tmp_path, db_conn):
        """If a paper already exists, it should not count as newly ingested."""
        config = _make_config(tmp_path)
        paper = _make_raw_paper(semantic_scholar_id="existing_paper")
        mock_scrape.return_value = [paper]

        with patch("src.ingestion.backfill.get_connection") as mock_gc:
            mock_gc.return_value.__enter__ = MagicMock(return_value=db_conn)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.ingestion.backfill.find_missing_dates") as mock_find:
                # Two dates, same paper
                mock_find.return_value = ["2026-02-24", "2026-02-25"]

                result = await run_backfill(config)

        # First date inserts (new), second date updates (not new)
        assert result.total_papers_found == 2
        assert result.total_papers_ingested == 1  # only first insertion counts
