"""Tests for src.rules — prune/promote logic."""

from __future__ import annotations

import pytest

from src.config import AppConfig, PruningConfig, PromotionConfig
from src.rules import (
    RulesResult,
    run_prune_promote,
    dry_run_prune_promote,
    _should_prune,
    _should_promote,
    _has_sustained_velocity,
    _paper_age_months,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_paper(
    conn,
    paper_id="p1",
    ingested_at="2024-01-01T00:00:00+00:00",
    published_date=None,
    citation_count=0,
    citation_velocity=0.0,
    status="active",
    manual_status=0,
):
    conn.execute(
        "INSERT INTO papers "
        "(id, title, authors, ingested_at, published_date, citation_count, "
        "citation_velocity, status, manual_status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (paper_id, f"Paper {paper_id}", "[]", ingested_at, published_date,
         citation_count, citation_velocity, status, manual_status),
    )


def _insert_snapshot(conn, paper_id, checked_at, total_citations):
    conn.execute(
        "INSERT INTO citation_snapshots (paper_id, checked_at, total_citations, source) "
        "VALUES (?, ?, ?, 'semantic_scholar')",
        (paper_id, checked_at, total_citations),
    )


def _get_status(conn, paper_id):
    row = conn.execute(
        "SELECT status FROM papers WHERE id = ?", (paper_id,)
    ).fetchone()
    return row["status"]


def _make_config(**overrides) -> AppConfig:
    """Build an AppConfig with optional pruning/promotion overrides."""
    pruning_kw = {}
    promotion_kw = {}
    for k, v in overrides.items():
        if k.startswith("prune_"):
            pruning_kw[k.removeprefix("prune_")] = v
        elif k.startswith("promote_"):
            promotion_kw[k.removeprefix("promote_")] = v

    return AppConfig(
        pruning=PruningConfig(**pruning_kw) if pruning_kw else PruningConfig(),
        promotion=PromotionConfig(**promotion_kw) if promotion_kw else PromotionConfig(),
    )


# ---------------------------------------------------------------------------
# _paper_age_months
# ---------------------------------------------------------------------------

class TestPaperAgeMonths:
    """Tests for age computation with published_date fallback."""

    def test_uses_published_date_when_available(self):
        paper = {
            "published_date": "2024-06-01T00:00:00+00:00",
            "ingested_at": "2024-07-01T00:00:00+00:00",
        }
        age = _paper_age_months(paper, "2025-01-01T00:00:00+00:00")
        # ~7 months from published_date, not ~6 from ingested_at
        assert age > 6.5

    def test_falls_back_to_ingested_at(self):
        paper = {
            "published_date": None,
            "ingested_at": "2024-07-01T00:00:00+00:00",
        }
        age = _paper_age_months(paper, "2025-01-01T00:00:00+00:00")
        assert 5.5 < age < 6.5

    def test_missing_published_date_key(self):
        paper = {"ingested_at": "2024-07-01T00:00:00+00:00"}
        age = _paper_age_months(paper, "2025-01-01T00:00:00+00:00")
        assert 5.5 < age < 6.5


# ---------------------------------------------------------------------------
# _should_prune
# ---------------------------------------------------------------------------

class TestShouldPrune:
    """Unit tests for the prune predicate."""

    NOW = "2025-01-01T00:00:00+00:00"

    def test_old_low_citations_low_velocity_pruned(self):
        paper = {
            "ingested_at": "2024-01-01T00:00:00+00:00",
            "published_date": None,
            "citation_count": 3,
            "citation_velocity": 0.5,
        }
        assert _should_prune(paper, self.NOW, 6, 10, 1.0) is True

    def test_too_young_not_pruned(self):
        paper = {
            "ingested_at": "2024-09-01T00:00:00+00:00",
            "published_date": None,
            "citation_count": 0,
            "citation_velocity": 0.0,
        }
        assert _should_prune(paper, self.NOW, 6, 10, 1.0) is False

    def test_enough_citations_not_pruned(self):
        paper = {
            "ingested_at": "2024-01-01T00:00:00+00:00",
            "published_date": None,
            "citation_count": 15,
            "citation_velocity": 0.5,
        }
        assert _should_prune(paper, self.NOW, 6, 10, 1.0) is False

    def test_enough_velocity_not_pruned(self):
        paper = {
            "ingested_at": "2024-01-01T00:00:00+00:00",
            "published_date": None,
            "citation_count": 3,
            "citation_velocity": 2.0,
        }
        assert _should_prune(paper, self.NOW, 6, 10, 1.0) is False

    def test_boundary_age_exactly_6_months_not_pruned(self):
        """Age must be strictly > min_age_months."""
        # 6 months = 6 * 30.44 = 182.64 days. 182 days back from NOW is just under.
        paper = {
            "ingested_at": "2024-07-03T00:00:00+00:00",  # 182 days before 2025-01-01
            "published_date": None,
            "citation_count": 0,
            "citation_velocity": 0.0,
        }
        assert _should_prune(paper, self.NOW, 6, 10, 1.0) is False

    def test_boundary_citations_exactly_min_not_pruned(self):
        """Citations must be strictly < min_citations."""
        paper = {
            "ingested_at": "2024-01-01T00:00:00+00:00",
            "published_date": None,
            "citation_count": 10,
            "citation_velocity": 0.5,
        }
        assert _should_prune(paper, self.NOW, 6, 10, 1.0) is False

    def test_boundary_velocity_exactly_min_not_pruned(self):
        """Velocity must be strictly < min_velocity."""
        paper = {
            "ingested_at": "2024-01-01T00:00:00+00:00",
            "published_date": None,
            "citation_count": 3,
            "citation_velocity": 1.0,
        }
        assert _should_prune(paper, self.NOW, 6, 10, 1.0) is False

    def test_published_date_used_for_age(self):
        """Prune age should use published_date, not ingested_at."""
        paper = {
            "published_date": "2024-01-01T00:00:00+00:00",  # > 6 months old
            "ingested_at": "2024-10-01T00:00:00+00:00",      # < 6 months old
            "citation_count": 0,
            "citation_velocity": 0.0,
        }
        assert _should_prune(paper, self.NOW, 6, 10, 1.0) is True


# ---------------------------------------------------------------------------
# _has_sustained_velocity
# ---------------------------------------------------------------------------

class TestHasSustainedVelocity:
    """Tests for the sustained velocity check."""

    def test_three_snapshots_two_high_velocity_pairs(self, db_conn):
        """3 snapshots with both pair-wise velocities above threshold."""
        _insert_paper(db_conn, "p1")
        _insert_snapshot(db_conn, "p1", "2024-01-01T00:00:00+00:00", 0)
        _insert_snapshot(db_conn, "p1", "2024-02-01T00:00:00+00:00", 30)
        _insert_snapshot(db_conn, "p1", "2024-03-01T00:00:00+00:00", 60)
        assert _has_sustained_velocity(db_conn, "p1", 10.0) is True

    def test_three_snapshots_one_high_pair(self, db_conn):
        """3 snapshots but only 1 pair exceeds threshold — not sustained."""
        _insert_paper(db_conn, "p1")
        _insert_snapshot(db_conn, "p1", "2024-01-01T00:00:00+00:00", 0)
        _insert_snapshot(db_conn, "p1", "2024-02-01T00:00:00+00:00", 1)   # low velocity
        _insert_snapshot(db_conn, "p1", "2024-03-01T00:00:00+00:00", 40)  # spike
        assert _has_sustained_velocity(db_conn, "p1", 10.0) is False

    def test_two_snapshots_fallback_true(self, db_conn):
        """With only 2 snapshots, falls back to True (re-evaluate next cycle)."""
        _insert_paper(db_conn, "p1")
        _insert_snapshot(db_conn, "p1", "2024-01-01T00:00:00+00:00", 0)
        _insert_snapshot(db_conn, "p1", "2024-02-01T00:00:00+00:00", 30)
        assert _has_sustained_velocity(db_conn, "p1", 10.0) is True

    def test_one_snapshot_returns_false(self, db_conn):
        _insert_paper(db_conn, "p1")
        _insert_snapshot(db_conn, "p1", "2024-01-01T00:00:00+00:00", 10)
        assert _has_sustained_velocity(db_conn, "p1", 10.0) is False

    def test_zero_snapshots_returns_false(self, db_conn):
        _insert_paper(db_conn, "p1")
        assert _has_sustained_velocity(db_conn, "p1", 10.0) is False

    def test_same_day_snapshots_skipped(self, db_conn):
        """Pairs with < 1 day difference are skipped."""
        _insert_paper(db_conn, "p1")
        _insert_snapshot(db_conn, "p1", "2024-01-01T00:00:00+00:00", 0)
        _insert_snapshot(db_conn, "p1", "2024-01-01T12:00:00+00:00", 5)
        _insert_snapshot(db_conn, "p1", "2024-02-01T00:00:00+00:00", 40)
        # Only 1 valid pair (Jan 1 12:00 → Feb 1), so < 2 → False
        assert _has_sustained_velocity(db_conn, "p1", 10.0) is False


# ---------------------------------------------------------------------------
# _should_promote
# ---------------------------------------------------------------------------

class TestShouldPromote:
    """Unit tests for the promote predicate."""

    def test_high_citations_promoted(self, db_conn):
        _insert_paper(db_conn, "p1", citation_count=60)
        paper = dict(db_conn.execute("SELECT * FROM papers WHERE id = 'p1'").fetchone())
        assert _should_promote(paper, db_conn, 50, 10.0) is True

    def test_high_velocity_sustained_promoted(self, db_conn):
        """High velocity with 3 snapshots showing sustained high velocity."""
        _insert_paper(db_conn, "p1", citation_velocity=12.0)
        _insert_snapshot(db_conn, "p1", "2024-01-01T00:00:00+00:00", 0)
        _insert_snapshot(db_conn, "p1", "2024-02-01T00:00:00+00:00", 30)
        _insert_snapshot(db_conn, "p1", "2024-03-01T00:00:00+00:00", 60)
        paper = dict(db_conn.execute("SELECT * FROM papers WHERE id = 'p1'").fetchone())
        assert _should_promote(paper, db_conn, 50, 10.0) is True

    def test_high_velocity_spike_not_sustained(self, db_conn):
        """High current velocity but only a spike in the last interval."""
        _insert_paper(db_conn, "p1", citation_velocity=12.0)
        _insert_snapshot(db_conn, "p1", "2024-01-01T00:00:00+00:00", 0)
        _insert_snapshot(db_conn, "p1", "2024-02-01T00:00:00+00:00", 1)
        _insert_snapshot(db_conn, "p1", "2024-03-01T00:00:00+00:00", 40)
        paper = dict(db_conn.execute("SELECT * FROM papers WHERE id = 'p1'").fetchone())
        assert _should_promote(paper, db_conn, 50, 10.0) is False

    def test_high_velocity_single_snapshot_not_promoted(self, db_conn):
        """High velocity but only 1 snapshot → not sustained."""
        _insert_paper(db_conn, "p1", citation_velocity=15.0)
        _insert_snapshot(db_conn, "p1", "2024-01-01T00:00:00+00:00", 10)
        paper = dict(db_conn.execute("SELECT * FROM papers WHERE id = 'p1'").fetchone())
        assert _should_promote(paper, db_conn, 50, 10.0) is False

    def test_low_everything_not_promoted(self, db_conn):
        _insert_paper(db_conn, "p1", citation_count=5, citation_velocity=1.0)
        paper = dict(db_conn.execute("SELECT * FROM papers WHERE id = 'p1'").fetchone())
        assert _should_promote(paper, db_conn, 50, 10.0) is False

    def test_boundary_citations_exactly_threshold_promoted(self, db_conn):
        """Citations >= threshold → promoted."""
        _insert_paper(db_conn, "p1", citation_count=50)
        paper = dict(db_conn.execute("SELECT * FROM papers WHERE id = 'p1'").fetchone())
        assert _should_promote(paper, db_conn, 50, 10.0) is True

    def test_boundary_velocity_exactly_threshold_sustained(self, db_conn):
        """Velocity >= threshold with sustained snapshots → promoted."""
        _insert_paper(db_conn, "p1", citation_velocity=10.0)
        # 11 citations per ~30 days ≈ 11.0/month, comfortably above 10.0
        _insert_snapshot(db_conn, "p1", "2024-01-01T00:00:00+00:00", 0)
        _insert_snapshot(db_conn, "p1", "2024-02-01T00:00:00+00:00", 11)
        _insert_snapshot(db_conn, "p1", "2024-03-01T00:00:00+00:00", 22)
        paper = dict(db_conn.execute("SELECT * FROM papers WHERE id = 'p1'").fetchone())
        assert _should_promote(paper, db_conn, 50, 10.0) is True

    def test_high_velocity_no_snapshots_not_promoted(self, db_conn):
        """High velocity but zero snapshots → cannot verify sustained."""
        _insert_paper(db_conn, "p1", citation_velocity=15.0, citation_count=5)
        paper = dict(db_conn.execute("SELECT * FROM papers WHERE id = 'p1'").fetchone())
        assert _should_promote(paper, db_conn, 50, 10.0) is False


# ---------------------------------------------------------------------------
# run_prune_promote (integration)
# ---------------------------------------------------------------------------

class TestRunPrunePromote:
    """Integration tests for the full rule evaluation pass."""

    NOW = "2025-01-01T00:00:00+00:00"

    def test_prune_eligible_paper(self, db_conn):
        _insert_paper(db_conn, "old_low", ingested_at="2024-01-01T00:00:00+00:00",
                       citation_count=2, citation_velocity=0.3)
        config = _make_config()
        result = run_prune_promote(db_conn, config, self.NOW)

        assert result.pruned_ids == ["old_low"]
        assert result.promoted_ids == []
        assert result.papers_pruned == 1
        assert _get_status(db_conn, "old_low") == "pruned"

    def test_promote_eligible_paper(self, db_conn):
        _insert_paper(db_conn, "hot", citation_count=55)
        config = _make_config()
        result = run_prune_promote(db_conn, config, self.NOW)

        assert result.promoted_ids == ["hot"]
        assert result.pruned_ids == []
        assert result.papers_promoted == 1
        assert _get_status(db_conn, "hot") == "promoted"

    def test_promote_takes_priority_over_prune(self, db_conn):
        """Paper qualifies for both promote (high citations) and prune (old).
        Promote should win."""
        _insert_paper(db_conn, "dual", ingested_at="2024-01-01T00:00:00+00:00",
                       citation_count=55, citation_velocity=0.5)
        config = _make_config()
        result = run_prune_promote(db_conn, config, self.NOW)

        assert "dual" in result.promoted_ids
        assert "dual" not in result.pruned_ids
        assert _get_status(db_conn, "dual") == "promoted"

    def test_manual_status_skipped(self, db_conn):
        """Papers with manual_status=1 are never auto-modified."""
        _insert_paper(db_conn, "manual_active",
                       ingested_at="2024-01-01T00:00:00+00:00",
                       citation_count=2, citation_velocity=0.1,
                       manual_status=1)
        config = _make_config()
        result = run_prune_promote(db_conn, config, self.NOW)

        assert result.pruned_ids == []
        assert result.promoted_ids == []
        assert result.papers_evaluated == 0  # manual papers excluded from query
        assert _get_status(db_conn, "manual_active") == "active"

    def test_only_active_papers_evaluated(self, db_conn):
        """Already promoted/pruned papers are not re-evaluated."""
        _insert_paper(db_conn, "already_pruned",
                       ingested_at="2024-01-01T00:00:00+00:00",
                       citation_count=0, citation_velocity=0.0,
                       status="pruned")
        _insert_paper(db_conn, "already_promoted",
                       citation_count=100, status="promoted")
        config = _make_config()
        result = run_prune_promote(db_conn, config, self.NOW)

        assert result.pruned_ids == []
        assert result.promoted_ids == []
        assert result.papers_evaluated == 0
        assert _get_status(db_conn, "already_pruned") == "pruned"
        assert _get_status(db_conn, "already_promoted") == "promoted"

    def test_mixed_batch(self, db_conn):
        """Multiple papers with different outcomes."""
        # Should be pruned
        _insert_paper(db_conn, "stale", ingested_at="2024-01-01T00:00:00+00:00",
                       citation_count=1, citation_velocity=0.1)
        # Should be promoted
        _insert_paper(db_conn, "star", citation_count=80)
        # Should stay active (young, low citations)
        _insert_paper(db_conn, "young", ingested_at="2024-11-01T00:00:00+00:00",
                       citation_count=3, citation_velocity=0.5)
        # Manual — excluded from query
        _insert_paper(db_conn, "pinned", ingested_at="2024-01-01T00:00:00+00:00",
                       citation_count=0, manual_status=1)

        config = _make_config()
        result = run_prune_promote(db_conn, config, self.NOW)

        assert set(result.pruned_ids) == {"stale"}
        assert set(result.promoted_ids) == {"star"}
        assert result.papers_evaluated == 3  # pinned excluded from query
        assert _get_status(db_conn, "young") == "active"
        assert _get_status(db_conn, "pinned") == "active"

    def test_custom_thresholds(self, db_conn):
        """Config thresholds are respected."""
        _insert_paper(db_conn, "p1", ingested_at="2024-01-01T00:00:00+00:00",
                       citation_count=20, citation_velocity=0.5)
        # Default prune: min_citations=10 → would NOT prune (20 >= 10)
        # Custom prune: min_citations=25 → WILL prune (20 < 25)
        config = _make_config(prune_min_citations=25)
        result = run_prune_promote(db_conn, config, self.NOW)

        assert result.pruned_ids == ["p1"]

    def test_empty_database(self, db_conn):
        config = _make_config()
        result = run_prune_promote(db_conn, config, self.NOW)

        assert result.pruned_ids == []
        assert result.promoted_ids == []
        assert result.papers_evaluated == 0

    def test_velocity_promote_requires_sustained(self, db_conn):
        """Velocity-based promotion needs sustained velocity across snapshots."""
        _insert_paper(db_conn, "p1", citation_velocity=15.0, citation_count=5)
        # No snapshots — cannot confirm sustained
        config = _make_config()
        result = run_prune_promote(db_conn, config, self.NOW)

        assert result.promoted_ids == []
        assert _get_status(db_conn, "p1") == "active"

    def test_result_dataclass_fields(self, db_conn):
        _insert_paper(db_conn, "p1", citation_count=60)
        config = _make_config()
        result = run_prune_promote(db_conn, config, self.NOW)

        assert isinstance(result, RulesResult)
        assert isinstance(result.pruned_ids, list)
        assert isinstance(result.promoted_ids, list)
        assert isinstance(result.papers_evaluated, int)
        assert isinstance(result.papers_pruned, int)
        assert isinstance(result.papers_promoted, int)

    def test_papers_evaluated_count(self, db_conn):
        """papers_evaluated counts only active non-manual papers."""
        _insert_paper(db_conn, "a1", citation_count=5)
        _insert_paper(db_conn, "a2", citation_count=3)
        _insert_paper(db_conn, "manual", manual_status=1)
        _insert_paper(db_conn, "pruned", status="pruned")

        config = _make_config()
        result = run_prune_promote(db_conn, config, self.NOW)
        assert result.papers_evaluated == 2

    def test_status_update_uses_db_function(self, db_conn):
        """Status updates should set manual_status=0 (auto, not manual)."""
        _insert_paper(db_conn, "p1", ingested_at="2024-01-01T00:00:00+00:00",
                       citation_count=2, citation_velocity=0.3)
        config = _make_config()
        run_prune_promote(db_conn, config, self.NOW)

        row = db_conn.execute(
            "SELECT manual_status FROM papers WHERE id = 'p1'"
        ).fetchone()
        assert row["manual_status"] == 0


# ---------------------------------------------------------------------------
# dry_run_prune_promote
# ---------------------------------------------------------------------------

class TestDryRunPrunePromote:
    """Tests for dry-run mode — evaluates without modifying DB."""

    NOW = "2025-01-01T00:00:00+00:00"

    def test_identifies_candidates_without_modifying(self, db_conn):
        _insert_paper(db_conn, "old_low", ingested_at="2024-01-01T00:00:00+00:00",
                       citation_count=2, citation_velocity=0.3)
        _insert_paper(db_conn, "hot", citation_count=55)

        config = _make_config()
        result = dry_run_prune_promote(db_conn, config, self.NOW)

        assert result.pruned_ids == ["old_low"]
        assert result.promoted_ids == ["hot"]
        assert result.papers_evaluated == 2

        # DB unchanged
        assert _get_status(db_conn, "old_low") == "active"
        assert _get_status(db_conn, "hot") == "active"

    def test_returns_same_result_type(self, db_conn):
        config = _make_config()
        result = dry_run_prune_promote(db_conn, config, self.NOW)
        assert isinstance(result, RulesResult)

    def test_empty_db(self, db_conn):
        config = _make_config()
        result = dry_run_prune_promote(db_conn, config, self.NOW)
        assert result.papers_evaluated == 0
        assert result.pruned_ids == []
        assert result.promoted_ids == []
