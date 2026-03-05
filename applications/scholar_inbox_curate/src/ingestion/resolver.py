"""Paper ID resolution via Semantic Scholar API.

Resolves scraped papers to canonical Semantic Scholar paper IDs and enriches
records with metadata (venue, year, publication date, DOI, citation count).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

import httpx

from src.constants import (
    RATE_LIMIT_DELAY_NO_KEY,
    RATE_LIMIT_DELAY_WITH_KEY,
    S2_BASE_URL,
    S2_FIELDS,
    SIMILARITY_THRESHOLD,
)
from src.ingestion.scraper import RawPaper

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class ResolvedPaper:
    """A paper with a resolved Semantic Scholar ID and enriched metadata."""

    semantic_scholar_id: str
    title: str
    authors: list[str]
    abstract: str
    url: str | None
    arxiv_id: str | None
    doi: str | None
    venue: str | None
    year: int | None
    published_date: str | None
    citation_count: int
    scholar_inbox_score: float
    scholar_inbox_url: str | None
    category: str | None = None


# ---------------------------------------------------------------------------
# Title matching
# ---------------------------------------------------------------------------

def _normalize_title(title: str) -> str:
    """Normalize a title for comparison (lowercase, no punctuation, collapsed whitespace)."""
    title = title.lower().strip()
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title


def _title_similarity(title1: str, title2: str) -> float:
    """Compute similarity ratio between two titles (0.0 to 1.0)."""
    t1 = _normalize_title(title1)
    t2 = _normalize_title(title2)
    return SequenceMatcher(None, t1, t2).ratio()


def _find_best_match(scraped_title: str, results: list[dict]) -> dict | None:
    """Find the best matching paper from S2 search results.

    Returns the result with the highest title similarity if it exceeds
    ``SIMILARITY_THRESHOLD``, otherwise ``None``.
    """
    best = None
    best_score = 0.0

    for result in results:
        score = _title_similarity(scraped_title, result.get("title", ""))
        if score > best_score:
            best_score = score
            best = result

    if best and best_score >= SIMILARITY_THRESHOLD:
        return best

    return None


# ---------------------------------------------------------------------------
# S2 API helpers
# ---------------------------------------------------------------------------

def _get_headers(config) -> dict:
    """Build request headers, optionally including the API key."""
    headers = {"Accept": "application/json"}
    api_key = config.secrets.semantic_scholar_api_key
    if api_key:
        headers["x-api-key"] = api_key
    return headers


async def _rate_limited_request(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    has_api_key: bool,
    *,
    params: dict | None = None,
) -> httpx.Response:
    """Make an API request with rate limiting and 429 retry."""
    delay = RATE_LIMIT_DELAY_WITH_KEY if has_api_key else RATE_LIMIT_DELAY_NO_KEY
    await asyncio.sleep(delay)

    response = await client.get(url, headers=headers, params=params, timeout=30.0)

    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", "5"))
        logger.warning("Rate limited by Semantic Scholar, retrying in %ds", retry_after)
        await asyncio.sleep(retry_after)
        response = await client.get(url, headers=headers, params=params, timeout=30.0)

    return response


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_s2_response(data: dict, raw: RawPaper) -> ResolvedPaper:
    """Convert a Semantic Scholar API response dict into a ``ResolvedPaper``."""
    authors = [a["name"] for a in data.get("authors", []) if "name" in a]
    external_ids = data.get("externalIds") or {}

    return ResolvedPaper(
        semantic_scholar_id=data["paperId"],
        title=data.get("title") or raw.title,
        authors=authors if authors else raw.authors,
        abstract=data.get("abstract") or raw.abstract,
        url=data.get("url") or raw.scholar_inbox_url,
        arxiv_id=external_ids.get("ArXiv"),
        doi=external_ids.get("DOI"),
        venue=data.get("venue") or raw.venue,
        year=data.get("year") or raw.year,
        published_date=data.get("publicationDate"),
        citation_count=data.get("citationCount", 0),
        scholar_inbox_score=raw.score,
        scholar_inbox_url=raw.scholar_inbox_url,
        category=raw.category,
    )


# ---------------------------------------------------------------------------
# Fallback ID generation
# ---------------------------------------------------------------------------

def _generate_fallback_id(raw: RawPaper) -> str:
    """Generate a deterministic fallback ID for papers not found on S2.

    Priority:
    1. ``arxiv:{arxiv_id}`` — if arXiv ID is known
    2. ``title:{hash}`` — SHA-256 of normalized title (first 16 hex chars)
    """
    if raw.arxiv_id:
        return f"arxiv:{raw.arxiv_id}"

    title_hash = hashlib.sha256(
        _normalize_title(raw.title).encode()
    ).hexdigest()[:16]
    return f"title:{title_hash}"


def _create_fallback_resolved(raw: RawPaper) -> ResolvedPaper:
    """Create a ``ResolvedPaper`` with a synthetic fallback ID."""
    return ResolvedPaper(
        semantic_scholar_id=_generate_fallback_id(raw),
        title=raw.title,
        authors=raw.authors,
        abstract=raw.abstract,
        url=raw.scholar_inbox_url,
        arxiv_id=raw.arxiv_id,
        doi=None,
        venue=raw.venue,
        year=raw.year,
        published_date=raw.publication_date,
        citation_count=0,
        scholar_inbox_score=raw.score,
        scholar_inbox_url=raw.scholar_inbox_url,
        category=raw.category,
    )


def _create_pre_resolved(raw: RawPaper) -> ResolvedPaper:
    """Convert a ``RawPaper`` that already has a ``semantic_scholar_id`` into a ``ResolvedPaper``.

    Used when Scholar Inbox provides the S2 ID directly, skipping the
    Semantic Scholar API call.  Citation count defaults to 0 and will be
    populated on the first citation poll.
    """
    return ResolvedPaper(
        semantic_scholar_id=raw.semantic_scholar_id,
        title=raw.title,
        authors=raw.authors,
        abstract=raw.abstract,
        url=raw.scholar_inbox_url,
        arxiv_id=raw.arxiv_id,
        doi=None,
        venue=raw.venue,
        year=raw.year,
        published_date=raw.publication_date,
        citation_count=0,
        scholar_inbox_score=raw.score,
        scholar_inbox_url=raw.scholar_inbox_url,
        category=raw.category,
    )


def paper_to_dict(paper: ResolvedPaper) -> dict:
    """Convert a ResolvedPaper dataclass to a dictionary for database storage.

    Parameters
    ----------
    paper : ResolvedPaper
        The resolved paper to convert

    Returns
    -------
    dict
        Dictionary with keys matching the papers table schema
    """
    from datetime import datetime, timezone

    return {
        "id": paper.semantic_scholar_id,
        "title": paper.title,
        "authors": __import__("json").dumps(paper.authors),
        "abstract": paper.abstract,
        "url": paper.url,
        "arxiv_id": paper.arxiv_id,
        "doi": paper.doi,
        "venue": paper.venue,
        "year": paper.year,
        "published_date": paper.published_date,
        "scholar_inbox_score": paper.scholar_inbox_score,
        "scholar_inbox_url": paper.scholar_inbox_url,
        "category": paper.category,
        "citation_count": paper.citation_count,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "status": "active",
        "manual_status": 0,
    }


# ---------------------------------------------------------------------------
# Resolution strategies
# ---------------------------------------------------------------------------

async def _resolve_by_arxiv(
    client: httpx.AsyncClient,
    raw: RawPaper,
    headers: dict,
    has_api_key: bool,
) -> ResolvedPaper | None:
    """Try to resolve a paper by its arXiv ID."""
    if not raw.arxiv_id:
        return None

    url = f"{S2_BASE_URL}/paper/ARXIV:{raw.arxiv_id}"
    try:
        resp = await _rate_limited_request(
            client, url, headers, has_api_key, params={"fields": S2_FIELDS}
        )
        if resp.status_code == 404:
            logger.debug("arXiv ID %s not found on S2", raw.arxiv_id)
            return None
        if resp.status_code >= 500:
            logger.warning("S2 server error %d for arXiv:%s, retrying once", resp.status_code, raw.arxiv_id)
            await asyncio.sleep(5)
            resp = await client.get(url, headers=headers, params={"fields": S2_FIELDS}, timeout=30.0)
            if not resp.is_success:
                return None
        resp.raise_for_status()
        return _parse_s2_response(resp.json(), raw)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("Failed to resolve arXiv:%s — %s", raw.arxiv_id, exc)
        return None


async def _resolve_by_doi(
    client: httpx.AsyncClient,
    raw: RawPaper,
    doi: str,
    headers: dict,
    has_api_key: bool,
) -> ResolvedPaper | None:
    """Try to resolve a paper by its DOI.

    Parameters
    ----------
    client : httpx.AsyncClient
    raw : RawPaper
    doi : str
        The DOI string (without "DOI:" prefix)
    headers : dict
        Request headers including API key if available
    has_api_key : bool
        Whether the API key is set (affects rate limiting)

    Returns
    -------
    ResolvedPaper | None
        Resolved paper if found, None otherwise
    """
    url = f"{S2_BASE_URL}/paper/DOI:{doi}"
    try:
        resp = await _rate_limited_request(
            client, url, headers, has_api_key, params={"fields": S2_FIELDS}
        )
        if resp.status_code == 404:
            logger.debug("DOI %s not found on S2", doi)
            return None
        if resp.status_code >= 500:
            logger.warning("S2 server error %d for DOI:%s, retrying once", resp.status_code, doi)
            await asyncio.sleep(5)
            resp = await client.get(url, headers=headers, params={"fields": S2_FIELDS}, timeout=30.0)
            if not resp.is_success:
                return None
        resp.raise_for_status()
        return _parse_s2_response(resp.json(), raw)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("Failed to resolve DOI:%s — %s", doi, exc)
        return None


async def _resolve_by_title(
    client: httpx.AsyncClient,
    raw: RawPaper,
    headers: dict,
    has_api_key: bool,
) -> ResolvedPaper | None:
    """Try to resolve a paper by title search + fuzzy matching."""
    url = f"{S2_BASE_URL}/paper/search"
    params = {"query": raw.title, "fields": S2_FIELDS, "limit": "5"}

    try:
        resp = await _rate_limited_request(
            client, url, headers, has_api_key, params=params
        )
        if resp.status_code >= 500:
            logger.warning("S2 server error %d for title search, retrying once", resp.status_code)
            await asyncio.sleep(5)
            resp = await client.get(url, headers=headers, params=params, timeout=30.0)
            if not resp.is_success:
                return None
        resp.raise_for_status()

        data = resp.json()
        results = data.get("data", [])
        if not results:
            return None

        match = _find_best_match(raw.title, results)
        if match is None:
            return None

        return _parse_s2_response(match, raw)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("Failed title search for '%s' — %s", raw.title[:60], exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def resolve_paper(
    client: httpx.AsyncClient,
    raw: RawPaper,
    config,
) -> ResolvedPaper | None:
    """Resolve a single ``RawPaper`` to a ``ResolvedPaper`` via Semantic Scholar.

    Resolution priority:
    1. arXiv ID lookup (if available)
    2. DOI lookup (if available)
    3. Title search (fallback)

    Returns ``None`` if the paper cannot be found.
    """
    headers = _get_headers(config)
    has_api_key = bool(config.secrets.semantic_scholar_api_key)

    # Strategy 1: arXiv ID (most reliable)
    result = await _resolve_by_arxiv(client, raw, headers, has_api_key)
    if result:
        return result

    # Strategy 2: DOI (if available from Scholar Inbox metadata)
    # Note: Most Scholar Inbox papers don't have DOI, but attempt if we find one
    # This can be extended if we extract DOI from paper metadata
    if hasattr(raw, 'doi') and raw.doi:
        result = await _resolve_by_doi(client, raw, raw.doi, headers, has_api_key)
        if result:
            return result

    # Strategy 3: title search (fallback)
    result = await _resolve_by_title(client, raw, headers, has_api_key)
    if result:
        return result

    return None


async def resolve_papers(
    client: httpx.AsyncClient,
    papers: list[RawPaper],
    config,
) -> list[ResolvedPaper]:
    """Resolve a batch of ``RawPaper`` objects with progress logging.

    Papers that already have a ``semantic_scholar_id`` from Scholar Inbox
    are converted directly without an API call.  Only papers missing their
    S2 ID go through the Semantic Scholar resolution pipeline.

    Papers that cannot be found on Semantic Scholar receive a fallback ID.
    """
    resolved: list[ResolvedPaper] = []
    skipped = 0
    failed = 0

    for i, raw in enumerate(papers):
        # Optimization: Scholar Inbox already provides semantic_scholar_id
        # for most papers — skip the S2 API call for these.
        if raw.semantic_scholar_id:
            resolved.append(_create_pre_resolved(raw))
            skipped += 1
            continue

        logger.info("Resolving paper %d/%d: %s", i + 1, len(papers), raw.title[:60])

        result = await resolve_paper(client, raw, config)

        if result:
            resolved.append(result)
        else:
            failed += 1
            logger.warning("Could not resolve: %s", raw.title[:80])
            resolved.append(_create_fallback_resolved(raw))

    logger.info(
        "Resolution complete: %d pre-resolved, %d resolved via S2, "
        "%d used fallback IDs",
        skipped,
        len(resolved) - skipped - failed,
        failed,
    )
    return resolved
