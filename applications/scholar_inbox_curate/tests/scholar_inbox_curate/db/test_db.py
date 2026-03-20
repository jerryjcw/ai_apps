"""Tests for the database layer (src/db.py)."""

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from src.db import (
    get_connection,
    init_db,
    init_db_on_conn,
    now_utc,
    months_between,
    upsert_paper,
    get_paper,
    list_papers,
    update_paper_status,
    update_paper_citations,
    get_papers_due_for_poll,
    get_papers_never_polled,
    get_paper_count_by_status,
    count_papers,
    count_non_pruned_papers,
    paper_exists,
    insert_snapshot,
    get_snapshots,
    get_snapshot_for_velocity,
    get_earliest_snapshot,
    create_ingestion_run,
    update_ingestion_run,
    get_recent_ingestion_runs,
    record_scraped_date,
    get_scraped_dates,
    find_missing_dates,
    _migrate_v1_to_v2,
    _migrate_v2_to_v3,
    _migrate_v3_to_v4,
    CURRENT_SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_paper(
    paper_id="abc123",
    title="Test Paper",
    authors='["Alice", "Bob"]',
    ingested_at="2026-01-01T00:00:00+00:00",
    **overrides,
) -> dict:
    """Helper to create a paper dict with sensible defaults."""
    paper = {
        "id": paper_id,
        "title": title,
        "authors": authors,
        "abstract": "An abstract.",
        "url": "https://arxiv.org/abs/1234",
        "arxiv_id": "1234.5678",
        "venue": "NeurIPS",
        "year": 2026,
        "published_date": "2026-01-01T00:00:00+00:00",
        "scholar_inbox_score": 0.85,
        "ingested_at": ingested_at,
    }
    paper.update(overrides)
    return paper


# ---------------------------------------------------------------------------
# Schema & Connection Tests
# ---------------------------------------------------------------------------

class TestSchemaInitialization:
    def test_tables_created(self, db_conn):
        """All four tables should exist after init."""
        tables = db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [t["name"] for t in tables]
        assert "papers" in table_names
        assert "citation_snapshots" in table_names
        assert "ingestion_runs" in table_names
        assert "scraped_dates" in table_names

    def test_schema_version_set(self, db_conn):
        version = db_conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == CURRENT_SCHEMA_VERSION

    def test_indexes_created(self, db_conn):
        indexes = db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        ).fetchall()
        index_names = {i["name"] for i in indexes}
        assert "idx_papers_status" in index_names
        assert "idx_papers_ingested_at" in index_names
        assert "idx_papers_velocity" in index_names
        assert "idx_papers_arxiv_id" in index_names
        assert "idx_snapshots_paper_date" in index_names

    def test_idempotent_init(self, db_conn):
        """Calling init_db_on_conn again on an already-initialized DB should be safe."""
        init_db_on_conn(db_conn)
        version = db_conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == CURRENT_SCHEMA_VERSION

    def test_foreign_keys_enabled(self, db_conn):
        result = db_conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert result == 1

    def test_init_db_with_file(self, tmp_path):
        """init_db creates a file-based database."""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        with get_connection(db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            assert len(tables) >= 4


class TestGetConnection:
    def test_context_manager_commits_on_success(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        with get_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO ingestion_runs (started_at) VALUES (?)",
                ("2026-01-01T00:00:00Z",),
            )
        # Verify data persisted
        with get_connection(db_path) as conn:
            rows = conn.execute("SELECT * FROM ingestion_runs").fetchall()
            assert len(rows) == 1

    def test_context_manager_rollbacks_on_error(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        with pytest.raises(ValueError):
            with get_connection(db_path) as conn:
                conn.execute(
                    "INSERT INTO ingestion_runs (started_at) VALUES (?)",
                    ("2026-01-01T00:00:00Z",),
                )
                raise ValueError("test error")
        # Verify data was rolled back
        with get_connection(db_path) as conn:
            rows = conn.execute("SELECT * FROM ingestion_runs").fetchall()
            assert len(rows) == 0

    def test_row_factory_returns_dict_like(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        with get_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO ingestion_runs (started_at) VALUES (?)",
                ("2026-01-01T00:00:00Z",),
            )
            row = conn.execute("SELECT * FROM ingestion_runs").fetchone()
            assert row["started_at"] == "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Date/Time Helper Tests
# ---------------------------------------------------------------------------

class TestDateHelpers:
    def test_now_utc_format(self):
        result = now_utc()
        dt = datetime.fromisoformat(result)
        assert dt.tzinfo is not None

    def test_months_between_same_date(self):
        assert months_between("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z") == 0.0

    def test_months_between_three_months(self):
        result = months_between("2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z")
        assert 2.9 < result < 3.1  # ~90 days / 30.44

    def test_months_between_order_independent(self):
        a = months_between("2026-01-01T00:00:00Z", "2026-07-01T00:00:00Z")
        b = months_between("2026-07-01T00:00:00Z", "2026-01-01T00:00:00Z")
        assert a == b


# ---------------------------------------------------------------------------
# Paper CRUD Tests
# ---------------------------------------------------------------------------

class TestUpsertPaper:
    def test_insert_new_paper(self, db_conn):
        paper = _make_paper()
        result = upsert_paper(db_conn, paper)
        assert result is True
        assert paper_exists(db_conn, "abc123")

    def test_update_existing_paper(self, db_conn):
        paper = _make_paper()
        upsert_paper(db_conn, paper)
        paper["title"] = "Updated Title"
        result = upsert_paper(db_conn, paper)
        assert result is False
        fetched = get_paper(db_conn, "abc123")
        assert fetched["title"] == "Updated Title"

    def test_upsert_preserves_status_on_update(self, db_conn):
        paper = _make_paper()
        upsert_paper(db_conn, paper)
        update_paper_status(db_conn, "abc123", "promoted", manual=True)

        paper["title"] = "New Title"
        upsert_paper(db_conn, paper)

        fetched = get_paper(db_conn, "abc123")
        assert fetched["status"] == "promoted"
        assert fetched["manual_status"] == 1

    def test_upsert_with_list_authors(self, db_conn):
        paper = _make_paper(authors=["Alice", "Bob", "Charlie"])
        upsert_paper(db_conn, paper)
        fetched = get_paper(db_conn, "abc123")
        assert json.loads(fetched["authors"]) == ["Alice", "Bob", "Charlie"]

    def test_upsert_preserves_citation_data_on_update(self, db_conn):
        paper = _make_paper()
        upsert_paper(db_conn, paper)
        update_paper_citations(db_conn, "abc123", citation_count=42, velocity=5.5)

        paper["title"] = "Updated"
        upsert_paper(db_conn, paper)

        fetched = get_paper(db_conn, "abc123")
        assert fetched["citation_count"] == 42
        assert fetched["citation_velocity"] == 5.5


class TestGetPaper:
    def test_get_existing_paper(self, db_conn):
        upsert_paper(db_conn, _make_paper())
        paper = get_paper(db_conn, "abc123")
        assert paper is not None
        assert paper["title"] == "Test Paper"

    def test_get_nonexistent_paper(self, db_conn):
        assert get_paper(db_conn, "nonexistent") is None


class TestListPapers:
    def _insert_papers(self, db_conn):
        papers = [
            _make_paper("p1", "Alpha Paper", ingested_at="2026-01-01T00:00:00+00:00"),
            _make_paper("p2", "Beta Paper", ingested_at="2026-01-02T00:00:00+00:00"),
            _make_paper("p3", "Gamma Paper", ingested_at="2026-01-03T00:00:00+00:00"),
        ]
        for p in papers:
            upsert_paper(db_conn, p)
        update_paper_citations(db_conn, "p1", 10, 1.0)
        update_paper_citations(db_conn, "p2", 50, 10.0)
        update_paper_citations(db_conn, "p3", 5, 0.5)

    def test_list_all(self, db_conn):
        self._insert_papers(db_conn)
        result = list_papers(db_conn)
        assert len(result) == 3

    def test_list_with_status_filter(self, db_conn):
        self._insert_papers(db_conn)
        update_paper_status(db_conn, "p2", "promoted")
        result = list_papers(db_conn, status="promoted")
        assert len(result) == 1
        assert result[0]["id"] == "p2"

    def test_list_sorted_by_velocity_desc(self, db_conn):
        self._insert_papers(db_conn)
        result = list_papers(db_conn, sort_by="citation_velocity", sort_order="DESC")
        velocities = [r["citation_velocity"] for r in result]
        assert velocities == sorted(velocities, reverse=True)

    def test_list_sorted_by_title_asc(self, db_conn):
        self._insert_papers(db_conn)
        result = list_papers(db_conn, sort_by="title", sort_order="ASC")
        titles = [r["title"] for r in result]
        assert titles == sorted(titles)

    def test_list_with_search(self, db_conn):
        self._insert_papers(db_conn)
        result = list_papers(db_conn, search="Beta")
        assert len(result) == 1
        assert result[0]["id"] == "p2"

    def test_list_with_pagination(self, db_conn):
        self._insert_papers(db_conn)
        page1 = list_papers(db_conn, limit=2, offset=0, sort_by="title", sort_order="ASC")
        page2 = list_papers(db_conn, limit=2, offset=2, sort_by="title", sort_order="ASC")
        assert len(page1) == 2
        assert len(page2) == 1
        all_ids = [p["id"] for p in page1 + page2]
        assert len(set(all_ids)) == 3

    def test_list_invalid_sort_column_falls_back(self, db_conn):
        self._insert_papers(db_conn)
        # Should not raise; falls back to citation_velocity
        result = list_papers(db_conn, sort_by="nonexistent_column")
        assert len(result) == 3

    def test_list_invalid_sort_order_falls_back(self, db_conn):
        self._insert_papers(db_conn)
        result = list_papers(db_conn, sort_order="INVALID")
        assert len(result) == 3

    def test_list_combined_status_and_search(self, db_conn):
        self._insert_papers(db_conn)
        update_paper_status(db_conn, "p1", "promoted")
        update_paper_status(db_conn, "p2", "promoted")
        result = list_papers(db_conn, status="promoted", search="Alpha")
        assert len(result) == 1
        assert result[0]["id"] == "p1"

    def test_list_multi_word_search_matches_both_words(self, db_conn):
        upsert_paper(db_conn, _make_paper("d1", "Video Generation with Latent Diffusion Models"))
        upsert_paper(db_conn, _make_paper("d2", "Diffusion Policies for Robotics"))
        upsert_paper(db_conn, _make_paper("d3", "Video Compression Algorithms"))
        result = list_papers(db_conn, search="Diffusion Video")
        assert len(result) == 1
        assert result[0]["id"] == "d1"

    def test_list_multi_word_search_across_fields(self, db_conn):
        upsert_paper(db_conn, _make_paper(
            "d4", "Novel Diffusion Approach", abstract="Applied to video synthesis tasks"
        ))
        upsert_paper(db_conn, _make_paper("d5", "Unrelated Paper", abstract="No match here"))
        result = list_papers(db_conn, search="Diffusion video")
        assert len(result) == 1
        assert result[0]["id"] == "d4"

    def test_count_multi_word_search(self, db_conn):
        upsert_paper(db_conn, _make_paper("d1", "Video Generation with Latent Diffusion Models"))
        upsert_paper(db_conn, _make_paper("d2", "Diffusion Policies for Robotics"))
        upsert_paper(db_conn, _make_paper("d3", "Video Compression Algorithms"))
        count = count_papers(db_conn, search="Diffusion Video")
        assert count == 1


class TestUpdatePaperStatus:
    def test_update_status(self, db_conn):
        upsert_paper(db_conn, _make_paper())
        update_paper_status(db_conn, "abc123", "pruned")
        paper = get_paper(db_conn, "abc123")
        assert paper["status"] == "pruned"
        assert paper["manual_status"] == 0

    def test_update_status_manual(self, db_conn):
        upsert_paper(db_conn, _make_paper())
        update_paper_status(db_conn, "abc123", "promoted", manual=True)
        paper = get_paper(db_conn, "abc123")
        assert paper["status"] == "promoted"
        assert paper["manual_status"] == 1

    def test_invalid_status_raises(self, db_conn):
        upsert_paper(db_conn, _make_paper())
        with pytest.raises(sqlite3.IntegrityError):
            update_paper_status(db_conn, "abc123", "invalid_status")


class TestUpdatePaperCitations:
    def test_updates_count_velocity_and_check_time(self, db_conn):
        upsert_paper(db_conn, _make_paper())
        update_paper_citations(db_conn, "abc123", citation_count=25, velocity=3.5)
        paper = get_paper(db_conn, "abc123")
        assert paper["citation_count"] == 25
        assert paper["citation_velocity"] == 3.5
        assert paper["last_cited_check"] is not None


class TestGetPapersDueForPoll:
    def test_never_polled_paper_included(self, db_conn):
        upsert_paper(db_conn, _make_paper(ingested_at="2026-02-20T00:00:00+00:00"))
        result = get_papers_due_for_poll(db_conn, "2026-02-26T00:00:00+00:00")
        assert len(result) == 1

    def test_pruned_paper_excluded(self, db_conn):
        upsert_paper(db_conn, _make_paper(ingested_at="2026-02-20T00:00:00+00:00"))
        update_paper_status(db_conn, "abc123", "pruned")
        result = get_papers_due_for_poll(db_conn, "2026-02-26T00:00:00+00:00")
        assert len(result) == 0

    def test_recently_polled_young_paper_excluded(self, db_conn):
        """Paper < 3 months old, polled 3 days ago -> not due yet (interval is 7 days)."""
        upsert_paper(db_conn, _make_paper(ingested_at="2026-02-01T00:00:00+00:00"))
        # Manually set last_cited_check to 3 days ago
        db_conn.execute(
            "UPDATE papers SET last_cited_check = ? WHERE id = ?",
            ("2026-02-23T00:00:00+00:00", "abc123"),
        )
        result = get_papers_due_for_poll(db_conn, "2026-02-26T00:00:00+00:00")
        assert len(result) == 0

    def test_young_paper_due_after_7_days(self, db_conn):
        """Paper < 3 months old, polled 8 days ago -> due."""
        upsert_paper(db_conn, _make_paper(ingested_at="2026-02-01T00:00:00+00:00"))
        db_conn.execute(
            "UPDATE papers SET last_cited_check = ? WHERE id = ?",
            ("2026-02-18T00:00:00+00:00", "abc123"),
        )
        result = get_papers_due_for_poll(db_conn, "2026-02-26T00:00:00+00:00")
        assert len(result) == 1

    def test_mid_age_paper_due_after_14_days(self, db_conn):
        """Paper 3-12 months old, polled 15 days ago -> due."""
        upsert_paper(db_conn, _make_paper(ingested_at="2025-08-01T00:00:00+00:00"))
        db_conn.execute(
            "UPDATE papers SET last_cited_check = ? WHERE id = ?",
            ("2026-02-11T00:00:00+00:00", "abc123"),
        )
        result = get_papers_due_for_poll(db_conn, "2026-02-26T00:00:00+00:00")
        assert len(result) == 1

    def test_old_paper_due_after_30_days(self, db_conn):
        """Paper > 12 months old, polled 31 days ago -> due."""
        upsert_paper(db_conn, _make_paper(ingested_at="2024-06-01T00:00:00+00:00"))
        db_conn.execute(
            "UPDATE papers SET last_cited_check = ? WHERE id = ?",
            ("2026-01-25T00:00:00+00:00", "abc123"),
        )
        result = get_papers_due_for_poll(db_conn, "2026-02-26T00:00:00+00:00")
        assert len(result) == 1

    def test_promoted_paper_due_after_30_days(self, db_conn):
        upsert_paper(db_conn, _make_paper(ingested_at="2026-01-01T00:00:00+00:00"))
        update_paper_status(db_conn, "abc123", "promoted")
        db_conn.execute(
            "UPDATE papers SET last_cited_check = ? WHERE id = ?",
            ("2026-01-20T00:00:00+00:00", "abc123"),
        )
        result = get_papers_due_for_poll(db_conn, "2026-02-26T00:00:00+00:00")
        assert len(result) == 1

    def test_limit_caps_results(self, db_conn):
        """When limit is provided, at most that many papers are returned."""
        for i in range(5):
            upsert_paper(db_conn, _make_paper(
                paper_id=f"p{i}",
                title=f"Paper {i}",
                ingested_at="2026-02-20T00:00:00+00:00",
            ))
        result = get_papers_due_for_poll(db_conn, "2026-02-26T00:00:00+00:00", limit=3)
        assert len(result) == 3

    def test_limit_none_returns_all(self, db_conn):
        """When limit is None, all eligible papers are returned."""
        for i in range(5):
            upsert_paper(db_conn, _make_paper(
                paper_id=f"p{i}",
                title=f"Paper {i}",
                ingested_at="2026-02-20T00:00:00+00:00",
            ))
        result = get_papers_due_for_poll(db_conn, "2026-02-26T00:00:00+00:00")
        assert len(result) == 5

    def test_never_polled_papers_sorted_first(self, db_conn):
        """Never-polled papers have highest priority (overdue_ratio = 1e9)."""
        # Paper A: polled 8 days ago (young, 7-day interval -> ratio ~1.14)
        upsert_paper(db_conn, _make_paper(
            paper_id="polled",
            title="Polled Paper",
            ingested_at="2026-02-01T00:00:00+00:00",
        ))
        db_conn.execute(
            "UPDATE papers SET last_cited_check = ? WHERE id = ?",
            ("2026-02-18T00:00:00+00:00", "polled"),
        )
        # Paper B: never polled
        upsert_paper(db_conn, _make_paper(
            paper_id="unpolled",
            title="Unpolled Paper",
            ingested_at="2026-02-20T00:00:00+00:00",
        ))

        result = get_papers_due_for_poll(db_conn, "2026-02-26T00:00:00+00:00")
        assert len(result) == 2
        assert result[0]["id"] == "unpolled"

    def test_higher_overdue_ratio_sorted_first(self, db_conn):
        """A monthly paper 60 days overdue outranks a weekly paper 8 days overdue."""
        now = "2026-03-15T00:00:00+00:00"

        # Old paper (>12 months), 30-day interval, last polled 60 days ago -> ratio 2.0
        upsert_paper(db_conn, _make_paper(
            paper_id="old_overdue",
            title="Old Overdue",
            ingested_at="2024-06-01T00:00:00+00:00",
        ))
        db_conn.execute(
            "UPDATE papers SET last_cited_check = ? WHERE id = ?",
            ("2026-01-14T00:00:00+00:00", "old_overdue"),
        )

        # Young paper (<3 months), 7-day interval, last polled 8 days ago -> ratio ~1.14
        upsert_paper(db_conn, _make_paper(
            paper_id="young_due",
            title="Young Due",
            ingested_at="2026-02-01T00:00:00+00:00",
        ))
        db_conn.execute(
            "UPDATE papers SET last_cited_check = ? WHERE id = ?",
            ("2026-03-07T00:00:00+00:00", "young_due"),
        )

        result = get_papers_due_for_poll(db_conn, now)
        assert len(result) == 2
        assert result[0]["id"] == "old_overdue"
        assert result[1]["id"] == "young_due"


class TestCountNonPrunedPapers:
    def test_empty_db(self, db_conn):
        assert count_non_pruned_papers(db_conn) == 0

    def test_counts_active_and_promoted(self, db_conn):
        upsert_paper(db_conn, _make_paper("p1", "Paper 1"))
        upsert_paper(db_conn, _make_paper("p2", "Paper 2"))
        update_paper_status(db_conn, "p2", "promoted")
        assert count_non_pruned_papers(db_conn) == 2

    def test_excludes_pruned(self, db_conn):
        upsert_paper(db_conn, _make_paper("p1", "Paper 1"))
        upsert_paper(db_conn, _make_paper("p2", "Paper 2"))
        update_paper_status(db_conn, "p2", "pruned")
        assert count_non_pruned_papers(db_conn) == 1


class TestGetPapersNeverPolled:
    def test_empty_db(self, db_conn):
        assert get_papers_never_polled(db_conn) == []

    def test_never_polled_paper_included(self, db_conn):
        upsert_paper(db_conn, _make_paper("p1", "Paper 1"))
        result = get_papers_never_polled(db_conn)
        assert len(result) == 1
        assert result[0]["id"] == "p1"

    def test_polled_paper_excluded(self, db_conn):
        upsert_paper(db_conn, _make_paper("p1", "Paper 1"))
        update_paper_citations(db_conn, "p1", 10, 1.5)
        result = get_papers_never_polled(db_conn)
        assert len(result) == 0

    def test_pruned_paper_excluded(self, db_conn):
        upsert_paper(db_conn, _make_paper("p1", "Paper 1"))
        update_paper_status(db_conn, "p1", "pruned")
        result = get_papers_never_polled(db_conn)
        assert len(result) == 0

    def test_mix_of_polled_and_unpolled(self, db_conn):
        upsert_paper(db_conn, _make_paper("p1", "Never Polled"))
        upsert_paper(db_conn, _make_paper("p2", "Already Polled"))
        upsert_paper(db_conn, _make_paper("p3", "Also Never Polled"))
        upsert_paper(db_conn, _make_paper("p4", "Pruned Unpolled"))
        update_paper_citations(db_conn, "p2", 5, 0.5)
        update_paper_status(db_conn, "p4", "pruned")
        result = get_papers_never_polled(db_conn)
        ids = {r["id"] for r in result}
        assert ids == {"p1", "p3"}

    def test_promoted_unpolled_paper_included(self, db_conn):
        upsert_paper(db_conn, _make_paper("p1", "Promoted"))
        update_paper_status(db_conn, "p1", "promoted")
        result = get_papers_never_polled(db_conn)
        assert len(result) == 1
        assert result[0]["id"] == "p1"


class TestPaperCountByStatus:
    def test_empty_db(self, db_conn):
        counts = get_paper_count_by_status(db_conn)
        assert counts == {"active": 0, "promoted": 0, "pruned": 0}

    def test_mixed_statuses(self, db_conn):
        upsert_paper(db_conn, _make_paper("p1", "Paper 1"))
        upsert_paper(db_conn, _make_paper("p2", "Paper 2"))
        upsert_paper(db_conn, _make_paper("p3", "Paper 3"))
        update_paper_status(db_conn, "p2", "promoted")
        update_paper_status(db_conn, "p3", "pruned")
        counts = get_paper_count_by_status(db_conn)
        assert counts == {"active": 1, "promoted": 1, "pruned": 1}


class TestCountPapers:
    def test_count_all(self, db_conn):
        upsert_paper(db_conn, _make_paper("p1", "Paper 1"))
        upsert_paper(db_conn, _make_paper("p2", "Paper 2"))
        assert count_papers(db_conn) == 2

    def test_count_by_status(self, db_conn):
        upsert_paper(db_conn, _make_paper("p1", "Paper 1"))
        upsert_paper(db_conn, _make_paper("p2", "Paper 2"))
        update_paper_status(db_conn, "p2", "promoted")
        assert count_papers(db_conn, status="active") == 1
        assert count_papers(db_conn, status="promoted") == 1

    def test_count_with_search(self, db_conn):
        upsert_paper(db_conn, _make_paper("p1", "Machine Learning"))
        upsert_paper(db_conn, _make_paper("p2", "Deep Learning"))
        assert count_papers(db_conn, search="Machine") == 1

    def test_count_combined_filters(self, db_conn):
        upsert_paper(db_conn, _make_paper("p1", "Machine Learning"))
        upsert_paper(db_conn, _make_paper("p2", "Machine Vision"))
        update_paper_status(db_conn, "p2", "promoted")
        assert count_papers(db_conn, status="active", search="Machine") == 1


class TestPaperExists:
    def test_exists(self, db_conn):
        upsert_paper(db_conn, _make_paper())
        assert paper_exists(db_conn, "abc123") is True

    def test_not_exists(self, db_conn):
        assert paper_exists(db_conn, "nonexistent") is False


# ---------------------------------------------------------------------------
# Citation Snapshot Tests
# ---------------------------------------------------------------------------

class TestInsertSnapshot:
    def test_insert_basic_snapshot(self, db_conn):
        upsert_paper(db_conn, _make_paper())
        insert_snapshot(db_conn, "abc123", 10, "semantic_scholar")
        snapshots = get_snapshots(db_conn, "abc123")
        assert len(snapshots) == 1
        assert snapshots[0]["total_citations"] == 10
        assert snapshots[0]["source"] == "semantic_scholar"

    def test_insert_snapshot_with_breakdown(self, db_conn):
        upsert_paper(db_conn, _make_paper())
        breakdown = {"2025": 5, "2026": 10}
        insert_snapshot(db_conn, "abc123", 15, "openalex", yearly_breakdown=breakdown)
        snapshots = get_snapshots(db_conn, "abc123")
        assert json.loads(snapshots[0]["yearly_breakdown"]) == breakdown

    def test_invalid_source_raises(self, db_conn):
        upsert_paper(db_conn, _make_paper())
        with pytest.raises(sqlite3.IntegrityError):
            insert_snapshot(db_conn, "abc123", 10, "invalid_source")

    def test_foreign_key_constraint(self, db_conn):
        with pytest.raises(sqlite3.IntegrityError):
            insert_snapshot(db_conn, "nonexistent", 10, "semantic_scholar")


class TestGetSnapshots:
    def test_ordered_by_date_desc(self, db_conn):
        upsert_paper(db_conn, _make_paper())
        # Insert with specific timestamps
        for i, ts in enumerate(["2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z", "2026-03-01T00:00:00Z"]):
            db_conn.execute(
                "INSERT INTO citation_snapshots (paper_id, checked_at, total_citations, source) "
                "VALUES (?, ?, ?, ?)",
                ("abc123", ts, (i + 1) * 10, "semantic_scholar"),
            )
        snapshots = get_snapshots(db_conn, "abc123")
        assert len(snapshots) == 3
        assert snapshots[0]["checked_at"] == "2026-03-01T00:00:00Z"

    def test_respects_limit(self, db_conn):
        upsert_paper(db_conn, _make_paper())
        for i in range(5):
            db_conn.execute(
                "INSERT INTO citation_snapshots (paper_id, checked_at, total_citations, source) "
                "VALUES (?, ?, ?, ?)",
                ("abc123", f"2026-01-0{i+1}T00:00:00Z", i * 10, "semantic_scholar"),
            )
        snapshots = get_snapshots(db_conn, "abc123", limit=3)
        assert len(snapshots) == 3


class TestGetSnapshotForVelocity:
    def test_finds_snapshot_from_months_ago(self, db_conn):
        upsert_paper(db_conn, _make_paper())
        # Insert snapshot from 4 months ago
        db_conn.execute(
            "INSERT INTO citation_snapshots (paper_id, checked_at, total_citations, source) "
            "VALUES (?, ?, ?, ?)",
            ("abc123", "2025-10-01T00:00:00Z", 5, "semantic_scholar"),
        )
        # The function uses now_utc() internally, so we mock it
        with patch("src.db.now_utc", return_value="2026-02-26T00:00:00+00:00"):
            result = get_snapshot_for_velocity(db_conn, "abc123", months_ago=3)
        assert result is not None
        assert result["total_citations"] == 5

    def test_returns_none_when_no_old_snapshots(self, db_conn):
        upsert_paper(db_conn, _make_paper())
        # Insert snapshot from today only
        db_conn.execute(
            "INSERT INTO citation_snapshots (paper_id, checked_at, total_citations, source) "
            "VALUES (?, ?, ?, ?)",
            ("abc123", "2026-02-26T00:00:00Z", 10, "semantic_scholar"),
        )
        with patch("src.db.now_utc", return_value="2026-02-26T00:00:00+00:00"):
            result = get_snapshot_for_velocity(db_conn, "abc123", months_ago=3)
        assert result is None


class TestGetEarliestSnapshot:
    def test_returns_earliest(self, db_conn):
        upsert_paper(db_conn, _make_paper())
        for ts, count in [("2026-03-01T00:00:00Z", 30), ("2026-01-01T00:00:00Z", 5), ("2026-02-01T00:00:00Z", 15)]:
            db_conn.execute(
                "INSERT INTO citation_snapshots (paper_id, checked_at, total_citations, source) "
                "VALUES (?, ?, ?, ?)",
                ("abc123", ts, count, "semantic_scholar"),
            )
        result = get_earliest_snapshot(db_conn, "abc123")
        assert result["checked_at"] == "2026-01-01T00:00:00Z"
        assert result["total_citations"] == 5

    def test_returns_none_for_no_snapshots(self, db_conn):
        upsert_paper(db_conn, _make_paper())
        assert get_earliest_snapshot(db_conn, "abc123") is None


# ---------------------------------------------------------------------------
# Ingestion Run Tests
# ---------------------------------------------------------------------------

class TestIngestionRuns:
    def test_create_run(self, db_conn):
        run_id = create_ingestion_run(db_conn)
        assert run_id is not None
        assert isinstance(run_id, int)

    def test_update_run_completed(self, db_conn):
        run_id = create_ingestion_run(db_conn)
        update_ingestion_run(db_conn, run_id, papers_found=20, papers_ingested=15, status="completed")
        runs = get_recent_ingestion_runs(db_conn)
        assert len(runs) == 1
        assert runs[0]["status"] == "completed"
        assert runs[0]["papers_found"] == 20
        assert runs[0]["papers_ingested"] == 15
        assert runs[0]["finished_at"] is not None

    def test_update_run_failed(self, db_conn):
        run_id = create_ingestion_run(db_conn)
        update_ingestion_run(
            db_conn, run_id,
            papers_found=0, papers_ingested=0,
            status="failed", error_message="Connection timeout",
        )
        runs = get_recent_ingestion_runs(db_conn)
        assert runs[0]["status"] == "failed"
        assert runs[0]["error_message"] == "Connection timeout"

    def test_recent_runs_ordered_desc(self, db_conn):
        for ts in ["2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z", "2026-03-01T00:00:00Z"]:
            db_conn.execute(
                "INSERT INTO ingestion_runs (started_at, status) VALUES (?, 'completed')",
                (ts,),
            )
        runs = get_recent_ingestion_runs(db_conn)
        assert runs[0]["started_at"] == "2026-03-01T00:00:00Z"

    def test_recent_runs_respects_limit(self, db_conn):
        for i in range(5):
            create_ingestion_run(db_conn)
        runs = get_recent_ingestion_runs(db_conn, limit=3)
        assert len(runs) == 3

    def test_invalid_run_status_raises(self, db_conn):
        with pytest.raises(sqlite3.IntegrityError):
            db_conn.execute(
                "INSERT INTO ingestion_runs (started_at, status) VALUES (?, ?)",
                ("2026-01-01T00:00:00Z", "invalid"),
            )


# ---------------------------------------------------------------------------
# Cascade Delete Tests
# ---------------------------------------------------------------------------

class TestCascadeDelete:
    def test_deleting_paper_cascades_to_snapshots(self, db_conn):
        upsert_paper(db_conn, _make_paper())
        insert_snapshot(db_conn, "abc123", 10, "semantic_scholar")
        assert len(get_snapshots(db_conn, "abc123")) == 1

        db_conn.execute("DELETE FROM papers WHERE id = ?", ("abc123",))
        assert len(get_snapshots(db_conn, "abc123")) == 0


# ---------------------------------------------------------------------------
# Scraped Dates Tests
# ---------------------------------------------------------------------------

class TestRecordScrapedDate:
    def test_record_single_date(self, db_conn):
        record_scraped_date(db_conn, "2026-02-25")
        dates = get_scraped_dates(db_conn)
        assert "2026-02-25" in dates

    def test_record_idempotent(self, db_conn):
        record_scraped_date(db_conn, "2026-02-25")
        record_scraped_date(db_conn, "2026-02-25")
        dates = get_scraped_dates(db_conn)
        assert len(dates) == 1

    def test_record_multiple_dates(self, db_conn):
        record_scraped_date(db_conn, "2026-02-24")
        record_scraped_date(db_conn, "2026-02-25")
        record_scraped_date(db_conn, "2026-02-26")
        dates = get_scraped_dates(db_conn)
        assert len(dates) == 3


class TestGetScrapedDates:
    def test_empty(self, db_conn):
        assert get_scraped_dates(db_conn) == set()

    def test_returns_set_of_strings(self, db_conn):
        record_scraped_date(db_conn, "2026-02-25")
        dates = get_scraped_dates(db_conn)
        assert isinstance(dates, set)
        assert all(isinstance(d, str) for d in dates)


class TestFindMissingDates:
    def test_all_missing(self, db_conn):
        """When nothing has been scraped, all weekdays are missing."""
        from datetime import date
        # Wednesday 2026-02-25
        today = date(2026, 2, 25)
        missing = find_missing_dates(db_conn, lookback_days=5, today=today)
        # 5 days back: Feb 24 (Tue), 23 (Mon), 22 (Sun-skip), 21 (Sat-skip), 20 (Fri)
        assert len(missing) == 3
        expected = ["2026-02-20", "2026-02-23", "2026-02-24"]
        assert missing == expected

    def test_some_scraped(self, db_conn):
        from datetime import date
        record_scraped_date(db_conn, "2026-02-24")
        today = date(2026, 2, 25)
        missing = find_missing_dates(db_conn, lookback_days=5, today=today)
        assert "2026-02-24" not in missing
        assert "2026-02-23" in missing

    def test_all_scraped(self, db_conn):
        from datetime import date
        today = date(2026, 2, 25)
        # Scrape all weekdays in range
        record_scraped_date(db_conn, "2026-02-20")
        record_scraped_date(db_conn, "2026-02-23")
        record_scraped_date(db_conn, "2026-02-24")
        missing = find_missing_dates(db_conn, lookback_days=5, today=today)
        assert missing == []

    def test_skips_weekends(self, db_conn):
        from datetime import date
        # Monday 2026-02-23
        today = date(2026, 2, 23)
        missing = find_missing_dates(db_conn, lookback_days=3, today=today)
        # 3 days back: Feb 22 (Sun-skip), 21 (Sat-skip), 20 (Fri)
        assert len(missing) == 1
        assert missing[0] == "2026-02-20"

    def test_sorted_oldest_first(self, db_conn):
        from datetime import date
        today = date(2026, 2, 27)
        missing = find_missing_dates(db_conn, lookback_days=7, today=today)
        assert missing == sorted(missing)


# ---------------------------------------------------------------------------
# Migration Tests
# ---------------------------------------------------------------------------

class TestMigrationV1ToV2:
    def test_migrate_adds_scraped_dates_table(self):
        """Simulate a V1 database and migrate to V2."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        # Create V1 schema (without scraped_dates or digest_date)
        v1_schema = """\
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT,
    abstract TEXT,
    url TEXT,
    arxiv_id TEXT,
    venue TEXT,
    year INTEGER,
    published_date TEXT,
    scholar_inbox_score REAL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'promoted', 'pruned')),
    manual_status INTEGER NOT NULL DEFAULT 0,
    ingested_at TEXT NOT NULL,
    last_cited_check TEXT,
    citation_count INTEGER NOT NULL DEFAULT 0,
    citation_velocity REAL NOT NULL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS citation_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    checked_at TEXT NOT NULL,
    total_citations INTEGER NOT NULL,
    yearly_breakdown TEXT,
    source TEXT NOT NULL CHECK(source IN ('semantic_scholar', 'openalex'))
);
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    papers_found INTEGER NOT NULL DEFAULT 0,
    papers_ingested INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK(status IN ('running', 'completed', 'failed')),
    error_message TEXT
);
"""
        conn.executescript(v1_schema)
        conn.execute("PRAGMA user_version = 1")

        # Run migration
        _migrate_v1_to_v2(conn)
        conn.execute("PRAGMA user_version = 2")

        # Verify scraped_dates table exists
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='scraped_dates'"
        ).fetchall()
        assert len(tables) == 1

        # Verify digest_date column exists on ingestion_runs
        cols = conn.execute("PRAGMA table_info(ingestion_runs)").fetchall()
        col_names = [c["name"] for c in cols]
        assert "digest_date" in col_names

        # Verify we can use the new table
        record_scraped_date(conn, "2026-02-25")
        assert "2026-02-25" in get_scraped_dates(conn)

        conn.close()

    def test_full_init_on_v1_db_runs_migration(self):
        """init_db_on_conn should detect V1 and run all migrations to current."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        # Simulate V1 state
        v1_schema = """\
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT,
    abstract TEXT,
    url TEXT,
    arxiv_id TEXT,
    venue TEXT,
    year INTEGER,
    published_date TEXT,
    scholar_inbox_score REAL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'promoted', 'pruned')),
    manual_status INTEGER NOT NULL DEFAULT 0,
    ingested_at TEXT NOT NULL,
    last_cited_check TEXT,
    citation_count INTEGER NOT NULL DEFAULT 0,
    citation_velocity REAL NOT NULL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS citation_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    checked_at TEXT NOT NULL,
    total_citations INTEGER NOT NULL,
    yearly_breakdown TEXT,
    source TEXT NOT NULL CHECK(source IN ('semantic_scholar', 'openalex'))
);
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    papers_found INTEGER NOT NULL DEFAULT 0,
    papers_ingested INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK(status IN ('running', 'completed', 'failed')),
    error_message TEXT
);
"""
        conn.executescript(v1_schema)
        conn.execute("PRAGMA user_version = 1")

        # Run full init — should detect V1 and migrate through V2 to V3
        init_db_on_conn(conn)

        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == CURRENT_SCHEMA_VERSION

        # scraped_dates should be usable
        record_scraped_date(conn, "2026-01-01")
        assert "2026-01-01" in get_scraped_dates(conn)

        # doi column should exist
        cols = conn.execute("PRAGMA table_info(papers)").fetchall()
        col_names = [c["name"] for c in cols]
        assert "doi" in col_names

        conn.close()


class TestMigrationV2ToV3:
    def test_migrate_adds_doi_column(self):
        """Simulate a V2 database and migrate to V3."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        # Create V2 schema (without doi)
        v2_schema = """\
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT,
    abstract TEXT,
    url TEXT,
    arxiv_id TEXT,
    venue TEXT,
    year INTEGER,
    published_date TEXT,
    scholar_inbox_score REAL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'promoted', 'pruned')),
    manual_status INTEGER NOT NULL DEFAULT 0,
    ingested_at TEXT NOT NULL,
    last_cited_check TEXT,
    citation_count INTEGER NOT NULL DEFAULT 0,
    citation_velocity REAL NOT NULL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS citation_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    checked_at TEXT NOT NULL,
    total_citations INTEGER NOT NULL,
    yearly_breakdown TEXT,
    source TEXT NOT NULL CHECK(source IN ('semantic_scholar', 'openalex'))
);
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    papers_found INTEGER NOT NULL DEFAULT 0,
    papers_ingested INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK(status IN ('running', 'completed', 'failed')),
    error_message TEXT,
    digest_date TEXT
);
CREATE TABLE IF NOT EXISTS scraped_dates (
    digest_date TEXT PRIMARY KEY,
    scraped_at TEXT NOT NULL,
    run_id INTEGER REFERENCES ingestion_runs(id),
    papers_found INTEGER NOT NULL DEFAULT 0
);
"""
        conn.executescript(v2_schema)
        conn.execute("PRAGMA user_version = 2")

        # Run migration
        _migrate_v2_to_v3(conn)
        conn.execute("PRAGMA user_version = 3")

        # Verify doi column exists
        cols = conn.execute("PRAGMA table_info(papers)").fetchall()
        col_names = [c["name"] for c in cols]
        assert "doi" in col_names

        # Verify we can insert a paper with doi
        conn.execute(
            "INSERT INTO papers (id, title, ingested_at, doi) VALUES (?, ?, ?, ?)",
            ("test1", "Test", "2026-01-01T00:00:00Z", "10.1234/test"),
        )
        row = conn.execute("SELECT doi FROM papers WHERE id = 'test1'").fetchone()
        assert row["doi"] == "10.1234/test"

        conn.close()

    def test_migrate_idempotent(self):
        """Running V2→V3 migration twice should not fail."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        # Create schema with doi already present
        conn.execute("""\
            CREATE TABLE papers (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, ingested_at TEXT NOT NULL,
                doi TEXT
            )
        """)
        conn.execute("PRAGMA user_version = 2")

        # Should not raise
        _migrate_v2_to_v3(conn)
        _migrate_v2_to_v3(conn)

        conn.close()


class TestDoiColumn:
    def test_upsert_paper_with_doi(self, db_conn):
        paper = _make_paper(doi="10.1234/test.2026")
        upsert_paper(db_conn, paper)
        fetched = get_paper(db_conn, "abc123")
        assert fetched["doi"] == "10.1234/test.2026"

    def test_upsert_paper_without_doi(self, db_conn):
        paper = _make_paper()
        upsert_paper(db_conn, paper)
        fetched = get_paper(db_conn, "abc123")
        assert fetched["doi"] is None

    def test_upsert_updates_doi(self, db_conn):
        paper = _make_paper()
        upsert_paper(db_conn, paper)
        paper["doi"] = "10.5555/new.doi"
        upsert_paper(db_conn, paper)
        fetched = get_paper(db_conn, "abc123")
        assert fetched["doi"] == "10.5555/new.doi"


class TestMigrationV3ToV4:
    def test_migrate_adds_category_column(self):
        """Simulate a V3 database and migrate to V4."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        # Create V3 schema (without category)
        v3_schema = """\
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT,
    abstract TEXT,
    url TEXT,
    arxiv_id TEXT,
    doi TEXT,
    venue TEXT,
    year INTEGER,
    published_date TEXT,
    scholar_inbox_score REAL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'promoted', 'pruned')),
    manual_status INTEGER NOT NULL DEFAULT 0,
    ingested_at TEXT NOT NULL,
    last_cited_check TEXT,
    citation_count INTEGER NOT NULL DEFAULT 0,
    citation_velocity REAL NOT NULL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS citation_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    checked_at TEXT NOT NULL,
    total_citations INTEGER NOT NULL,
    yearly_breakdown TEXT,
    source TEXT NOT NULL CHECK(source IN ('semantic_scholar', 'openalex'))
);
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    papers_found INTEGER NOT NULL DEFAULT 0,
    papers_ingested INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK(status IN ('running', 'completed', 'failed')),
    error_message TEXT,
    digest_date TEXT
);
CREATE TABLE IF NOT EXISTS scraped_dates (
    digest_date TEXT PRIMARY KEY,
    scraped_at TEXT NOT NULL,
    run_id INTEGER REFERENCES ingestion_runs(id),
    papers_found INTEGER NOT NULL DEFAULT 0
);
"""
        conn.executescript(v3_schema)
        conn.execute("PRAGMA user_version = 3")

        # Run migration
        _migrate_v3_to_v4(conn)
        conn.execute("PRAGMA user_version = 4")

        # Verify category column exists
        cols = conn.execute("PRAGMA table_info(papers)").fetchall()
        col_names = [c["name"] for c in cols]
        assert "category" in col_names

        # Verify we can insert a paper with category
        conn.execute(
            "INSERT INTO papers (id, title, ingested_at, category) VALUES (?, ?, ?, ?)",
            ("test1", "Test", "2026-01-01T00:00:00Z", "Computer Vision and Graphics"),
        )
        row = conn.execute("SELECT category FROM papers WHERE id = 'test1'").fetchone()
        assert row["category"] == "Computer Vision and Graphics"

        conn.close()

    def test_migrate_idempotent(self):
        """Running V3→V4 migration twice should not fail."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        conn.execute("""\
            CREATE TABLE papers (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, ingested_at TEXT NOT NULL,
                category TEXT
            )
        """)
        conn.execute("PRAGMA user_version = 3")

        # Should not raise
        _migrate_v3_to_v4(conn)
        _migrate_v3_to_v4(conn)

        conn.close()

    def test_full_init_on_v3_db_runs_migration(self):
        """init_db_on_conn should detect V3 and run migration to V4."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        # Simulate V3 state
        v3_schema = """\
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT,
    abstract TEXT,
    url TEXT,
    arxiv_id TEXT,
    doi TEXT,
    venue TEXT,
    year INTEGER,
    published_date TEXT,
    scholar_inbox_score REAL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'promoted', 'pruned')),
    manual_status INTEGER NOT NULL DEFAULT 0,
    ingested_at TEXT NOT NULL,
    last_cited_check TEXT,
    citation_count INTEGER NOT NULL DEFAULT 0,
    citation_velocity REAL NOT NULL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS citation_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    checked_at TEXT NOT NULL,
    total_citations INTEGER NOT NULL,
    yearly_breakdown TEXT,
    source TEXT NOT NULL CHECK(source IN ('semantic_scholar', 'openalex'))
);
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    papers_found INTEGER NOT NULL DEFAULT 0,
    papers_ingested INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK(status IN ('running', 'completed', 'failed')),
    error_message TEXT,
    digest_date TEXT
);
CREATE TABLE IF NOT EXISTS scraped_dates (
    digest_date TEXT PRIMARY KEY,
    scraped_at TEXT NOT NULL,
    run_id INTEGER REFERENCES ingestion_runs(id),
    papers_found INTEGER NOT NULL DEFAULT 0
);
"""
        conn.executescript(v3_schema)
        conn.execute("PRAGMA user_version = 3")

        init_db_on_conn(conn)

        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == CURRENT_SCHEMA_VERSION

        # category column should exist
        cols = conn.execute("PRAGMA table_info(papers)").fetchall()
        col_names = [c["name"] for c in cols]
        assert "category" in col_names

        conn.close()


class TestCategoryColumn:
    def test_upsert_paper_with_category(self, db_conn):
        paper = _make_paper(category="Computer Vision and Graphics")
        upsert_paper(db_conn, paper)
        fetched = get_paper(db_conn, "abc123")
        assert fetched["category"] == "Computer Vision and Graphics"

    def test_upsert_paper_without_category(self, db_conn):
        paper = _make_paper()
        upsert_paper(db_conn, paper)
        fetched = get_paper(db_conn, "abc123")
        assert fetched["category"] is None

    def test_upsert_updates_category(self, db_conn):
        paper = _make_paper()
        upsert_paper(db_conn, paper)
        paper["category"] = "Natural Language Processing"
        upsert_paper(db_conn, paper)
        fetched = get_paper(db_conn, "abc123")
        assert fetched["category"] == "Natural Language Processing"
