"""Tests for src.citations.openalex."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.citations.openalex import (
    _parse_openalex_work,
    fetch_yearly_citations,
)


def _make_response(data, status_code=200):
    """Create a MagicMock mimicking an httpx.Response (sync json/raise_for_status)."""
    resp = MagicMock()
    resp.json.return_value = data
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# _parse_openalex_work
# ---------------------------------------------------------------------------

class TestParseOpenalexWork:
    def test_basic_parsing(self):
        work = {
            "cited_by_count": 150,
            "counts_by_year": [
                {"year": 2024, "cited_by_count": 50},
                {"year": 2023, "cited_by_count": 60},
                {"year": 2022, "cited_by_count": 40},
            ],
        }
        result = _parse_openalex_work(work)
        assert result["total"] == 150
        assert result["by_year"] == {"2024": 50, "2023": 60, "2022": 40}

    def test_empty_counts(self):
        work = {"cited_by_count": 0, "counts_by_year": []}
        result = _parse_openalex_work(work)
        assert result["total"] == 0
        assert result["by_year"] == {}

    def test_missing_fields(self):
        work = {}
        result = _parse_openalex_work(work)
        assert result["total"] == 0
        assert result["by_year"] == {}


# ---------------------------------------------------------------------------
# fetch_yearly_citations
# ---------------------------------------------------------------------------

class TestFetchYearlyCitations:
    @pytest.mark.asyncio
    async def test_doi_lookup_success(self):
        work_data = {
            "cited_by_count": 100,
            "counts_by_year": [
                {"year": 2024, "cited_by_count": 30},
            ],
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = _make_response(work_data)

        result = await fetch_yearly_citations(
            client, doi="10.1234/test", title="Some Paper", email="test@example.com"
        )
        assert result is not None
        assert result["total"] == 100
        assert result["by_year"]["2024"] == 30

    @pytest.mark.asyncio
    async def test_doi_not_found_falls_back_to_title(self):
        not_found_response = _make_response({}, status_code=404)
        title_result = {
            "results": [
                {
                    "title": "My Paper Title",
                    "cited_by_count": 50,
                    "counts_by_year": [{"year": 2024, "cited_by_count": 20}],
                }
            ]
        }
        title_response = _make_response(title_result)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [not_found_response, title_response]

        result = await fetch_yearly_citations(
            client, doi="10.1234/missing", title="My Paper Title"
        )
        assert result is not None
        assert result["total"] == 50

    @pytest.mark.asyncio
    async def test_title_search_no_match(self):
        """Title search returns results but none match above threshold."""
        title_result = {
            "results": [
                {
                    "title": "Completely Different Paper",
                    "cited_by_count": 50,
                    "counts_by_year": [],
                }
            ]
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = _make_response(title_result)

        result = await fetch_yearly_citations(
            client, doi=None, title="My Specific Paper Title"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_no_doi_no_title(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        result = await fetch_yearly_citations(client, doi=None, title=None)
        assert result is None
        client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_doi_lookup_error(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = httpx.HTTPError("connection error")

        result = await fetch_yearly_citations(
            client, doi="10.1234/test", title=None
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_email_passed_as_mailto(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = _make_response({
            "cited_by_count": 10,
            "counts_by_year": [],
        })

        await fetch_yearly_citations(
            client, doi="10.1234/test", title=None, email="user@example.com"
        )
        # Verify mailto was passed in params
        call_kwargs = client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        assert params.get("mailto") == "user@example.com"
