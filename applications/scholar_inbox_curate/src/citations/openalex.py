"""OpenAlex citation fetching.

Provides yearly citation breakdowns as a secondary source.  Uses DOI
lookup (preferred) with title-search fallback.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from src.constants import OPENALEX_BASE_URL, OPENALEX_RATE_DELAY, SIMILARITY_THRESHOLD
from src.ingestion.resolver import _normalize_title, _title_similarity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_openalex_work(work: dict) -> dict:
    """Extract citation data from an OpenAlex work object.

    Returns
    -------
    dict
        ``{"total": int, "by_year": {str: int}}`` where keys in ``by_year``
        are year strings (e.g. ``"2024"``).
    """
    total = work.get("cited_by_count", 0)
    by_year: dict[str, int] = {}
    for entry in work.get("counts_by_year", []):
        year = str(entry.get("year", ""))
        count = entry.get("cited_by_count", 0)
        if year:
            by_year[year] = count
    return {"total": total, "by_year": by_year}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_yearly_citations(
    client: httpx.AsyncClient,
    doi: str | None,
    title: str | None,
    email: str | None = None,
) -> dict | None:
    """Fetch yearly citation breakdown from OpenAlex.

    Tries DOI lookup first, then falls back to title search with fuzzy
    matching.

    Parameters
    ----------
    client : httpx.AsyncClient
    doi : str | None
        Paper DOI (preferred lookup method).
    title : str | None
        Paper title (fallback search method).
    email : str | None
        Contact email for the OpenAlex polite pool (``mailto`` param).

    Returns
    -------
    dict | None
        ``{"total": int, "by_year": {str: int}}`` or ``None`` on failure.
    """
    params: dict[str, str] = {}
    if email:
        params["mailto"] = email

    # Strategy 1: DOI lookup
    if doi:
        result = await _fetch_by_doi(client, doi, params)
        if result is not None:
            return result

    # Strategy 2: title search
    if title:
        result = await _fetch_by_title(client, title, params)
        if result is not None:
            return result

    return None


# ---------------------------------------------------------------------------
# Internal strategies
# ---------------------------------------------------------------------------

async def _fetch_by_doi(
    client: httpx.AsyncClient,
    doi: str,
    params: dict,
) -> dict | None:
    """Look up a work by DOI."""
    url = f"{OPENALEX_BASE_URL}/works/doi:{doi}"
    try:
        await asyncio.sleep(OPENALEX_RATE_DELAY)
        resp = await client.get(url, params=params, timeout=30.0)
        if resp.status_code == 404:
            logger.debug("DOI %s not found on OpenAlex", doi)
            return None
        resp.raise_for_status()
        return _parse_openalex_work(resp.json())
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("OpenAlex DOI lookup failed for %s: %s", doi, exc)
        return None


async def _fetch_by_title(
    client: httpx.AsyncClient,
    title: str,
    params: dict,
) -> dict | None:
    """Search for a work by title with fuzzy matching."""
    search_params = {**params, "search": title, "per_page": "5"}
    url = f"{OPENALEX_BASE_URL}/works"
    try:
        await asyncio.sleep(OPENALEX_RATE_DELAY)
        resp = await client.get(url, params=search_params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None

        # Find best title match
        best_work = None
        best_score = 0.0
        for work in results:
            work_title = work.get("title", "")
            if not work_title:
                continue
            score = _title_similarity(title, work_title)
            if score > best_score:
                best_score = score
                best_work = work

        if best_work and best_score >= SIMILARITY_THRESHOLD:
            return _parse_openalex_work(best_work)

        return None
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("OpenAlex title search failed for '%s': %s", title[:60], exc)
        return None
