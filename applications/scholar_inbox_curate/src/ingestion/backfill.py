"""Backfill mechanism — scrape missing digest dates.

Identifies dates within a lookback window that haven't been scraped yet
and fetches papers for each, recording results in the database.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from src.config import AppConfig
from src.db import (
    find_missing_dates,
    get_connection,
    record_scraped_date,
    reset_resolve_failures,
    upsert_paper,
    create_ingestion_run,
    update_ingestion_run,
    now_utc,
)
from src.ingestion.scraper import RawPaper, scrape_date

logger = logging.getLogger(__name__)


@dataclass
class BackfillResult:
    """Summary of a backfill run."""

    dates_checked: int = 0
    dates_scraped: int = 0
    total_papers_found: int = 0
    total_papers_ingested: int = 0
    papers_re_resolved: int = 0
    errors: list[str] = field(default_factory=list)


def _raw_paper_to_db_dict(paper: RawPaper, digest_date_iso: str) -> dict:
    """Convert a RawPaper to the dict expected by ``upsert_paper``."""
    paper_id = paper.semantic_scholar_id or paper.arxiv_id or f"si-{paper.paper_id}"
    return {
        "id": paper_id,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "url": paper.scholar_inbox_url,
        "arxiv_id": paper.arxiv_id,
        "venue": paper.venue,
        "year": paper.year,
        "published_date": paper.publication_date,
        "scholar_inbox_score": paper.score,
        "category": paper.category,
        "ingested_at": now_utc(),
    }


def _date_to_api_format(d: date) -> str:
    """Convert a ``date`` to the API's ``MM-DD-YYYY`` format."""
    return d.strftime("%m-%d-%Y")


async def run_backfill(
    config: AppConfig,
    lookback_days: int | None = None,
    score_threshold: float | None = None,
) -> BackfillResult:
    """Backfill missing digest dates.

    Parameters
    ----------
    config : AppConfig
        Application configuration.
    lookback_days : int, optional
        Override the lookback window. Defaults to ``config.ingestion.backfill_lookback_days``.
    score_threshold : float, optional
        Override the score threshold (0.0-1.0). Defaults to ``config.ingestion.backfill_score_threshold``.

    Returns
    -------
    BackfillResult
        Summary of the backfill run.
    """
    if lookback_days is None:
        lookback_days = config.ingestion.backfill_lookback_days
    if score_threshold is None:
        score_threshold = config.ingestion.backfill_score_threshold

    result = BackfillResult()

    with get_connection(config.db_path) as conn:
        missing = find_missing_dates(conn, lookback_days)

    result.dates_checked = len(missing)

    if not missing:
        logger.info("Backfill: no missing dates found in the last %d days", lookback_days)
        return result

    logger.info("Backfill: %d missing dates to scrape", len(missing))

    for iso_date in missing:
        d = date.fromisoformat(iso_date)
        api_date = _date_to_api_format(d)

        try:
            papers = await scrape_date(config, api_date, score_threshold)
        except Exception as exc:
            error_msg = f"{iso_date}: {exc}"
            logger.error("Backfill error for %s: %s", iso_date, exc)
            result.errors.append(error_msg)
            continue

        result.dates_scraped += 1
        result.total_papers_found += len(papers)

        with get_connection(config.db_path) as conn:
            run_id = create_ingestion_run(conn)
            ingested = 0
            for paper in papers:
                db_dict = _raw_paper_to_db_dict(paper, iso_date)
                was_new = upsert_paper(conn, db_dict)
                if was_new:
                    ingested += 1

            update_ingestion_run(
                conn,
                run_id,
                papers_found=len(papers),
                papers_ingested=ingested,
                status="completed",
            )
            record_scraped_date(conn, iso_date, run_id=run_id, papers_found=len(papers))

        result.total_papers_ingested += ingested
        logger.info(
            "Backfill %s: %d found, %d new",
            iso_date,
            len(papers),
            ingested,
        )

    # Reset failure counters so every paper gets fresh attempts this cycle.
    with get_connection(config.db_path) as conn:
        reset_resolve_failures(conn)

    # Re-resolve any dangling papers (title: or si- prefix IDs) that
    # failed S2 resolution on previous runs due to HTTP errors.
    from src.ingestion.reresolver import re_resolve_dangling

    re_result = await re_resolve_dangling(config)
    result.papers_re_resolved = re_result.resolved + re_result.already_exists
    result.errors.extend(re_result.errors)

    return result
