"""Citation velocity computation.

Computes a rolling 3-month citation velocity (citations per month) for
papers, falling back to the earliest available snapshot when history is
shorter than 3 months.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime

from src.constants import VELOCITY_MIN_DAYS

logger = logging.getLogger(__name__)


def compute_velocity(
    conn: sqlite3.Connection,
    paper_id: str,
    now: str,
) -> float:
    """Compute citation velocity for a single paper.

    Algorithm (from design doc 05):
    1. Get the latest snapshot and the snapshot closest to 3 months ago.
    2. If < 3 months of data, fall back to the earliest snapshot.
    3. If < 2 snapshots or < 7 days elapsed, return 0.0.
    4. velocity = (latest_count - old_count) / months_elapsed
    5. Clamp negative values to 0.0.

    Parameters
    ----------
    conn : sqlite3.Connection
    paper_id : str
    now : str
        Current time as ISO 8601 string (for deterministic testing).

    Returns
    -------
    float
        Citation velocity (citations per month), clamped >= 0.0.
    """
    # Get latest snapshot
    latest = conn.execute(
        "SELECT total_citations, checked_at FROM citation_snapshots "
        "WHERE paper_id = ? ORDER BY checked_at DESC LIMIT 1",
        (paper_id,),
    ).fetchone()

    if latest is None:
        return 0.0

    latest_count = latest["total_citations"]
    latest_date = latest["checked_at"]

    # Try to get snapshot closest to 3 months ago
    old = conn.execute(
        "SELECT total_citations, checked_at FROM citation_snapshots "
        "WHERE paper_id = ? AND checked_at <= datetime(?, '-3 months') "
        "ORDER BY checked_at DESC LIMIT 1",
        (paper_id, now),
    ).fetchone()

    if old is None:
        # Fall back to earliest snapshot
        old = conn.execute(
            "SELECT total_citations, checked_at FROM citation_snapshots "
            "WHERE paper_id = ? ORDER BY checked_at ASC LIMIT 1",
            (paper_id,),
        ).fetchone()

    if old is None:
        return 0.0

    old_count = old["total_citations"]
    old_date = old["checked_at"]

    # Same snapshot — need at least 2 distinct snapshots
    if old_date == latest_date:
        return 0.0

    # Compute elapsed days
    dt_latest = datetime.fromisoformat(latest_date)
    dt_old = datetime.fromisoformat(old_date)
    elapsed_days = (dt_latest - dt_old).total_seconds() / 86400.0

    if elapsed_days < VELOCITY_MIN_DAYS:
        return 0.0

    months_elapsed = elapsed_days / 30.44  # average days per month
    diff = latest_count - old_count

    if diff <= 0:
        return 0.0

    return diff / months_elapsed


def update_velocities_bulk(
    conn: sqlite3.Connection,
    paper_ids: list[str],
    now: str,
) -> None:
    """Recompute and update velocity for a batch of papers.

    Parameters
    ----------
    conn : sqlite3.Connection
    paper_ids : list[str]
    now : str
        Current time as ISO 8601 string.
    """
    for paper_id in paper_ids:
        velocity = compute_velocity(conn, paper_id, now)
        conn.execute(
            "UPDATE papers SET citation_velocity = ? WHERE id = ?",
            (velocity, paper_id),
        )
