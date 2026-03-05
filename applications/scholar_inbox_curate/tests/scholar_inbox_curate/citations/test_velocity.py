"""Tests for src.citations.velocity."""

from __future__ import annotations

import pytest

from src.citations.velocity import compute_velocity, update_velocities_bulk
from src.db import init_db_on_conn, now_utc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_paper(conn, paper_id="paper1"):
    """Insert a minimal paper row for FK references."""
    conn.execute(
        "INSERT INTO papers (id, title, authors, ingested_at) VALUES (?, ?, ?, ?)",
        (paper_id, "Test Paper", "[]", "2024-01-01T00:00:00+00:00"),
    )


def _insert_snapshot(conn, paper_id, checked_at, total_citations):
    """Insert a citation snapshot."""
    conn.execute(
        "INSERT INTO citation_snapshots (paper_id, checked_at, total_citations, source) "
        "VALUES (?, ?, ?, 'semantic_scholar')",
        (paper_id, checked_at, total_citations),
    )


# ---------------------------------------------------------------------------
# compute_velocity
# ---------------------------------------------------------------------------

class TestComputeVelocity:
    def test_standard_case_3_months(self, db_conn):
        """3+ months of snapshot data → normal velocity."""
        _insert_paper(db_conn)
        _insert_snapshot(db_conn, "paper1", "2024-01-15T00:00:00+00:00", 10)
        _insert_snapshot(db_conn, "paper1", "2024-04-15T00:00:00+00:00", 40)

        now = "2024-04-15T00:00:00+00:00"
        vel = compute_velocity(db_conn, "paper1", now)
        # ~3 months elapsed, 30 citation diff
        assert vel > 0.0
        assert abs(vel - (30 / (91 / 30.44))) < 0.5  # approximately 10/month

    def test_short_history_with_two_snapshots(self, db_conn):
        """< 3 months but >= 2 snapshots and >= 7 days → fallback velocity."""
        _insert_paper(db_conn)
        _insert_snapshot(db_conn, "paper1", "2024-04-01T00:00:00+00:00", 5)
        _insert_snapshot(db_conn, "paper1", "2024-04-20T00:00:00+00:00", 15)

        now = "2024-04-20T00:00:00+00:00"
        vel = compute_velocity(db_conn, "paper1", now)
        assert vel > 0.0

    def test_single_snapshot_returns_zero(self, db_conn):
        """Only one snapshot → 0.0 (same snapshot used for latest and old)."""
        _insert_paper(db_conn)
        _insert_snapshot(db_conn, "paper1", "2024-04-01T00:00:00+00:00", 10)

        now = "2024-04-15T00:00:00+00:00"
        vel = compute_velocity(db_conn, "paper1", now)
        assert vel == 0.0

    def test_no_snapshots_returns_zero(self, db_conn):
        _insert_paper(db_conn)
        vel = compute_velocity(db_conn, "paper1", "2024-04-15T00:00:00+00:00")
        assert vel == 0.0

    def test_less_than_7_days_returns_zero(self, db_conn):
        """< 7 days elapsed → 0.0."""
        _insert_paper(db_conn)
        _insert_snapshot(db_conn, "paper1", "2024-04-10T00:00:00+00:00", 5)
        _insert_snapshot(db_conn, "paper1", "2024-04-13T00:00:00+00:00", 10)

        now = "2024-04-13T00:00:00+00:00"
        vel = compute_velocity(db_conn, "paper1", now)
        assert vel == 0.0

    def test_negative_diff_returns_zero(self, db_conn):
        """Citation count decreased → 0.0 (clamped)."""
        _insert_paper(db_conn)
        _insert_snapshot(db_conn, "paper1", "2024-01-01T00:00:00+00:00", 100)
        _insert_snapshot(db_conn, "paper1", "2024-04-01T00:00:00+00:00", 80)

        now = "2024-04-01T00:00:00+00:00"
        vel = compute_velocity(db_conn, "paper1", now)
        assert vel == 0.0

    def test_nonexistent_paper_returns_zero(self, db_conn):
        vel = compute_velocity(db_conn, "nonexistent", "2024-04-15T00:00:00+00:00")
        assert vel == 0.0


# ---------------------------------------------------------------------------
# update_velocities_bulk
# ---------------------------------------------------------------------------

class TestUpdateVelocitiesBulk:
    def test_updates_multiple_papers(self, db_conn):
        _insert_paper(db_conn, "p1")
        _insert_paper(db_conn, "p2")

        _insert_snapshot(db_conn, "p1", "2024-01-01T00:00:00+00:00", 10)
        _insert_snapshot(db_conn, "p1", "2024-04-01T00:00:00+00:00", 40)

        _insert_snapshot(db_conn, "p2", "2024-01-01T00:00:00+00:00", 5)
        _insert_snapshot(db_conn, "p2", "2024-04-01T00:00:00+00:00", 5)

        now = "2024-04-01T00:00:00+00:00"
        update_velocities_bulk(db_conn, ["p1", "p2"], now)

        p1 = db_conn.execute(
            "SELECT citation_velocity FROM papers WHERE id = 'p1'"
        ).fetchone()
        p2 = db_conn.execute(
            "SELECT citation_velocity FROM papers WHERE id = 'p2'"
        ).fetchone()

        assert p1["citation_velocity"] > 0.0
        assert p2["citation_velocity"] == 0.0
