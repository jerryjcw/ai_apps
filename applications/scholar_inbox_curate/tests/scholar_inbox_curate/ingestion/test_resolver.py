"""Tests for src.ingestion.resolver — Paper ID resolution via Semantic Scholar."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.config import AppConfig, IngestionConfig, SecretsConfig
from src.ingestion.resolver import (
    ResolvedPaper,
    _create_fallback_resolved,
    _create_pre_resolved,
    _find_best_match,
    _generate_fallback_id,
    _normalize_title,
    _parse_s2_response,
    _title_similarity,
    resolve_paper,
    resolve_papers,
)
from src.ingestion.scraper import RawPaper
from src.retry import RetryConfig

# Zero-delay retry for fast tests
_FAST_RETRY = RetryConfig(strategy="fixed", base_delay=0.0)

_DUMMY_REQUEST = httpx.Request("GET", "https://api.semanticscholar.org/test")


def _mock_response(status_code: int, json: dict | None = None, headers: dict | None = None) -> httpx.Response:
    """Create an httpx.Response with a request set (needed for raise_for_status)."""
    kwargs: dict = {"status_code": status_code, "request": _DUMMY_REQUEST}
    if json is not None:
        kwargs["json"] = json
    if headers is not None:
        kwargs["headers"] = headers
    return httpx.Response(**kwargs)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def raw_paper_with_arxiv() -> RawPaper:
    return RawPaper(
        title="Attention Is All You Need",
        authors=["Ashish Vaswani", "Noam Shazeer"],
        abstract="The dominant sequence models...",
        score=95.0,
        arxiv_id="1706.03762",
        scholar_inbox_url="https://www.scholar-inbox.com/paper/1706.03762",
    )


@pytest.fixture
def raw_paper_no_arxiv() -> RawPaper:
    return RawPaper(
        title="Some Novel Method for NLP",
        authors=["Alice Smith"],
        abstract="We propose a novel method...",
        score=80.0,
        venue="ACL 2025",
        year=2025,
    )


@pytest.fixture
def config_with_key() -> AppConfig:
    return AppConfig(
        secrets=SecretsConfig(
            semantic_scholar_api_key="test-key-123",
        ),
    )


@pytest.fixture
def config_no_key() -> AppConfig:
    return AppConfig(
        secrets=SecretsConfig(
            semantic_scholar_api_key="",
        ),
    )


def _s2_paper_response(
    paper_id: str = "abc123",
    title: str = "Attention Is All You Need",
    arxiv_id: str | None = "1706.03762",
    doi: str | None = "10.5555/3295222.3295349",
    citation_count: int = 90000,
) -> dict:
    """Build a mock Semantic Scholar paper response."""
    return {
        "paperId": paper_id,
        "title": title,
        "authors": [
            {"authorId": "1", "name": "Ashish Vaswani"},
            {"authorId": "2", "name": "Noam Shazeer"},
        ],
        "abstract": "The dominant sequence transduction models...",
        "url": "https://www.semanticscholar.org/paper/abc123",
        "venue": "NeurIPS",
        "year": 2017,
        "publicationDate": "2017-06-12",
        "externalIds": {"ArXiv": arxiv_id, "DOI": doi},
        "citationCount": citation_count,
    }


# ---------------------------------------------------------------------------
# Title normalization & similarity
# ---------------------------------------------------------------------------

class TestNormalizeTitle:
    def test_lowercases(self):
        assert _normalize_title("HELLO WORLD") == "hello world"

    def test_removes_punctuation(self):
        assert _normalize_title("Hello, World!") == "hello world"

    def test_collapses_whitespace(self):
        assert _normalize_title("hello   world") == "hello world"

    def test_strips(self):
        assert _normalize_title("  hello  ") == "hello"

    def test_mixed(self):
        assert _normalize_title("  Attention Is All You Need!  ") == "attention is all you need"


class TestTitleSimilarity:
    def test_identical(self):
        assert _title_similarity("Hello World", "Hello World") == 1.0

    def test_case_insensitive(self):
        assert _title_similarity("hello world", "HELLO WORLD") == 1.0

    def test_punctuation_ignored(self):
        assert _title_similarity("Hello, World!", "Hello World") == 1.0

    def test_different_titles(self):
        score = _title_similarity("Attention Is All You Need", "BERT: Pre-training of Deep Bidirectional Transformers")
        assert score < 0.5

    def test_similar_titles(self):
        score = _title_similarity(
            "Attention Is All You Need",
            "Attention is All You Need",
        )
        assert score == 1.0


# ---------------------------------------------------------------------------
# Best match selection
# ---------------------------------------------------------------------------

class TestFindBestMatch:
    def test_returns_best_above_threshold(self):
        results = [
            {"title": "Unrelated Paper About Biology"},
            {"title": "Attention Is All You Need"},
            {"title": "Another Unrelated Paper"},
        ]
        match = _find_best_match("Attention Is All You Need", results)
        assert match is not None
        assert match["title"] == "Attention Is All You Need"

    def test_returns_none_below_threshold(self):
        results = [
            {"title": "Completely Different Paper One"},
            {"title": "Completely Different Paper Two"},
        ]
        match = _find_best_match("Attention Is All You Need", results)
        assert match is None

    def test_empty_results(self):
        assert _find_best_match("Anything", []) is None

    def test_minor_variation_matches(self):
        results = [{"title": "Attention is All You Need."}]
        match = _find_best_match("Attention Is All You Need", results)
        assert match is not None


# ---------------------------------------------------------------------------
# S2 response parsing
# ---------------------------------------------------------------------------

class TestParseS2Response:
    def test_basic_parsing(self, raw_paper_with_arxiv):
        data = _s2_paper_response()
        resolved = _parse_s2_response(data, raw_paper_with_arxiv)

        assert resolved.semantic_scholar_id == "abc123"
        assert resolved.title == "Attention Is All You Need"
        assert resolved.authors == ["Ashish Vaswani", "Noam Shazeer"]
        assert resolved.arxiv_id == "1706.03762"
        assert resolved.doi == "10.5555/3295222.3295349"
        assert resolved.venue == "NeurIPS"
        assert resolved.year == 2017
        assert resolved.published_date == "2017-06-12"
        assert resolved.citation_count == 90000
        assert resolved.scholar_inbox_score == 95.0

    def test_falls_back_to_raw_fields(self, raw_paper_with_arxiv):
        data = {
            "paperId": "xyz",
            "title": None,
            "authors": [],
            "abstract": None,
            "url": None,
            "venue": None,
            "year": None,
            "publicationDate": None,
            "citationCount": 0,
        }
        resolved = _parse_s2_response(data, raw_paper_with_arxiv)

        assert resolved.title == raw_paper_with_arxiv.title
        assert resolved.authors == raw_paper_with_arxiv.authors
        assert resolved.abstract == raw_paper_with_arxiv.abstract
        assert resolved.url == raw_paper_with_arxiv.scholar_inbox_url

    def test_missing_external_ids(self, raw_paper_with_arxiv):
        data = _s2_paper_response()
        data["externalIds"] = None
        resolved = _parse_s2_response(data, raw_paper_with_arxiv)
        assert resolved.arxiv_id is None
        assert resolved.doi is None


# ---------------------------------------------------------------------------
# Fallback ID generation
# ---------------------------------------------------------------------------

class TestGenerateFallbackId:
    def test_arxiv_id_preferred(self, raw_paper_with_arxiv):
        fid = _generate_fallback_id(raw_paper_with_arxiv)
        assert fid == "arxiv:1706.03762"

    def test_title_hash_when_no_arxiv(self, raw_paper_no_arxiv):
        fid = _generate_fallback_id(raw_paper_no_arxiv)
        expected_hash = hashlib.sha256(
            _normalize_title(raw_paper_no_arxiv.title).encode()
        ).hexdigest()[:16]
        assert fid == f"title:{expected_hash}"

    def test_deterministic(self, raw_paper_no_arxiv):
        assert _generate_fallback_id(raw_paper_no_arxiv) == _generate_fallback_id(raw_paper_no_arxiv)


class TestCreateFallbackResolved:
    def test_creates_resolved_paper(self, raw_paper_with_arxiv):
        resolved = _create_fallback_resolved(raw_paper_with_arxiv)
        assert resolved.semantic_scholar_id == "arxiv:1706.03762"
        assert resolved.title == raw_paper_with_arxiv.title
        assert resolved.citation_count == 0
        assert resolved.doi is None


class TestCreatePreResolved:
    def test_uses_existing_s2_id(self):
        raw = RawPaper(
            title="Pre-Resolved Paper",
            authors=["Alice"],
            abstract="Already has S2 ID",
            score=90.0,
            arxiv_id="2602.99999",
            semantic_scholar_id="existing_s2_id_abc",
            paper_id=1234,
            venue="NeurIPS 2026",
            year=2026,
            scholar_inbox_url="https://www.scholar-inbox.com/paper/2602.99999",
        )
        resolved = _create_pre_resolved(raw)
        assert resolved.semantic_scholar_id == "existing_s2_id_abc"
        assert resolved.title == "Pre-Resolved Paper"
        assert resolved.citation_count == 0
        assert resolved.doi is None
        assert resolved.arxiv_id == "2602.99999"
        assert resolved.scholar_inbox_score == 90.0

    def test_preserves_all_raw_fields(self):
        raw = RawPaper(
            title="Test",
            authors=["Bob"],
            abstract="Abstract text",
            score=75.0,
            semantic_scholar_id="s2_xyz",
            venue="ICML",
            year=2025,
            scholar_inbox_url="https://example.com",
            publication_date="2025-06-01",
        )
        resolved = _create_pre_resolved(raw)
        assert resolved.venue == "ICML"
        assert resolved.year == 2025
        assert resolved.published_date == "2025-06-01"
        assert resolved.url == "https://example.com"


# ---------------------------------------------------------------------------
# resolve_paper (mocked HTTP)
# ---------------------------------------------------------------------------

class TestResolvePaper:
    @pytest.mark.asyncio
    async def test_resolve_by_arxiv(self, raw_paper_with_arxiv, config_with_key):
        """Paper with arXiv ID resolves via direct lookup."""
        s2_data = _s2_paper_response()
        mock_resp = _mock_response(200, json=s2_data)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        result = await resolve_paper(client, raw_paper_with_arxiv, config_with_key)

        assert result is not None
        assert result.semantic_scholar_id == "abc123"
        assert result.arxiv_id == "1706.03762"

    @pytest.mark.asyncio
    async def test_resolve_by_title_search(self, raw_paper_no_arxiv, config_with_key):
        """Paper without arXiv ID falls back to title search."""
        search_data = {
            "data": [
                _s2_paper_response(
                    paper_id="found456",
                    title="Some Novel Method for NLP",
                    arxiv_id=None,
                ),
            ]
        }
        mock_resp = _mock_response(200, json=search_data)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        result = await resolve_paper(client, raw_paper_no_arxiv, config_with_key)

        assert result is not None
        assert result.semantic_scholar_id == "found456"

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self, raw_paper_no_arxiv, config_with_key):
        """Paper not found on S2 returns None."""
        mock_empty_search = _mock_response(200, json={"data": []})

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_empty_search)

        result = await resolve_paper(client, raw_paper_no_arxiv, config_with_key)
        assert result is None

    @pytest.mark.asyncio
    async def test_arxiv_404_falls_back_to_title(self, raw_paper_with_arxiv, config_with_key):
        """If arXiv lookup returns 404, falls back to title search."""
        mock_404 = _mock_response(404)
        search_data = {
            "data": [
                _s2_paper_response(paper_id="title_match_789"),
            ]
        }
        mock_search = _mock_response(200, json=search_data)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=[mock_404, mock_search])

        result = await resolve_paper(client, raw_paper_with_arxiv, config_with_key)

        assert result is not None
        assert result.semantic_scholar_id == "title_match_789"

    @pytest.mark.asyncio
    async def test_title_search_no_good_match(self, raw_paper_no_arxiv, config_with_key):
        """Title search returns results but none match well enough."""
        search_data = {
            "data": [
                _s2_paper_response(
                    paper_id="bad_match",
                    title="Completely Unrelated Paper Title About Chemistry",
                ),
            ]
        }
        mock_resp = _mock_response(200, json=search_data)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        result = await resolve_paper(client, raw_paper_no_arxiv, config_with_key)
        assert result is None


# ---------------------------------------------------------------------------
# resolve_papers (batch)
# ---------------------------------------------------------------------------

class TestResolvePapers:
    @pytest.mark.asyncio
    async def test_batch_with_fallbacks(self, raw_paper_with_arxiv, raw_paper_no_arxiv, config_with_key):
        """Batch resolves papers; unresolvable ones get fallback IDs."""
        # raw_paper_with_arxiv has no semantic_scholar_id set, so it needs S2 API
        s2_data = _s2_paper_response()
        mock_success = _mock_response(200, json=s2_data)
        mock_empty = _mock_response(200, json={"data": []})

        client = AsyncMock(spec=httpx.AsyncClient)
        # First paper resolves via arXiv, second fails title search
        client.get = AsyncMock(side_effect=[mock_success, mock_empty])

        results = await resolve_papers(
            client, [raw_paper_with_arxiv, raw_paper_no_arxiv], config_with_key
        )

        assert len(results) == 2
        # First paper resolved normally
        assert results[0].semantic_scholar_id == "abc123"
        # Second paper got fallback
        assert results[1].semantic_scholar_id.startswith("title:")

    @pytest.mark.asyncio
    async def test_empty_list(self, config_with_key):
        client = AsyncMock(spec=httpx.AsyncClient)
        results = await resolve_papers(client, [], config_with_key)
        assert results == []

    @pytest.mark.asyncio
    async def test_pre_resolved_skips_api(self, config_with_key):
        """Papers with existing semantic_scholar_id skip the S2 API call."""
        pre_resolved_paper = RawPaper(
            title="Already Resolved Paper",
            authors=["Alice"],
            abstract="Has S2 ID from Scholar Inbox",
            score=90.0,
            arxiv_id="2602.12345",
            semantic_scholar_id="existing_s2_id",
            paper_id=42,
        )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock()  # Should NOT be called

        results = await resolve_papers(client, [pre_resolved_paper], config_with_key)

        assert len(results) == 1
        assert results[0].semantic_scholar_id == "existing_s2_id"
        assert results[0].title == "Already Resolved Paper"
        client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_mixed_pre_resolved_and_unresolved(self, raw_paper_no_arxiv, config_with_key):
        """Mix of pre-resolved and unresolved papers."""
        pre_resolved = RawPaper(
            title="Pre-Resolved",
            authors=["Bob"],
            abstract="Has S2 ID",
            score=85.0,
            semantic_scholar_id="pre_s2_id",
        )
        # raw_paper_no_arxiv has no semantic_scholar_id
        mock_empty = _mock_response(200, json={"data": []})
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_empty)

        results = await resolve_papers(
            client, [pre_resolved, raw_paper_no_arxiv], config_with_key
        )

        assert len(results) == 2
        # First: pre-resolved (no API call)
        assert results[0].semantic_scholar_id == "pre_s2_id"
        # Second: fallback (API returned no results)
        assert results[1].semantic_scholar_id.startswith("title:")


# ---------------------------------------------------------------------------
# Rate limiting & error handling
# ---------------------------------------------------------------------------

class TestRateLimitingAndErrors:
    @pytest.mark.asyncio
    async def test_429_retry(self, raw_paper_with_arxiv, config_no_key):
        """429 response triggers retry."""
        s2_data = _s2_paper_response()
        mock_429 = _mock_response(429, headers={"Retry-After": "1"})
        mock_success = _mock_response(200, json=s2_data)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=[mock_429, mock_success])

        with patch("src.ingestion.resolver.DEFAULT_RETRY", _FAST_RETRY):
            result = await resolve_paper(client, raw_paper_with_arxiv, config_no_key)

        assert result is not None
        assert result.semantic_scholar_id == "abc123"
        assert client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_429_multiple_retries(self, raw_paper_with_arxiv, config_no_key):
        """Multiple 429 responses are retried."""
        s2_data = _s2_paper_response()
        mock_429 = _mock_response(429, headers={"Retry-After": "1"})
        mock_success = _mock_response(200, json=s2_data)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=[mock_429, mock_429, mock_429, mock_success])

        with patch("src.ingestion.resolver.DEFAULT_RETRY", _FAST_RETRY):
            result = await resolve_paper(client, raw_paper_with_arxiv, config_no_key)

        assert result is not None
        assert result.semantic_scholar_id == "abc123"
        assert client.get.call_count == 4

    @pytest.mark.asyncio
    async def test_429_all_attempts_exhausted(self, raw_paper_with_arxiv, config_no_key):
        """All retry attempts exhausted on 429 returns None."""
        mock_429 = _mock_response(429, headers={"Retry-After": "0"})

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_429)

        with patch("src.ingestion.resolver.DEFAULT_RETRY", _FAST_RETRY):
            result = await resolve_paper(client, raw_paper_with_arxiv, config_no_key)

        # raise_for_status on 429 causes HTTPError, caught → returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_5xx_retry(self, raw_paper_with_arxiv, config_with_key):
        """5xx errors trigger retry."""
        s2_data = _s2_paper_response()
        mock_500 = _mock_response(500)
        mock_success = _mock_response(200, json=s2_data)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=[mock_500, mock_success])

        with patch("src.ingestion.resolver.DEFAULT_RETRY", _FAST_RETRY):
            result = await resolve_paper(client, raw_paper_with_arxiv, config_with_key)

        assert result is not None
        assert result.semantic_scholar_id == "abc123"

    @pytest.mark.asyncio
    async def test_fixed_retry_strategy(self, raw_paper_with_arxiv, config_with_key):
        """Fixed strategy retries with constant delay."""
        s2_data = _s2_paper_response()
        mock_500 = _mock_response(500)
        mock_success = _mock_response(200, json=s2_data)
        fixed_retry = RetryConfig(max_attempts=3, strategy="fixed", base_delay=0.0)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=[mock_500, mock_500, mock_success])

        with patch("src.ingestion.resolver.DEFAULT_RETRY", fixed_retry):
            result = await resolve_paper(client, raw_paper_with_arxiv, config_with_key)

        assert result is not None
        assert client.get.call_count == 3

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self, raw_paper_no_arxiv, config_with_key):
        """Timeout during resolution returns None."""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        result = await resolve_paper(client, raw_paper_no_arxiv, config_with_key)
        assert result is None

    @pytest.mark.asyncio
    async def test_uses_api_key_header(self, raw_paper_with_arxiv, config_with_key):
        """API key is included in request headers when configured."""
        s2_data = _s2_paper_response()
        mock_resp = _mock_response(200, json=s2_data)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        await resolve_paper(client, raw_paper_with_arxiv, config_with_key)

        # Check that the x-api-key header was passed
        call_kwargs = client.get.call_args_list[0]
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert headers.get("x-api-key") == "test-key-123"

    @pytest.mark.asyncio
    async def test_no_api_key_no_header(self, raw_paper_with_arxiv, config_no_key):
        """No x-api-key header when API key is not configured."""
        s2_data = _s2_paper_response()
        mock_resp = _mock_response(200, json=s2_data)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        await resolve_paper(client, raw_paper_with_arxiv, config_no_key)

        call_kwargs = client.get.call_args_list[0]
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert "x-api-key" not in headers


# ---------------------------------------------------------------------------
# Category pass-through
# ---------------------------------------------------------------------------

class TestCategoryPassThrough:
    def test_parse_s2_response_carries_category(self):
        raw = RawPaper(
            title="Test Paper",
            authors=["Alice"],
            abstract="Abstract",
            score=0.9,
            category="Computer Vision and Graphics",
        )
        data = _s2_paper_response()
        resolved = _parse_s2_response(data, raw)
        assert resolved.category == "Computer Vision and Graphics"

    def test_parse_s2_response_none_category(self):
        raw = RawPaper(
            title="Test Paper",
            authors=["Alice"],
            abstract="Abstract",
            score=0.9,
        )
        data = _s2_paper_response()
        resolved = _parse_s2_response(data, raw)
        assert resolved.category is None

    def test_fallback_resolved_carries_category(self):
        raw = RawPaper(
            title="Fallback Paper",
            authors=["Bob"],
            abstract="Abstract",
            score=0.8,
            category="Natural Language Processing",
        )
        resolved = _create_fallback_resolved(raw)
        assert resolved.category == "Natural Language Processing"

    def test_pre_resolved_carries_category(self):
        raw = RawPaper(
            title="Pre-Resolved",
            authors=["Charlie"],
            abstract="Abstract",
            score=0.85,
            semantic_scholar_id="s2_id",
            category="Machine Learning",
        )
        resolved = _create_pre_resolved(raw)
        assert resolved.category == "Machine Learning"
