"""Semantic Scholar batch citation fetching.

Fetches updated citation counts for tracked papers using the S2 batch
endpoint.  Handles rate limiting, 429 retries, and 5xx errors gracefully.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from src.constants import (
    S2_BATCH_DELAY_NO_KEY,
    S2_BATCH_DELAY_WITH_KEY,
    S2_BATCH_FIELDS,
    S2_BATCH_URL,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_s2_id(paper_id: str) -> str | None:
    """Convert an internal paper ID to a Semantic Scholar API identifier.

    Mappings:
    - ``arxiv:X``  → ``ARXIV:X``
    - ``doi:X``    → ``DOI:X``
    - ``title:X``  → ``None`` (not resolvable via batch)
    - anything else → passed through as-is (assumed S2 paperId)
    """
    if paper_id.startswith("arxiv:"):
        return "ARXIV:" + paper_id[len("arxiv:"):]
    if paper_id.startswith("doi:"):
        return "DOI:" + paper_id[len("doi:"):]
    if paper_id.startswith("title:"):
        return None
    return paper_id


def _get_headers(api_key: str | None) -> dict:
    """Build request headers with optional API key."""
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key
    return headers


# ---------------------------------------------------------------------------
# Low-level batch fetch
# ---------------------------------------------------------------------------

async def _fetch_batch(
    client: httpx.AsyncClient,
    ids: list[str],
    headers: dict,
) -> list[dict | None]:
    """POST to the S2 batch endpoint and return the response list.

    Each element is either a dict with paper data or ``None`` if the paper
    was not found.
    """
    resp = await client.post(
        S2_BATCH_URL,
        headers=headers,
        params={"fields": S2_BATCH_FIELDS},
        json={"ids": ids},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_citations_batch(
    client: httpx.AsyncClient,
    paper_ids: list[str],
    api_key: str | None = None,
    batch_size: int = 100,
) -> dict[str, int]:
    """Fetch citation counts for a list of paper IDs.

    Parameters
    ----------
    client : httpx.AsyncClient
    paper_ids : list[str]
        Internal paper IDs (``arxiv:``, ``doi:``, S2 hash, etc.).
    api_key : str | None
        Optional Semantic Scholar API key for higher rate limits.
    batch_size : int
        Maximum IDs per batch request (S2 limit is 500).

    Returns
    -------
    dict[str, int]
        Mapping of *original* paper_id → citation count.  Papers that
        could not be resolved are omitted from the result.
    """
    headers = _get_headers(api_key)
    delay = S2_BATCH_DELAY_WITH_KEY if api_key else S2_BATCH_DELAY_NO_KEY

    # Build mapping: s2_id -> original_id (skip title: papers)
    id_pairs: list[tuple[str, str]] = []
    for pid in paper_ids:
        s2_id = _to_s2_id(pid)
        if s2_id is not None:
            id_pairs.append((s2_id, pid))

    results: dict[str, int] = {}

    for start in range(0, len(id_pairs), batch_size):
        chunk = id_pairs[start : start + batch_size]
        s2_ids = [pair[0] for pair in chunk]

        if start > 0:
            await asyncio.sleep(delay)

        try:
            batch_results = await _try_fetch_batch(client, s2_ids, headers, delay)
        except Exception as exc:
            logger.error("Batch fetch failed: %s", exc)
            continue

        for (s2_id, orig_id), entry in zip(chunk, batch_results):
            if entry is not None and "citationCount" in entry:
                results[orig_id] = entry["citationCount"]

    return results


async def _try_fetch_batch(
    client: httpx.AsyncClient,
    s2_ids: list[str],
    headers: dict,
    delay: float,
) -> list[dict | None]:
    """Attempt a batch fetch with retry logic for 429 and 5xx errors."""
    try:
        return await _fetch_batch(client, s2_ids, headers)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 429:
            retry_after = int(exc.response.headers.get("Retry-After", "5"))
            logger.warning("Rate limited (429), retrying in %ds", retry_after)
            await asyncio.sleep(retry_after)
            return await _fetch_batch(client, s2_ids, headers)
        if 500 <= status < 600:
            logger.warning("Server error %d, retrying once after %gs", status, delay)
            await asyncio.sleep(delay)
            try:
                return await _fetch_batch(client, s2_ids, headers)
            except Exception:
                logger.error("Retry failed for 5xx, skipping batch")
                return [None] * len(s2_ids)
        raise
    except httpx.TimeoutException:
        logger.warning("Batch request timed out, skipping batch")
        return [None] * len(s2_ids)
