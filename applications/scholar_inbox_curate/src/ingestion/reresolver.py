"""Re-resolution of dangling papers with synthetic/fallback IDs.

Papers stored with ``title:{hash}`` or ``si-{paper_id}`` IDs could not be
resolved via Semantic Scholar at ingestion time (e.g. due to temporary API
outages).  This module finds them and re-attempts resolution so they can
participate in citation polling.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

from src.config import AppConfig
from src.constants import MAX_RESOLVE_FAILURES
from src.db import (
    get_connection,
    get_dangling_papers,
    increment_resolve_failures,
    replace_paper_id,
)
from src.ingestion.resolver import ResolvedPaper, resolve_paper
from src.ingestion.scraper import RawPaper

logger = logging.getLogger(__name__)


@dataclass
class ReResolveResult:
    """Summary of a re-resolution run."""

    total_dangling: int = 0
    resolved: int = 0
    already_exists: int = 0
    still_unresolved: int = 0
    skipped_max_failures: int = 0
    errors: list[str] = field(default_factory=list)


def _paper_dict_to_raw(paper: dict) -> RawPaper:
    """Reconstruct a ``RawPaper`` from a DB row dict for re-resolution."""
    authors = paper.get("authors") or "[]"
    if isinstance(authors, str):
        try:
            authors = json.loads(authors)
        except json.JSONDecodeError:
            authors = [a.strip() for a in authors.split(",") if a.strip()]

    return RawPaper(
        title=paper["title"],
        authors=authors,
        abstract=paper.get("abstract") or "",
        score=paper.get("scholar_inbox_score") or 0.0,
        arxiv_id=paper.get("arxiv_id"),
        semantic_scholar_id=None,  # Force re-resolution
        paper_id=None,
        venue=paper.get("venue"),
        year=paper.get("year"),
        category=paper.get("category"),
        scholar_inbox_url=paper.get("url"),
        publication_date=paper.get("published_date"),
    )


def _resolved_to_update_fields(resolved: ResolvedPaper) -> dict:
    """Extract fields to update from a ``ResolvedPaper``."""
    return {
        "title": resolved.title,
        "authors": json.dumps(resolved.authors),
        "abstract": resolved.abstract,
        "url": resolved.url,
        "arxiv_id": resolved.arxiv_id,
        "doi": resolved.doi,
        "venue": resolved.venue,
        "year": resolved.year,
        "published_date": resolved.published_date,
        "citation_count": resolved.citation_count,
    }


async def re_resolve_dangling(config: AppConfig) -> ReResolveResult:
    """Find and re-resolve papers with synthetic/fallback IDs.

    Queries the DB for papers whose ``id`` starts with ``title:`` or ``si-``,
    re-attempts Semantic Scholar resolution, and replaces the ID on success.

    Papers that have failed ``MAX_RESOLVE_FAILURES`` consecutive times are
    skipped.  On each failure the counter is incremented; on success the old
    row is deleted (counter resets naturally).  The backfill command resets
    all counters at the start of each cycle.
    """
    result = ReResolveResult()

    with get_connection(config.db_path) as conn:
        dangling = get_dangling_papers(conn, max_failures=MAX_RESOLVE_FAILURES)
        # Count papers that were skipped due to max failures
        all_dangling = conn.execute(
            "SELECT COUNT(*) as cnt FROM papers "
            "WHERE id LIKE 'title:%' OR id LIKE 'si-%'"
        ).fetchone()["cnt"]

    result.total_dangling = all_dangling
    result.skipped_max_failures = all_dangling - len(dangling)

    if not dangling:
        if result.skipped_max_failures > 0:
            logger.info(
                "No eligible dangling papers (%d skipped due to max failures)",
                result.skipped_max_failures,
            )
        else:
            logger.info("No dangling papers found")
        return result

    logger.info(
        "Found %d dangling papers to re-resolve (%d skipped due to max failures)",
        len(dangling),
        result.skipped_max_failures,
    )

    async with httpx.AsyncClient() as client:
        for paper in dangling:
            old_id = paper["id"]
            raw = _paper_dict_to_raw(paper)

            try:
                resolved = await resolve_paper(client, raw, config)
            except Exception as exc:
                result.errors.append(f"{old_id}: {exc}")
                with get_connection(config.db_path) as conn:
                    increment_resolve_failures(conn, old_id)
                continue

            if resolved is None:
                result.still_unresolved += 1
                with get_connection(config.db_path) as conn:
                    increment_resolve_failures(conn, old_id)
                continue

            new_id = resolved.semantic_scholar_id
            # Skip if resolution returned another synthetic ID
            if new_id.startswith("title:") or new_id.startswith("si-"):
                result.still_unresolved += 1
                with get_connection(config.db_path) as conn:
                    increment_resolve_failures(conn, old_id)
                continue

            with get_connection(config.db_path) as conn:
                updated_fields = _resolved_to_update_fields(resolved)
                replaced = replace_paper_id(conn, old_id, new_id, updated_fields)

                if replaced:
                    result.resolved += 1
                    logger.info("Re-resolved %s -> %s", old_id, new_id)
                else:
                    result.already_exists += 1
                    logger.info(
                        "Duplicate removed %s (already have %s)", old_id, new_id
                    )

    logger.info(
        "Re-resolution complete: %d resolved, %d duplicates removed, "
        "%d still unresolved, %d skipped (max failures)",
        result.resolved,
        result.already_exists,
        result.still_unresolved,
        result.skipped_max_failures,
    )
    return result
