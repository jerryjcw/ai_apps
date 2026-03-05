"""Prune and promote rules for papers.

Evaluates papers against configurable thresholds and updates their status.
Papers with manual_status=1 are never modified by automatic rules.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from src.config import AppConfig
from src.db import update_paper_status

logger = logging.getLogger(__name__)


@dataclass
class RulesResult:
    """Summary of a rules evaluation run."""

    papers_evaluated: int
    papers_pruned: int
    papers_promoted: int
    pruned_ids: list[str]
    promoted_ids: list[str]


def _paper_age_months(paper: dict, now: str) -> float:
    """Return paper age in months, using published_date with fallback to ingested_at."""
    published = paper.get("published_date") or paper["ingested_at"]
    dt_published = datetime.fromisoformat(published)
    dt_now = datetime.fromisoformat(now)
    # Normalize both to UTC-aware to avoid naive vs aware subtraction errors
    if dt_published.tzinfo is None:
        dt_published = dt_published.replace(tzinfo=timezone.utc)
    if dt_now.tzinfo is None:
        dt_now = dt_now.replace(tzinfo=timezone.utc)
    return (dt_now - dt_published).total_seconds() / (30.44 * 86400)


def _should_prune(
    paper: dict,
    now: str,
    min_age_months: int,
    min_citations: int,
    min_velocity: float,
) -> bool:
    """Check if a paper meets all prune criteria.

    A paper is pruned when ALL of:
    - Age since publication (or ingestion) > min_age_months
    - Total citations < min_citations
    - Citation velocity < min_velocity
    """
    age = _paper_age_months(paper, now)
    return (
        age > min_age_months
        and paper["citation_count"] < min_citations
        and paper["citation_velocity"] < min_velocity
    )


def _has_sustained_velocity(
    conn: sqlite3.Connection,
    paper_id: str,
    threshold: float,
) -> bool:
    """Check if velocity has been above threshold for 2+ consecutive snapshots.

    Gets the last 3 snapshots, computes pair-wise velocity between consecutive
    snapshots, returns True if at least 2 of these pair-wise velocities exceed
    the threshold.

    With fewer than 3 snapshots: falls back to requiring >= 2 snapshots
    (paper will be re-evaluated next cycle with more data).
    """
    snapshots = conn.execute(
        "SELECT total_citations, checked_at FROM citation_snapshots "
        "WHERE paper_id = ? ORDER BY checked_at DESC LIMIT 3",
        (paper_id,),
    ).fetchall()

    if len(snapshots) < 3:
        return len(snapshots) >= 2

    velocities_above = 0
    for i in range(len(snapshots) - 1):
        newer = snapshots[i]
        older = snapshots[i + 1]
        days = (
            datetime.fromisoformat(newer["checked_at"])
            - datetime.fromisoformat(older["checked_at"])
        ).days
        if days < 1:
            continue
        velocity = (newer["total_citations"] - older["total_citations"]) / (days / 30.44)
        if velocity >= threshold:
            velocities_above += 1

    return velocities_above >= 2


def _should_promote(
    paper: dict,
    conn: sqlite3.Connection,
    citation_threshold: int,
    velocity_threshold: float,
) -> bool:
    """Check if a paper meets any promote criteria.

    A paper is promoted when ANY of:
    - Total citations >= citation_threshold
    - Citation velocity >= velocity_threshold (sustained over 2+ consecutive snapshots)
    """
    if paper["citation_count"] >= citation_threshold:
        return True

    if paper["citation_velocity"] >= velocity_threshold:
        if _has_sustained_velocity(conn, paper["id"], velocity_threshold):
            return True

    return False


def run_prune_promote(
    conn: sqlite3.Connection,
    config: AppConfig,
    now: str,
) -> RulesResult:
    """Evaluate all eligible papers against prune/promote rules.

    Only papers with status='active' and manual_status=0 are evaluated.
    Promote is evaluated before prune — a paper that qualifies for both
    gets promoted.

    Parameters
    ----------
    conn : sqlite3.Connection
    config : AppConfig
    now : str
        Current time as ISO 8601 string (for deterministic testing).

    Returns
    -------
    RulesResult
        Summary of actions taken.
    """
    rows = conn.execute(
        "SELECT * FROM papers WHERE status = 'active' AND manual_status = 0"
    ).fetchall()
    papers = [dict(r) for r in rows]

    pruned_ids: list[str] = []
    promoted_ids: list[str] = []

    for paper in papers:
        # Promote takes priority over prune
        if _should_promote(
            paper,
            conn,
            config.promotion.citation_threshold,
            config.promotion.velocity_threshold,
        ):
            update_paper_status(conn, paper["id"], "promoted", manual=False)
            promoted_ids.append(paper["id"])
            logger.info(
                "Promoted: %s (citations=%d, velocity=%.1f)",
                paper["title"][:60],
                paper["citation_count"],
                paper["citation_velocity"],
            )
        elif _should_prune(
            paper,
            now,
            config.pruning.min_age_months,
            config.pruning.min_citations,
            config.pruning.min_velocity,
        ):
            update_paper_status(conn, paper["id"], "pruned", manual=False)
            pruned_ids.append(paper["id"])
            logger.info(
                "Pruned: %s (citations=%d, velocity=%.1f, age=%.1f months)",
                paper["title"][:60],
                paper["citation_count"],
                paper["citation_velocity"],
                _paper_age_months(paper, now),
            )

    logger.info(
        "Rules complete: %d evaluated, %d promoted, %d pruned",
        len(papers),
        len(promoted_ids),
        len(pruned_ids),
    )

    return RulesResult(
        papers_evaluated=len(papers),
        papers_pruned=len(pruned_ids),
        papers_promoted=len(promoted_ids),
        pruned_ids=pruned_ids,
        promoted_ids=promoted_ids,
    )


def dry_run_prune_promote(
    conn: sqlite3.Connection,
    config: AppConfig,
    now: str,
) -> RulesResult:
    """Evaluate rules without modifying the database.

    Returns the same RulesResult showing what *would* be pruned/promoted.
    Used by: ``scholar-curate prune --dry-run``
    """
    rows = conn.execute(
        "SELECT * FROM papers WHERE status = 'active' AND manual_status = 0"
    ).fetchall()
    papers = [dict(r) for r in rows]

    pruned_ids: list[str] = []
    promoted_ids: list[str] = []

    for paper in papers:
        if _should_promote(
            paper,
            conn,
            config.promotion.citation_threshold,
            config.promotion.velocity_threshold,
        ):
            promoted_ids.append(paper["id"])
        elif _should_prune(
            paper,
            now,
            config.pruning.min_age_months,
            config.pruning.min_citations,
            config.pruning.min_velocity,
        ):
            pruned_ids.append(paper["id"])

    return RulesResult(
        papers_evaluated=len(papers),
        papers_pruned=len(pruned_ids),
        papers_promoted=len(promoted_ids),
        pruned_ids=pruned_ids,
        promoted_ids=promoted_ids,
    )


def restore_auto_status(conn: sqlite3.Connection, paper_id: str) -> None:
    """Restore a paper to auto-managed status.

    Resets status to 'active' and clears manual_status flag, allowing
    the paper to be re-evaluated by prune/promote rules on the next cycle.

    Parameters
    ----------
    conn : sqlite3.Connection
    paper_id : str
        The paper ID to restore
    """
    conn.execute(
        "UPDATE papers SET status = 'active', manual_status = 0 WHERE id = ?",
        (paper_id,),
    )
    logger.info("Restored paper to auto-managed status: %s", paper_id)
