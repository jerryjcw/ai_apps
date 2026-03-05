"""Tests for src.ingestion.scraper — all external I/O is mocked."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.ingestion.scraper import (
    APIError,
    CloudflareTimeoutError,
    LoginError,
    RawPaper,
    ScraperError,
    SessionExpiredError,
    _epoch_ms_to_iso,
    _extract_session_cookie,
    _extract_year,
    _fetch_papers,
    _parse_papers,
    ensure_session,
    extract_chrome_session,
    load_session_cookie,
    save_cookies,
    scrape_date,
    scrape_recommendations,
    verify_session,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api_paper(**overrides) -> dict:
    """Return a realistic Scholar Inbox API paper entry."""
    paper = {
        "title": "Test Paper",
        "authors": "Alice A, Bob B, Carol C",
        "abstract": "An abstract.",
        "ranking_score": 0.85,
        "arxiv_id": "2601.12345",
        "semantic_scholar_id": "abc123hash",
        "paper_id": 999,
        "display_venue": "ArXiv 2026 (January 14)",
        "category": "Computer Science",
        "publication_date": "2026-01-14",
    }
    paper.update(overrides)
    return paper


def _make_api_response(papers: list[dict] | None = None) -> dict:
    """Wrap papers in the top-level API response structure."""
    if papers is None:
        papers = [_make_api_paper()]
    return {
        "digest_df": papers,
        "current_digest_date": "02-25-2026",
        "total_papers": len(papers),
    }


# ===================================================================
# TestRawPaper
# ===================================================================


class TestRawPaper:
    def test_construction(self):
        p = RawPaper(
            title="T",
            authors=["A"],
            abstract="Abs",
            score=90.0,
        )
        assert p.title == "T"
        assert p.authors == ["A"]
        assert p.score == 90.0

    def test_defaults(self):
        p = RawPaper(title="T", authors=[], abstract="", score=0.0)
        assert p.arxiv_id is None
        assert p.semantic_scholar_id is None
        assert p.paper_id is None
        assert p.venue is None
        assert p.year is None
        assert p.category is None
        assert p.scholar_inbox_url is None
        assert p.publication_date is None

    def test_full_fields(self):
        p = RawPaper(
            title="Full",
            authors=["X", "Y"],
            abstract="Ab",
            score=75.0,
            arxiv_id="2601.00001",
            semantic_scholar_id="hash",
            paper_id=42,
            venue="NeurIPS 2025",
            year=2025,
            category="AI",
            scholar_inbox_url="https://www.scholar-inbox.com/paper/2601.00001",
            publication_date="2025-12-01",
        )
        assert p.paper_id == 42
        assert p.year == 2025


# ===================================================================
# TestExtractYear
# ===================================================================


class TestExtractYear:
    def test_arxiv_with_date(self):
        assert _extract_year("ArXiv 2026 (January 14)") == 2026

    def test_conference_year(self):
        assert _extract_year("NeurIPS 2025") == 2025

    def test_old_year(self):
        assert _extract_year("ICML 1999") == 1999

    def test_no_year(self):
        assert _extract_year("Unknown Venue") is None

    def test_none_input(self):
        assert _extract_year(None) is None

    def test_empty_string(self):
        assert _extract_year("") is None

    def test_multiple_years_takes_first(self):
        assert _extract_year("ArXiv 2025 resubmitted 2026") == 2025


# ===================================================================
# TestEpochMsToIso
# ===================================================================


class TestEpochMsToIso:
    def test_known_epoch(self):
        # 2026-01-14 00:00:00 UTC = 1768348800 * 1000
        result = _epoch_ms_to_iso(1768348800000)
        assert result == "2026-01-14"

    def test_none(self):
        assert _epoch_ms_to_iso(None) is None

    def test_zero(self):
        assert _epoch_ms_to_iso(0) == "1970-01-01"

    def test_invalid_string(self):
        assert _epoch_ms_to_iso("not-a-number") is None

    def test_integer_string(self):
        result = _epoch_ms_to_iso("1768348800000")
        assert result == "2026-01-14"


# ===================================================================
# TestParsePapers
# ===================================================================


class TestParsePapers:
    def test_basic_parsing(self):
        data = _make_api_response([_make_api_paper(ranking_score=0.85)])
        papers = _parse_papers(data, score_threshold=0.70)
        assert len(papers) == 1
        p = papers[0]
        assert p.title == "Test Paper"
        assert p.authors == ["Alice A", "Bob B", "Carol C"]
        assert p.score == 85.0
        assert p.arxiv_id == "2601.12345"
        assert p.year == 2026

    def test_score_filtering(self):
        data = _make_api_response([
            _make_api_paper(ranking_score=0.90),
            _make_api_paper(ranking_score=0.50),
            _make_api_paper(ranking_score=0.70),
        ])
        papers = _parse_papers(data, score_threshold=0.70)
        assert len(papers) == 2
        scores = {p.score for p in papers}
        assert scores == {90.0, 70.0}

    def test_threshold_boundary(self):
        data = _make_api_response([_make_api_paper(ranking_score=0.70)])
        papers = _parse_papers(data, score_threshold=0.70)
        assert len(papers) == 1

    def test_below_threshold(self):
        data = _make_api_response([_make_api_paper(ranking_score=0.69)])
        papers = _parse_papers(data, score_threshold=0.70)
        assert len(papers) == 0

    def test_empty_digest(self):
        data = {"digest_df": []}
        papers = _parse_papers(data, score_threshold=0.70)
        assert papers == []

    def test_missing_digest_df(self):
        data = {}
        papers = _parse_papers(data, score_threshold=0.70)
        assert papers == []

    def test_author_splitting(self):
        data = _make_api_response([
            _make_api_paper(authors="  Foo ,  Bar  , Baz  ")
        ])
        papers = _parse_papers(data, score_threshold=0)
        assert papers[0].authors == ["Foo", "Bar", "Baz"]

    def test_empty_authors(self):
        data = _make_api_response([_make_api_paper(authors="")])
        papers = _parse_papers(data, score_threshold=0)
        assert papers[0].authors == []

    def test_none_authors(self):
        data = _make_api_response([_make_api_paper(authors=None)])
        papers = _parse_papers(data, score_threshold=0)
        assert papers[0].authors == []

    def test_scholar_inbox_url(self):
        data = _make_api_response([_make_api_paper(arxiv_id="2601.99999")])
        papers = _parse_papers(data, score_threshold=0)
        assert papers[0].scholar_inbox_url == "https://www.scholar-inbox.com/paper/2601.99999"

    def test_no_arxiv_id_no_url(self):
        data = _make_api_response([_make_api_paper(arxiv_id=None)])
        papers = _parse_papers(data, score_threshold=0)
        assert papers[0].scholar_inbox_url is None

    def test_missing_ranking_score_treated_as_zero(self):
        data = _make_api_response([_make_api_paper(ranking_score=None)])
        papers = _parse_papers(data, score_threshold=1)
        assert len(papers) == 0

    def test_publication_date_preserved(self):
        data = _make_api_response([_make_api_paper(publication_date="2026-01-14")])
        papers = _parse_papers(data, score_threshold=0)
        assert papers[0].publication_date == "2026-01-14"

    def test_year_extracted_from_venue(self):
        data = _make_api_response([
            _make_api_paper(display_venue="NeurIPS 2025")
        ])
        papers = _parse_papers(data, score_threshold=0)
        assert papers[0].year == 2025
        assert papers[0].venue == "NeurIPS 2025"

    def test_score_rounding(self):
        data = _make_api_response([_make_api_paper(ranking_score=0.9116259641)])
        papers = _parse_papers(data, score_threshold=0)
        assert papers[0].score == 91.2


# ===================================================================
# TestCookieManagement
# ===================================================================


class TestCookieManagement:
    def test_save_and_load_roundtrip(self, tmp_path):
        cookies = [
            {"name": "session", "value": "abc123", "domain": "api.scholar-inbox.com"},
            {"name": "other", "value": "xyz", "domain": "scholar-inbox.com"},
        ]
        save_cookies(cookies, str(tmp_path))
        loaded = load_session_cookie(str(tmp_path))
        assert loaded == "abc123"

    def test_load_missing_file(self, tmp_path):
        assert load_session_cookie(str(tmp_path)) is None

    def test_load_corrupt_json(self, tmp_path):
        (tmp_path / "cookies.json").write_text("NOT JSON{{{")
        assert load_session_cookie(str(tmp_path)) is None

    def test_load_no_session_cookie(self, tmp_path):
        cookies = [{"name": "other", "value": "val"}]
        save_cookies(cookies, str(tmp_path))
        assert load_session_cookie(str(tmp_path)) is None

    def test_save_creates_parent_dirs(self, tmp_path):
        deep = tmp_path / "a" / "b"
        save_cookies([{"name": "session", "value": "v"}], str(deep))
        assert (deep / "cookies.json").exists()

    def test_extract_session_cookie(self):
        cookies = [
            {"name": "csrf", "value": "tok"},
            {"name": "session", "value": "sess_val"},
        ]
        assert _extract_session_cookie(cookies) == "sess_val"

    def test_extract_session_cookie_missing(self):
        assert _extract_session_cookie([{"name": "other", "value": "x"}]) is None

    def test_extract_session_cookie_empty_list(self):
        assert _extract_session_cookie([]) is None


# ===================================================================
# TestVerifySession
# ===================================================================


class TestVerifySession:
    @pytest.mark.asyncio
    async def test_valid_session(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"is_logged_in": True}
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = mock_response

        assert await verify_session(client, "good_cookie") is True
        client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_expired_session(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"is_logged_in": False}
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = mock_response

        assert await verify_session(client, "bad_cookie") is False

    @pytest.mark.asyncio
    async def test_http_error(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = httpx.ConnectError("connection refused")

        assert await verify_session(client, "any") is False

    @pytest.mark.asyncio
    async def test_missing_is_logged_in_key(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = mock_response

        assert await verify_session(client, "cookie") is False


# ===================================================================
# TestFetchPapers
# ===================================================================


class TestFetchPapers:
    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        expected = _make_api_response()
        mock_response = MagicMock()
        mock_response.json.return_value = expected
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = mock_response

        result = await _fetch_papers(client, {})
        assert result == expected

    @pytest.mark.asyncio
    async def test_params_passed_through(self):
        mock_response = MagicMock()
        mock_response.json.return_value = _make_api_response()
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = mock_response

        await _fetch_papers(client, {"date": "02-25-2026"})
        _, kwargs = client.get.call_args
        assert kwargs["params"] == {"date": "02-25-2026"}

    @pytest.mark.asyncio
    async def test_http_status_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=mock_response,
        )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = mock_response

        with pytest.raises(APIError, match="HTTP 500"):
            await _fetch_papers(client, {})

    @pytest.mark.asyncio
    async def test_connection_error(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = httpx.ConnectError("refused")

        with pytest.raises(APIError, match="request failed"):
            await _fetch_papers(client, {})

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.side_effect = ValueError("bad json")

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = mock_response

        with pytest.raises(APIError, match="invalid JSON"):
            await _fetch_papers(client, {})


# ===================================================================
# TestScrapeRecommendations
# ===================================================================


class TestScrapeRecommendations:
    def _make_config(self, tmp_path, threshold=0.70):
        """Create a minimal mock config."""
        config = MagicMock()
        config.db_path = str(tmp_path / "data" / "test.db")
        config.ingestion.score_threshold = threshold
        config.secrets.scholar_inbox_email = "test@test.com"
        config.secrets.scholar_inbox_password = "pass"
        return config

    @pytest.mark.asyncio
    @patch("src.ingestion.scraper.ensure_session", new_callable=AsyncMock)
    @patch("src.ingestion.scraper._fetch_papers", new_callable=AsyncMock)
    async def test_basic_flow(self, mock_fetch, mock_session, tmp_path):
        mock_session.return_value = "session_cookie"
        mock_fetch.return_value = _make_api_response([
            _make_api_paper(ranking_score=0.90, title="Good Paper"),
            _make_api_paper(ranking_score=0.50, title="Low Paper"),
        ])

        config = self._make_config(tmp_path)
        papers = await scrape_recommendations(config)

        assert len(papers) == 1
        assert papers[0].title == "Good Paper"
        mock_session.assert_awaited_once_with(config)

    @pytest.mark.asyncio
    @patch("src.ingestion.scraper.ensure_session", new_callable=AsyncMock)
    @patch("src.ingestion.scraper._fetch_papers", new_callable=AsyncMock)
    async def test_date_param(self, mock_fetch, mock_session, tmp_path):
        mock_session.return_value = "cookie"
        mock_fetch.return_value = _make_api_response()

        config = self._make_config(tmp_path)
        await scrape_recommendations(config, date="02-25-2026")

        call_args = mock_fetch.call_args
        # Second positional arg is params dict
        params = call_args[0][1]
        assert params == {"date": "02-25-2026"}

    @pytest.mark.asyncio
    @patch("src.ingestion.scraper.ensure_session", new_callable=AsyncMock)
    @patch("src.ingestion.scraper._fetch_papers", new_callable=AsyncMock)
    async def test_date_range_params(self, mock_fetch, mock_session, tmp_path):
        mock_session.return_value = "cookie"
        mock_fetch.return_value = _make_api_response()

        config = self._make_config(tmp_path)
        await scrape_recommendations(
            config, from_date="02-20-2026", to_date="02-25-2026"
        )

        params = mock_fetch.call_args[0][1]
        assert params == {"from": "02-20-2026", "to": "02-25-2026"}

    @pytest.mark.asyncio
    @patch("src.ingestion.scraper.ensure_session", new_callable=AsyncMock)
    @patch("src.ingestion.scraper._fetch_papers", new_callable=AsyncMock)
    async def test_no_params(self, mock_fetch, mock_session, tmp_path):
        mock_session.return_value = "cookie"
        mock_fetch.return_value = _make_api_response()

        config = self._make_config(tmp_path)
        await scrape_recommendations(config)

        params = mock_fetch.call_args[0][1]
        assert params == {}

    @pytest.mark.asyncio
    @patch("src.ingestion.scraper.ensure_session", new_callable=AsyncMock)
    @patch("src.ingestion.scraper._fetch_papers", new_callable=AsyncMock)
    async def test_date_takes_precedence_over_range(self, mock_fetch, mock_session, tmp_path):
        mock_session.return_value = "cookie"
        mock_fetch.return_value = _make_api_response()

        config = self._make_config(tmp_path)
        await scrape_recommendations(
            config, date="02-25-2026", from_date="02-20-2026", to_date="02-25-2026"
        )

        params = mock_fetch.call_args[0][1]
        assert params == {"date": "02-25-2026"}

    @pytest.mark.asyncio
    @patch("src.ingestion.scraper.ensure_session", new_callable=AsyncMock)
    @patch("src.ingestion.scraper._fetch_papers", new_callable=AsyncMock)
    async def test_custom_threshold(self, mock_fetch, mock_session, tmp_path):
        mock_session.return_value = "cookie"
        mock_fetch.return_value = _make_api_response([
            _make_api_paper(ranking_score=0.95),
            _make_api_paper(ranking_score=0.85),
            _make_api_paper(ranking_score=0.75),
        ])

        config = self._make_config(tmp_path, threshold=0.90)
        papers = await scrape_recommendations(config)

        assert len(papers) == 1
        assert papers[0].score == 95.0


# ===================================================================
# TestScrapeDate
# ===================================================================


class TestScrapeDate:
    def _make_config(self, tmp_path, threshold=0.60):
        config = MagicMock()
        config.db_path = str(tmp_path / "data" / "test.db")
        config.ingestion.score_threshold = threshold
        config.secrets.scholar_inbox_email = "test@test.com"
        config.secrets.scholar_inbox_password = "pass"
        return config

    @pytest.mark.asyncio
    @patch("src.ingestion.scraper.ensure_session", new_callable=AsyncMock)
    @patch("src.ingestion.scraper._fetch_papers", new_callable=AsyncMock)
    async def test_basic_scrape_date(self, mock_fetch, mock_session, tmp_path):
        mock_session.return_value = "session_cookie"
        mock_fetch.return_value = _make_api_response([
            _make_api_paper(ranking_score=0.90, title="Good Paper"),
            _make_api_paper(ranking_score=0.50, title="Low Paper"),
        ])

        config = self._make_config(tmp_path)
        papers = await scrape_date(config, "02-25-2026", score_threshold=0.70)

        assert len(papers) == 1
        assert papers[0].title == "Good Paper"

    @pytest.mark.asyncio
    @patch("src.ingestion.scraper.ensure_session", new_callable=AsyncMock)
    @patch("src.ingestion.scraper._fetch_papers", new_callable=AsyncMock)
    async def test_scrape_date_passes_date_param(self, mock_fetch, mock_session, tmp_path):
        mock_session.return_value = "cookie"
        mock_fetch.return_value = _make_api_response()

        config = self._make_config(tmp_path)
        await scrape_date(config, "02-25-2026")

        params = mock_fetch.call_args[0][1]
        assert params == {"date": "02-25-2026"}

    @pytest.mark.asyncio
    @patch("src.ingestion.scraper.ensure_session", new_callable=AsyncMock)
    @patch("src.ingestion.scraper._fetch_papers", new_callable=AsyncMock)
    async def test_scrape_date_uses_config_threshold_by_default(
        self, mock_fetch, mock_session, tmp_path
    ):
        mock_session.return_value = "cookie"
        mock_fetch.return_value = _make_api_response([
            _make_api_paper(ranking_score=0.65),
            _make_api_paper(ranking_score=0.60),
        ])

        config = self._make_config(tmp_path, threshold=0.60)
        papers = await scrape_date(config, "02-25-2026")

        # Both papers should pass since threshold is 0.60
        assert len(papers) == 2

    @pytest.mark.asyncio
    @patch("src.ingestion.scraper.ensure_session", new_callable=AsyncMock)
    @patch("src.ingestion.scraper._fetch_papers", new_callable=AsyncMock)
    async def test_scrape_date_explicit_threshold_overrides(
        self, mock_fetch, mock_session, tmp_path
    ):
        mock_session.return_value = "cookie"
        mock_fetch.return_value = _make_api_response([
            _make_api_paper(ranking_score=0.95),
            _make_api_paper(ranking_score=0.85),
            _make_api_paper(ranking_score=0.75),
        ])

        config = self._make_config(tmp_path, threshold=0.60)
        papers = await scrape_date(config, "02-25-2026", score_threshold=0.90)

        assert len(papers) == 1
        assert papers[0].score == 95.0


# ===================================================================
# TestExceptionHierarchy
# ===================================================================


class TestExceptionHierarchy:
    def test_base_exception(self):
        assert issubclass(ScraperError, Exception)

    def test_cloudflare_timeout(self):
        assert issubclass(CloudflareTimeoutError, ScraperError)

    def test_login_error(self):
        assert issubclass(LoginError, ScraperError)

    def test_session_expired(self):
        assert issubclass(SessionExpiredError, ScraperError)

    def test_api_error(self):
        assert issubclass(APIError, ScraperError)


# ===================================================================
# TestExtractChromeSession
# ===================================================================


class TestExtractChromeSession:
    def _make_config(self, tmp_path):
        config = MagicMock()
        config.db_path = str(tmp_path / "data" / "test.db")
        return config

    def _mock_bc3(self, cookies):
        """Create a mock browser_cookie3 module with given cookies."""
        mock_module = MagicMock()
        mock_module.chrome.return_value = cookies
        return mock_module

    @pytest.mark.asyncio
    @patch("src.ingestion.scraper.verify_session", new_callable=AsyncMock)
    async def test_success(self, mock_verify, tmp_path):
        """Extract valid cookie from Chrome, verify, and save."""
        cookie = MagicMock()
        cookie.name = "session"
        cookie.value = "chrome_sess_123"
        mock_bc3 = self._mock_bc3([cookie])
        mock_verify.return_value = True

        config = self._make_config(tmp_path)
        with patch.dict("sys.modules", {"browser_cookie3": mock_bc3}):
            result = await extract_chrome_session(config)

        assert result == "chrome_sess_123"
        mock_bc3.chrome.assert_called_once_with(domain_name="api.scholar-inbox.com")
        # Cookie should be saved to disk
        cookies_path = tmp_path / "data" / "cookies.json"
        assert cookies_path.exists()
        saved = json.loads(cookies_path.read_text())
        assert saved[0]["name"] == "session"
        assert saved[0]["value"] == "chrome_sess_123"

    @pytest.mark.asyncio
    async def test_no_session_cookie_in_chrome(self, tmp_path):
        """Raise LoginError when Chrome has no session cookie."""
        other_cookie = MagicMock()
        other_cookie.name = "csrf_token"
        other_cookie.value = "xyz"
        mock_bc3 = self._mock_bc3([other_cookie])

        config = self._make_config(tmp_path)
        with patch.dict("sys.modules", {"browser_cookie3": mock_bc3}):
            with pytest.raises(LoginError, match="No 'session' cookie found"):
                await extract_chrome_session(config)

    @pytest.mark.asyncio
    async def test_empty_cookie_jar(self, tmp_path):
        """Raise LoginError when Chrome cookie jar is empty."""
        mock_bc3 = self._mock_bc3([])

        config = self._make_config(tmp_path)
        with patch.dict("sys.modules", {"browser_cookie3": mock_bc3}):
            with pytest.raises(LoginError, match="No 'session' cookie found"):
                await extract_chrome_session(config)

    @pytest.mark.asyncio
    @patch("src.ingestion.scraper.verify_session", new_callable=AsyncMock)
    async def test_expired_cookie(self, mock_verify, tmp_path):
        """Raise LoginError when Chrome cookie exists but is expired."""
        cookie = MagicMock()
        cookie.name = "session"
        cookie.value = "expired_sess"
        mock_bc3 = self._mock_bc3([cookie])
        mock_verify.return_value = False

        config = self._make_config(tmp_path)
        with patch.dict("sys.modules", {"browser_cookie3": mock_bc3}):
            with pytest.raises(LoginError, match="expired"):
                await extract_chrome_session(config)

    @pytest.mark.asyncio
    async def test_chrome_read_failure(self, tmp_path):
        """Raise LoginError when browser_cookie3 cannot read Chrome cookies."""
        mock_bc3 = MagicMock()
        mock_bc3.chrome.side_effect = PermissionError("Chrome is locked")

        config = self._make_config(tmp_path)
        with patch.dict("sys.modules", {"browser_cookie3": mock_bc3}):
            with pytest.raises(LoginError, match="Failed to read Chrome cookies"):
                await extract_chrome_session(config)

    @pytest.mark.asyncio
    async def test_browser_cookie3_not_installed(self, tmp_path):
        """Raise LoginError when browser_cookie3 is not importable."""
        config = self._make_config(tmp_path)
        with patch.dict("sys.modules", {"browser_cookie3": None}):
            with pytest.raises(LoginError, match="browser_cookie3 is not installed"):
                await extract_chrome_session(config)


# ===================================================================
# TestEnsureSession
# ===================================================================


class TestEnsureSession:
    def _make_config(self, tmp_path):
        config = MagicMock()
        config.db_path = str(tmp_path / "data" / "test.db")
        config.secrets.scholar_inbox_email = "test@test.com"
        config.secrets.scholar_inbox_password = "pass"
        return config

    @pytest.mark.asyncio
    @patch("src.ingestion.scraper.load_session_cookie")
    @patch("src.ingestion.scraper.verify_session", new_callable=AsyncMock)
    async def test_uses_saved_cookie_when_valid(self, mock_verify, mock_load, tmp_path):
        mock_load.return_value = "saved_cookie"
        mock_verify.return_value = True

        config = self._make_config(tmp_path)
        result = await ensure_session(config)

        assert result == "saved_cookie"

    @pytest.mark.asyncio
    @patch("src.ingestion.scraper.manual_login", new_callable=AsyncMock)
    @patch("src.ingestion.scraper.extract_chrome_session", new_callable=AsyncMock)
    @patch("src.ingestion.scraper.verify_session", new_callable=AsyncMock)
    @patch("src.ingestion.scraper.load_session_cookie")
    async def test_tries_chrome_when_saved_expired(
        self, mock_load, mock_verify, mock_chrome, mock_login, tmp_path
    ):
        mock_load.return_value = "old_cookie"
        mock_verify.return_value = False
        mock_chrome.return_value = "chrome_cookie"

        config = self._make_config(tmp_path)
        result = await ensure_session(config)

        assert result == "chrome_cookie"
        mock_chrome.assert_awaited_once()
        mock_login.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("src.ingestion.scraper.manual_login", new_callable=AsyncMock)
    @patch("src.ingestion.scraper.extract_chrome_session", new_callable=AsyncMock)
    @patch("src.ingestion.scraper.load_session_cookie")
    async def test_falls_back_to_playwright_when_chrome_fails(
        self, mock_load, mock_chrome, mock_login, tmp_path
    ):
        mock_load.return_value = None
        mock_chrome.side_effect = LoginError("no cookie in Chrome")
        mock_login.return_value = [
            {"name": "session", "value": "pw_cookie", "domain": "api.scholar-inbox.com"}
        ]

        config = self._make_config(tmp_path)
        result = await ensure_session(config)

        assert result == "pw_cookie"
        mock_chrome.assert_awaited_once()
        mock_login.assert_awaited_once()
