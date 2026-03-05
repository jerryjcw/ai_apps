"""APScheduler-based cron scheduler for automated ingestion and polling.

Provides ``start_scheduler`` which runs indefinitely, triggering paper
ingestion and citation polling on cron schedules defined in ``config.toml``.
"""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import AppConfig
from src.db import get_connection, now_utc
from src.rules import run_prune_promote

logger = logging.getLogger(__name__)


def _parse_cron(cron_expr: str) -> CronTrigger:
    """Parse a standard 5-field cron expression into an APScheduler CronTrigger.

    Format: minute hour day_of_month month day_of_week
    Example: ``"0 8 * * 1"`` = every Monday at 8:00 AM
    """
    parts = cron_expr.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression (need 5 fields): {cron_expr!r}")

    return CronTrigger(
        minute=parts[0],
        hour=parts[1],
        day=parts[2],
        month=parts[3],
        day_of_week=parts[4],
    )


def _job_ingest(config: AppConfig) -> None:
    """Scheduled job: run paper ingestion."""
    from src.ingestion.orchestrate import run_ingest

    logger.info("Scheduled ingestion starting")
    try:
        asyncio.run(run_ingest(config))
        logger.info("Scheduled ingestion completed")
    except Exception as e:
        logger.error("Scheduled ingestion failed: %s", e)


def _job_poll_citations(config: AppConfig) -> None:
    """Scheduled job: run citation polling + prune/promote rules."""
    from src.citations.poller import run_citation_poll

    logger.info("Scheduled citation poll starting")
    try:
        asyncio.run(run_citation_poll(config, config.db_path))
        # Run rules after polling
        with get_connection(config.db_path) as conn:
            result = run_prune_promote(conn, config, now_utc())
            logger.info(
                "Rules: pruned=%d, promoted=%d",
                result.papers_pruned,
                result.papers_promoted,
            )
        logger.info("Scheduled citation poll completed")
    except Exception as e:
        logger.error("Scheduled citation poll failed: %s", e)


def start_scheduler(config: AppConfig) -> None:
    """Start the blocking scheduler with configured cron jobs.

    Runs indefinitely until interrupted (Ctrl+C).
    """
    scheduler = BlockingScheduler()

    ingest_cron = _parse_cron(config.ingestion.schedule_cron)
    poll_cron = _parse_cron(config.citations.poll_schedule_cron)

    scheduler.add_job(
        _job_ingest,
        trigger=ingest_cron,
        args=[config],
        id="ingest",
        name="Paper Ingestion",
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        _job_poll_citations,
        trigger=poll_cron,
        args=[config],
        id="poll_citations",
        name="Citation Polling",
        misfire_grace_time=3600,
    )

    logger.info(
        "Scheduler started. Ingestion: %s, Polling: %s",
        config.ingestion.schedule_cron,
        config.citations.poll_schedule_cron,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
        scheduler.shutdown()
