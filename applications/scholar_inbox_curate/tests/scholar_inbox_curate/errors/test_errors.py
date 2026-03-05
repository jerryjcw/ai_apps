"""Tests for src.errors — exception hierarchy and retry decorator."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.errors import (
    ScholarCurateError,
    ConfigError,
    DatabaseError,
    ScraperError,
    CloudflareTimeoutError,
    LoginError,
    SessionExpiredError,
    APIError,
    ResolverError,
    CitationPollError,
    RulesError,
    retry_async,
)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class TestExceptionHierarchy:
    """All custom exceptions inherit from ScholarCurateError."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            ConfigError,
            DatabaseError,
            ScraperError,
            CloudflareTimeoutError,
            LoginError,
            SessionExpiredError,
            APIError,
            ResolverError,
            CitationPollError,
            RulesError,
        ],
    )
    def test_inherits_from_base(self, exc_class):
        assert issubclass(exc_class, ScholarCurateError)

    def test_scraper_subtypes(self):
        assert issubclass(CloudflareTimeoutError, ScraperError)
        assert issubclass(LoginError, ScraperError)
        assert issubclass(SessionExpiredError, ScraperError)
        assert issubclass(APIError, ScraperError)

    def test_base_inherits_from_exception(self):
        assert issubclass(ScholarCurateError, Exception)

    def test_catch_all_works(self):
        """Can catch any custom error via ScholarCurateError."""
        with pytest.raises(ScholarCurateError):
            raise CloudflareTimeoutError("timeout")

        with pytest.raises(ScholarCurateError):
            raise ConfigError("bad config")

        with pytest.raises(ScholarCurateError):
            raise DatabaseError("corrupt")


# ---------------------------------------------------------------------------
# Backward-compatible imports
# ---------------------------------------------------------------------------

class TestBackwardCompatibleImports:
    def test_config_error_from_config(self):
        from src.config import ConfigError as CE
        assert CE is ConfigError

    def test_scraper_errors_from_scraper(self):
        from src.ingestion.scraper import (
            ScraperError as SE,
            CloudflareTimeoutError as CTE,
            LoginError as LE,
            SessionExpiredError as SEE,
            APIError as AE,
        )
        assert SE is ScraperError
        assert CTE is CloudflareTimeoutError
        assert LE is LoginError
        assert SEE is SessionExpiredError
        assert AE is APIError


# ---------------------------------------------------------------------------
# retry_async
# ---------------------------------------------------------------------------

class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_succeeds_first_try(self):
        call_count = 0

        @retry_async(max_retries=2, delay=0.01)
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self):
        call_count = 0

        @retry_async(max_retries=2, delay=0.01)
        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("not yet")
            return "ok"

        result = await fail_then_succeed()
        assert result == "ok"
        assert call_count == 3  # 1 initial + 2 retries

    @pytest.mark.asyncio
    async def test_exhausts_retries_and_raises(self):
        call_count = 0

        @retry_async(max_retries=2, delay=0.01)
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("permanent")

        with pytest.raises(ValueError, match="permanent"):
            await always_fail()

        assert call_count == 3  # 1 initial + 2 retries

    @pytest.mark.asyncio
    async def test_backoff_multiplier(self):
        """Verify delay increases with backoff factor."""
        delays = []

        @retry_async(max_retries=2, delay=0.1, backoff=2.0)
        async def fail():
            raise RuntimeError("fail")

        with patch("src.errors.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(RuntimeError):
                await fail()

            # Should have slept twice (2 retries)
            assert mock_sleep.call_count == 2
            actual_delays = [c.args[0] for c in mock_sleep.call_args_list]
            assert abs(actual_delays[0] - 0.1) < 0.01
            assert abs(actual_delays[1] - 0.2) < 0.01

    @pytest.mark.asyncio
    async def test_zero_retries(self):
        """max_retries=0 means no retries — fail immediately."""
        call_count = 0

        @retry_async(max_retries=0, delay=0.01)
        async def fail():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            await fail()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_preserves_function_name(self):
        @retry_async(max_retries=1, delay=0.01)
        async def my_function():
            pass

        assert my_function.__name__ == "my_function"

    @pytest.mark.asyncio
    async def test_raises_last_error(self):
        """When retries are exhausted, the last exception is raised."""
        attempt = 0

        @retry_async(max_retries=1, delay=0.01)
        async def changing_error():
            nonlocal attempt
            attempt += 1
            raise ValueError(f"error {attempt}")

        with pytest.raises(ValueError, match="error 2"):
            await changing_error()


# ---------------------------------------------------------------------------
# Recovery hints in orchestrate.py
# ---------------------------------------------------------------------------

class TestRecoveryHints:
    @pytest.mark.asyncio
    async def test_cloudflare_error_logs_hint(self, tmp_path):
        from src.config import AppConfig
        from src.db import init_db
        from src.ingestion.orchestrate import run_ingest

        db_path = str(tmp_path / "test.db")
        config = AppConfig(db_path=db_path)
        init_db(db_path)

        with (
            patch(
                "src.ingestion.orchestrate.scrape_recommendations",
                new_callable=AsyncMock,
                side_effect=CloudflareTimeoutError("timeout"),
            ),
            patch("src.ingestion.orchestrate.logger") as mock_logger,
            pytest.raises(CloudflareTimeoutError),
        ):
            await run_ingest(config)

        mock_logger.error.assert_called_once()
        msg = mock_logger.error.call_args.args[0]
        assert "reset-session" in msg

    @pytest.mark.asyncio
    async def test_login_error_logs_hint(self, tmp_path):
        from src.config import AppConfig
        from src.db import init_db
        from src.ingestion.orchestrate import run_ingest

        db_path = str(tmp_path / "test.db")
        config = AppConfig(db_path=db_path)
        init_db(db_path)

        with (
            patch(
                "src.ingestion.orchestrate.scrape_recommendations",
                new_callable=AsyncMock,
                side_effect=LoginError("bad creds"),
            ),
            patch("src.ingestion.orchestrate.logger") as mock_logger,
            pytest.raises(LoginError),
        ):
            await run_ingest(config)

        mock_logger.error.assert_called_once()
        msg = mock_logger.error.call_args.args[0]
        assert "SCHOLAR_INBOX_EMAIL" in msg

    @pytest.mark.asyncio
    async def test_generic_error_still_records_failure(self, tmp_path):
        from src.config import AppConfig
        from src.db import init_db, get_connection
        from src.ingestion.orchestrate import run_ingest

        db_path = str(tmp_path / "test.db")
        config = AppConfig(db_path=db_path)
        init_db(db_path)

        with (
            patch(
                "src.ingestion.orchestrate.scrape_recommendations",
                new_callable=AsyncMock,
                side_effect=RuntimeError("unexpected"),
            ),
            pytest.raises(RuntimeError),
        ):
            await run_ingest(config)

        with get_connection(db_path) as conn:
            run = conn.execute(
                "SELECT * FROM ingestion_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert run["status"] == "failed"
