"""Tests for src.citations.semantic_scholar."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.citations.semantic_scholar import (
    _fetch_batch,
    _get_headers,
    _to_s2_id,
    fetch_citations_batch,
)


def _make_response(data, status_code=200):
    """Create a MagicMock mimicking an httpx.Response (sync json/raise_for_status)."""
    resp = MagicMock()
    resp.json.return_value = data
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# _to_s2_id
# ---------------------------------------------------------------------------

class TestToS2Id:
    def test_arxiv_prefix(self):
        assert _to_s2_id("arxiv:2301.12345") == "ARXIV:2301.12345"

    def test_doi_prefix(self):
        assert _to_s2_id("doi:10.1234/test") == "DOI:10.1234/test"

    def test_title_prefix_returns_none(self):
        assert _to_s2_id("title:abc123") is None

    def test_s2_hash_passthrough(self):
        s2_id = "a1b2c3d4e5f6"
        assert _to_s2_id(s2_id) == s2_id

    def test_empty_arxiv(self):
        assert _to_s2_id("arxiv:") == "ARXIV:"

    def test_doi_with_slash(self):
        assert _to_s2_id("doi:10.1000/xyz123") == "DOI:10.1000/xyz123"


# ---------------------------------------------------------------------------
# _get_headers
# ---------------------------------------------------------------------------

class TestGetHeaders:
    def test_with_api_key(self):
        headers = _get_headers("my-key")
        assert headers["x-api-key"] == "my-key"
        assert "Content-Type" in headers

    def test_without_api_key(self):
        headers = _get_headers(None)
        assert "x-api-key" not in headers
        assert headers["Accept"] == "application/json"


# ---------------------------------------------------------------------------
# _fetch_batch
# ---------------------------------------------------------------------------

class TestFetchBatch:
    @pytest.mark.asyncio
    async def test_success(self):
        response_data = [
            {"paperId": "abc", "citationCount": 42, "externalIds": {}},
            None,
        ]
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _make_response(response_data)

        result = await _fetch_batch(client, ["ARXIV:123", "ARXIV:456"], {})
        assert len(result) == 2
        assert result[0]["citationCount"] == 42
        assert result[1] is None

    @pytest.mark.asyncio
    async def test_null_entries_preserved(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _make_response([None, None, None])

        result = await _fetch_batch(client, ["a", "b", "c"], {})
        assert result == [None, None, None]


# ---------------------------------------------------------------------------
# fetch_citations_batch
# ---------------------------------------------------------------------------

class TestFetchCitationsBatch:
    @pytest.mark.asyncio
    async def test_basic_success(self):
        response_data = [
            {"paperId": "abc", "citationCount": 10, "externalIds": {}},
            {"paperId": "def", "citationCount": 20, "externalIds": {}},
        ]
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _make_response(response_data)

        result = await fetch_citations_batch(
            client, ["arxiv:123", "arxiv:456"], api_key="key", batch_size=100,
        )
        assert result == {"arxiv:123": 10, "arxiv:456": 20}

    @pytest.mark.asyncio
    async def test_title_papers_skipped(self):
        """Papers with title: prefix should not be sent to the batch API."""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _make_response([
            {"paperId": "abc", "citationCount": 5, "externalIds": {}},
        ])

        result = await fetch_citations_batch(
            client, ["arxiv:123", "title:abcdef"], api_key=None, batch_size=100,
        )
        assert "arxiv:123" in result
        assert "title:abcdef" not in result

    @pytest.mark.asyncio
    async def test_batching_splits_large_list(self):
        """Should split into multiple batch requests when exceeding batch_size."""
        def make_batch_response(*args, **kwargs):
            ids = kwargs.get("json", {}).get("ids", [])
            return _make_response([
                {"paperId": s2id, "citationCount": 1, "externalIds": {}}
                for s2id in ids
            ])

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.side_effect = make_batch_response

        paper_ids = [f"s2id{i}" for i in range(5)]
        result = await fetch_citations_batch(
            client, paper_ids, api_key="key", batch_size=2,
        )
        # Should have made 3 POST calls (2+2+1)
        assert client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_429_retry(self):
        """Should retry after a 429 response."""
        error_response = httpx.Response(
            429,
            headers={"Retry-After": "1"},
            request=httpx.Request("POST", "https://example.com"),
        )
        success_data = [
            {"paperId": "abc", "citationCount": 7, "externalIds": {}},
        ]

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.side_effect = [
            httpx.HTTPStatusError(
                "429", request=error_response.request, response=error_response
            ),
            _make_response(success_data),
        ]

        result = await fetch_citations_batch(
            client, ["arxiv:123"], api_key="key", batch_size=100,
        )
        assert result == {"arxiv:123": 7}
        assert client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_5xx_retry_then_skip(self):
        """Should retry once on 5xx, then skip the batch."""
        error_response = httpx.Response(
            503, request=httpx.Request("POST", "https://example.com"),
        )
        error = httpx.HTTPStatusError(
            "503", request=error_response.request, response=error_response
        )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.side_effect = [error, error]

        result = await fetch_citations_batch(
            client, ["arxiv:123"], api_key="key", batch_size=100,
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Should skip batch on timeout."""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.side_effect = httpx.TimeoutException("timeout")

        result = await fetch_citations_batch(
            client, ["arxiv:123"], api_key=None, batch_size=100,
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_input(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        result = await fetch_citations_batch(client, [], api_key=None)
        assert result == {}
        client.post.assert_not_called()
