"""Ingestion orchestrator — scrape, resolve, and store papers.

Provides the ``run_ingest`` coroutine used by both the CLI ``ingest``
command and the web UI trigger endpoint.
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from src.config import AppConfig
from src.db import (
    create_ingestion_run,
    get_connection,
    insert_snapshot,
    paper_exists,
    record_scraped_date,
    update_ingestion_run,
    upsert_paper,
)
from src.errors import CloudflareTimeoutError, LoginError
from src.ingestion.resolver import ResolvedPaper, resolve_papers
from src.ingestion.scraper import scrape_recommendations

logger = logging.getLogger(__name__)


def _resolved_to_db_dict(paper: ResolvedPaper) -> dict:
    """Convert a ``ResolvedPaper`` to the dict expected by ``upsert_paper``."""
    import json

    return {
        "id": paper.semantic_scholar_id,
        "title": paper.title,
        "authors": json.dumps(paper.authors),
        "abstract": paper.abstract,
        "url": paper.url or paper.scholar_inbox_url,
        "arxiv_id": paper.arxiv_id,
        "doi": paper.doi,
        "venue": paper.venue,
        "year": paper.year,
        "published_date": paper.published_date,
        "scholar_inbox_score": paper.scholar_inbox_score,
        "category": paper.category,
        "citation_count": paper.citation_count,
        "ingested_at": datetime.now().isoformat(),
        "status": "active",
        "manual_status": 0,
    }


async def run_ingest(config: AppConfig) -> dict:
    """Execute a full paper ingestion cycle.

    Steps:
    1. Scrape today's recommendations from Scholar Inbox.
    2. Resolve papers via Semantic Scholar API.
    3. Store new papers and take initial citation snapshots.

    Returns
    -------
    dict
        Summary with keys: papers_found, papers_ingested, run_id.
    """
    with get_connection(config.db_path) as conn:
        run_id = create_ingestion_run(conn)

    try:
        # 1. Scrape
        raw_papers = await scrape_recommendations(config)
        logger.info("Scraped %d papers above threshold", len(raw_papers))

        # 2. Resolve
        async with httpx.AsyncClient() as client:
            resolved = await resolve_papers(client, raw_papers, config)

        # 3. Store
        new_count = 0
        today = datetime.now().strftime("%Y-%m-%d")
        with get_connection(config.db_path) as conn:
            for paper in resolved:
                if not paper_exists(conn, paper.semantic_scholar_id):
                    upsert_paper(conn, _resolved_to_db_dict(paper))
                    if paper.citation_count > 0:
                        insert_snapshot(
                            conn,
                            paper.semantic_scholar_id,
                            paper.citation_count,
                            "semantic_scholar",
                        )
                    new_count += 1

            # Record that today's digest was successfully scraped
            record_scraped_date(conn, today, run_id, len(raw_papers))

            update_ingestion_run(
                conn,
                run_id,
                papers_found=len(raw_papers),
                papers_ingested=new_count,
                status="completed",
            )

        logger.info(
            "Ingestion complete: %d found, %d new", len(raw_papers), new_count
        )
        return {
            "papers_found": len(raw_papers),
            "papers_ingested": new_count,
            "run_id": run_id,
        }

    except CloudflareTimeoutError:
        logger.error(
            "Cloudflare challenge timed out. "
            "Try: scholar-curate reset-session && scholar-curate ingest"
        )
        with get_connection(config.db_path) as conn:
            update_ingestion_run(
                conn, run_id, 0, 0, "failed", "Cloudflare challenge timed out"
            )
        raise
    except LoginError:
        logger.error(
            "Login failed. Verify credentials in .env: "
            "SCHOLAR_INBOX_EMAIL and SCHOLAR_INBOX_PASSWORD"
        )
        with get_connection(config.db_path) as conn:
            update_ingestion_run(conn, run_id, 0, 0, "failed", "Login failed")
        raise
    except Exception as e:
        logger.error("Ingestion failed: %s", e)
        with get_connection(config.db_path) as conn:
            update_ingestion_run(conn, run_id, 0, 0, "failed", str(e))
        raise
