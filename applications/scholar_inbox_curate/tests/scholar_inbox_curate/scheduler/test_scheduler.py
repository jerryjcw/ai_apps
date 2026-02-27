"""Tests for src.scheduler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest
from apscheduler.triggers.cron import CronTrigger

from src.scheduler import _parse_cron, _job_ingest, _job_poll_citations, start_scheduler


# ---------------------------------------------------------------------------
# _parse_cron
# ---------------------------------------------------------------------------

class TestParseCron:
    def test_valid_5_field_expression(self):
        trigger = _parse_cron("0 8 * * 1")
        assert isinstance(trigger, CronTrigger)

    def test_every_day_at_midnight(self):
        trigger = _parse_cron("0 0 * * *")
        assert isinstance(trigger, CronTrigger)

    def test_complex_expression(self):
        trigger = _parse_cron("30 6 1,15 * *")
        assert isinstance(trigger, CronTrigger)

    def test_too_few_fields_raises(self):
        with pytest.raises(ValueError, match="Invalid cron expression"):
            _parse_cron("0 8 *")

    def test_too_many_fields_raises(self):
        with pytest.raises(ValueError, match="Invalid cron expression"):
            _parse_cron("0 8 * * 1 2024")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Invalid cron expression"):
            _parse_cron("")


# ---------------------------------------------------------------------------
# _job_ingest
# ---------------------------------------------------------------------------

class TestJobIngest:
    def test_calls_run_ingest(self):
        config = MagicMock()
        with patch("src.scheduler.asyncio.run") as mock_run:
            _job_ingest(config)
            mock_run.assert_called_once()

    def test_logs_error_on_failure(self):
        config = MagicMock()
        with (
            patch("src.scheduler.asyncio.run", side_effect=RuntimeError("fail")),
            patch("src.scheduler.logger") as mock_logger,
        ):
            _job_ingest(config)  # Should not raise
            mock_logger.error.assert_called()


# ---------------------------------------------------------------------------
# _job_poll_citations
# ---------------------------------------------------------------------------

class TestJobPollCitations:
    def test_calls_poll_and_rules(self):
        config = MagicMock()
        config.db_path = ":memory:"
        mock_result = MagicMock()
        mock_result.papers_pruned = 0
        mock_result.papers_promoted = 0

        with (
            patch("src.scheduler.asyncio.run") as mock_run,
            patch("src.scheduler.get_connection") as mock_conn,
            patch("src.scheduler.run_prune_promote", return_value=mock_result),
        ):
            _job_poll_citations(config)
            mock_run.assert_called_once()

    def test_logs_error_on_failure(self):
        config = MagicMock()
        config.db_path = ":memory:"

        with (
            patch("src.scheduler.asyncio.run", side_effect=RuntimeError("fail")),
            patch("src.scheduler.logger") as mock_logger,
        ):
            _job_poll_citations(config)  # Should not raise
            mock_logger.error.assert_called()


# ---------------------------------------------------------------------------
# start_scheduler
# ---------------------------------------------------------------------------

class TestStartScheduler:
    def test_adds_two_jobs_and_starts(self):
        config = MagicMock()
        config.ingestion.schedule_cron = "0 8 * * 1"
        config.citations.poll_schedule_cron = "0 6 * * 3"

        with patch("src.scheduler.BlockingScheduler") as MockScheduler:
            mock_scheduler = MockScheduler.return_value
            mock_scheduler.start.side_effect = KeyboardInterrupt

            start_scheduler(config)

            assert mock_scheduler.add_job.call_count == 2
            job_ids = [c.kwargs["id"] for c in mock_scheduler.add_job.call_args_list]
            assert "ingest" in job_ids
            assert "poll_citations" in job_ids
            mock_scheduler.start.assert_called_once()
            mock_scheduler.shutdown.assert_called_once()

    def test_invalid_cron_raises(self):
        config = MagicMock()
        config.ingestion.schedule_cron = "bad"
        config.citations.poll_schedule_cron = "0 6 * * 3"

        with pytest.raises(ValueError, match="Invalid cron expression"):
            start_scheduler(config)
