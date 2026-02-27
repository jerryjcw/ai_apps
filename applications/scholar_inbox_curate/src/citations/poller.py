"""Citation polling orchestrator.

Coordinates the full citation-update cycle: fetching counts from Semantic
Scholar, optionally enriching with OpenAlex yearly breakdowns, computing
velocity, and persisting results.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from src import db
from src.citations import semantic_scholar, openalex, velocity
from src.config import AppConfig

logger = logging.getLogger(__name__)

# OpenAlex is checked at most once per month per paper.
_OPENALEX_INTERVAL_DAYS = 30


def _should_fetch_openalex(paper: dict, now: datetime) -> bool:
    """Return True if the paper is due for an OpenAlex refresh.

    OpenAlex is queried at most monthly.  A paper qualifies if it has never
    been checked or its last check was 30+ days ago.
    """
    last_check = paper.get("last_cited_check")
    if last_check is None:
        return True
    try:
        last_dt = datetime.fromisoformat(last_check)
        return (now - last_dt) >= timedelta(days=_OPENALEX_INTERVAL_DAYS)
    except (ValueError, TypeError):
        return True


async def run_citation_poll(config: AppConfig, db_path: str) -> int:
    """Run one full citation polling cycle.

    Returns the number of papers processed.
    """
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    with db.get_connection(db_path) as conn:
        papers = db.get_papers_due_for_poll(conn, now_iso)

    if not papers:
        logger.info("No papers due for citation polling")
        return 0

    logger.info("Polling citations for %d papers", len(papers))

    paper_ids = [p["id"] for p in papers]

    # ------------------------------------------------------------------
    # Step 1: Fetch citation counts from Semantic Scholar
    # ------------------------------------------------------------------
    async with httpx.AsyncClient() as client:
        s2_counts = await semantic_scholar.fetch_citations_batch(
            client,
            paper_ids,
            api_key=config.secrets.semantic_scholar_api_key or None,
            batch_size=config.citations.semantic_scholar_batch_size,
        )

        # ----------------------------------------------------------
        # Step 2: Record snapshots, compute velocity, update papers
        # ----------------------------------------------------------
        with db.get_connection(db_path) as conn:
            for paper in papers:
                pid = paper["id"]
                count = s2_counts.get(pid)
                if count is not None:
                    db.insert_snapshot(conn, pid, count, "semantic_scholar")

            # Recompute velocity for all papers that got new counts
            updated_ids = [pid for pid in paper_ids if pid in s2_counts]
            velocity.update_velocities_bulk(conn, updated_ids, now_iso)

            for pid in updated_ids:
                vel = velocity.compute_velocity(conn, pid, now_iso)
                db.update_paper_citations(conn, pid, s2_counts[pid], vel)

        # ----------------------------------------------------------
        # Step 3: OpenAlex yearly breakdown (monthly cycle)
        # ----------------------------------------------------------
        openalex_due = [
            p for p in papers if _should_fetch_openalex(p, now_dt)
        ]
        if openalex_due:
            logger.info(
                "Fetching OpenAlex data for %d papers", len(openalex_due)
            )
            email = config.secrets.scholar_inbox_email or None

            with db.get_connection(db_path) as conn:
                for paper in openalex_due:
                    pid = paper["id"]
                    # Extract DOI from paper ID if available
                    doi = None
                    if pid.startswith("doi:"):
                        doi = pid[len("doi:"):]
                    elif paper.get("arxiv_id"):
                        doi = None  # arXiv papers may not have DOI in ID

                    result = await openalex.fetch_yearly_citations(
                        client, doi, paper.get("title"), email
                    )
                    if result:
                        db.insert_snapshot(
                            conn,
                            pid,
                            result["total"],
                            "openalex",
                            yearly_breakdown=result["by_year"],
                        )

        # ----------------------------------------------------------
        # Step 4: Update last_cited_check for all polled papers
        # ----------------------------------------------------------
        with db.get_connection(db_path) as conn:
            for paper in papers:
                conn.execute(
                    "UPDATE papers SET last_cited_check = ? WHERE id = ?",
                    (now_iso, paper["id"]),
                )

    logger.info("Citation poll complete: %d papers processed", len(papers))
    return len(papers)
