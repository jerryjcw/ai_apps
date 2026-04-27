"""Tests for the /stats page route, template, and the supporting db queries."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.config import AppConfig
from src.db import (
    get_connection,
    get_monthly_ingest_counts,
    get_paper_date_range,
    get_poll_staleness_buckets,
    get_weekly_citation_updates,
    init_db,
    insert_snapshot,
    upsert_paper,
)
from src.web.app import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def web_config(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return AppConfig(db_path=db_path)


@pytest.fixture
def client(web_config):
    app = create_app(web_config)
    return TestClient(app, follow_redirects=True)


def _iso(d: date) -> str:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).isoformat()


def _insert_paper(conn: sqlite3.Connection, *, pid: str, ingested: date,
                  published: date | None = None, last_poll: date | None = None,
                  status: str = "active", citation_count: int = 0) -> None:
    upsert_paper(conn, {
        "id": pid,
        "title": f"Paper {pid}",
        "authors": '["A. Author"]',
        "ingested_at": _iso(ingested),
        "published_date": _iso(published) if published else None,
        "last_cited_check": _iso(last_poll) if last_poll else None,
        "citation_count": citation_count,
        "citation_velocity": 0.0,
        "status": status,
    })


# ---------------------------------------------------------------------------
# DB-layer tests
# ---------------------------------------------------------------------------

class TestGetPaperDateRange:
    def test_empty_db(self, db_conn):
        r = get_paper_date_range(db_conn)
        assert r["oldest_published"] is None
        assert r["newest_published"] is None
        assert r["oldest_ingested"] is None
        assert r["newest_ingested"] is None
        assert r["total_papers"] == 0
        assert r["missing_published_date"] == 0

    def test_published_range(self, db_conn):
        _insert_paper(db_conn, pid="p-old", ingested=date(2026, 1, 1),
                      published=date(2020, 3, 15))
        _insert_paper(db_conn, pid="p-mid", ingested=date(2026, 1, 2),
                      published=date(2022, 6, 1))
        _insert_paper(db_conn, pid="p-new", ingested=date(2026, 1, 3),
                      published=date(2024, 12, 31))

        r = get_paper_date_range(db_conn)
        assert r["oldest_published"]["id"] == "p-old"
        assert r["newest_published"]["id"] == "p-new"
        assert r["total_papers"] == 3
        assert r["missing_published_date"] == 0

    def test_missing_published_dates_not_in_range(self, db_conn):
        _insert_paper(db_conn, pid="p-has", ingested=date(2026, 1, 1),
                      published=date(2022, 6, 1))
        _insert_paper(db_conn, pid="p-nopub", ingested=date(2026, 1, 2),
                      published=None)

        r = get_paper_date_range(db_conn)
        assert r["oldest_published"]["id"] == "p-has"
        assert r["newest_published"]["id"] == "p-has"
        assert r["missing_published_date"] == 1

    def test_ingested_range_uses_all_papers(self, db_conn):
        _insert_paper(db_conn, pid="p-1", ingested=date(2026, 1, 1))
        _insert_paper(db_conn, pid="p-2", ingested=date(2026, 4, 15))
        r = get_paper_date_range(db_conn)
        assert r["oldest_ingested"]["id"] == "p-1"
        assert r["newest_ingested"]["id"] == "p-2"


class TestGetPollStalenessBuckets:
    def test_empty_db(self, db_conn):
        r = get_poll_staleness_buckets(db_conn, now="2026-04-19T00:00:00+00:00")
        assert r["total_non_pruned"] == 0
        assert r["stale_over_week"] == 0
        # 1 never-polled bucket + 5 age buckets
        assert len(r["buckets"]) == 6
        assert all(b["count"] == 0 for b in r["buckets"])

    def test_bucket_boundaries(self, db_conn):
        now = date(2026, 4, 19)
        # Never polled
        _insert_paper(db_conn, pid="never", ingested=now - timedelta(days=5))
        # 3 days ago -> "< 1 week"
        _insert_paper(db_conn, pid="fresh", ingested=now - timedelta(days=10),
                      last_poll=now - timedelta(days=3))
        # 10 days ago -> "1–2 weeks"
        _insert_paper(db_conn, pid="ten", ingested=now - timedelta(days=30),
                      last_poll=now - timedelta(days=10))
        # 20 days ago -> "2–4 weeks"
        _insert_paper(db_conn, pid="twenty", ingested=now - timedelta(days=40),
                      last_poll=now - timedelta(days=20))
        # 40 days ago -> "4–8 weeks"
        _insert_paper(db_conn, pid="forty", ingested=now - timedelta(days=60),
                      last_poll=now - timedelta(days=40))
        # 90 days ago -> "8+ weeks"
        _insert_paper(db_conn, pid="ninety", ingested=now - timedelta(days=120),
                      last_poll=now - timedelta(days=90))

        r = get_poll_staleness_buckets(db_conn, now=_iso(now))
        by_label = {b["label"]: b["count"] for b in r["buckets"]}
        assert by_label["Never polled"] == 1
        assert by_label["< 1 week"] == 1
        assert by_label["1–2 weeks"] == 1
        assert by_label["2–4 weeks"] == 1
        assert by_label["4–8 weeks"] == 1
        assert by_label["8+ weeks"] == 1
        assert r["total_non_pruned"] == 6
        # Never polled + 4 buckets >= 7 days = 5
        assert r["stale_over_week"] == 5

    def test_pruned_papers_excluded(self, db_conn):
        now = date(2026, 4, 19)
        _insert_paper(db_conn, pid="p-active", ingested=now - timedelta(days=30),
                      last_poll=now - timedelta(days=10))
        _insert_paper(db_conn, pid="p-pruned", ingested=now - timedelta(days=30),
                      last_poll=now - timedelta(days=10), status="pruned")

        r = get_poll_staleness_buckets(db_conn, now=_iso(now))
        assert r["total_non_pruned"] == 1

    def test_exact_seven_day_boundary_is_stale(self, db_conn):
        """7 days → counts as stale (>=7), not fresh."""
        now = date(2026, 4, 19)
        _insert_paper(db_conn, pid="seven", ingested=now - timedelta(days=30),
                      last_poll=now - timedelta(days=7))
        r = get_poll_staleness_buckets(db_conn, now=_iso(now))
        by_label = {b["label"]: b["count"] for b in r["buckets"]}
        assert by_label["< 1 week"] == 0
        assert by_label["1–2 weeks"] == 1
        assert r["stale_over_week"] == 1


class TestGetMonthlyIngestCounts:
    def test_zero_fills_missing_months(self, db_conn):
        today = date(2026, 4, 19)
        _insert_paper(db_conn, pid="p-1", ingested=date(2026, 2, 10))
        _insert_paper(db_conn, pid="p-2", ingested=date(2026, 4, 5))

        out = get_monthly_ingest_counts(db_conn, months=6, today=today)
        assert len(out) == 6
        # oldest-first
        months = [x["month"] for x in out]
        assert months == ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04"]
        by_month = {x["month"]: x["count"] for x in out}
        assert by_month["2026-02"] == 1
        assert by_month["2026-04"] == 1
        assert by_month["2025-11"] == 0
        assert by_month["2026-03"] == 0

    def test_length_matches_months_param(self, db_conn):
        assert len(get_monthly_ingest_counts(db_conn, months=1)) == 1
        assert len(get_monthly_ingest_counts(db_conn, months=12)) == 12


class TestGetWeeklyCitationUpdates:
    def test_zero_fills_missing_weeks(self, db_conn):
        today = date(2026, 4, 19)  # Sunday
        _insert_paper(db_conn, pid="p-1", ingested=date(2026, 1, 1))
        # Manually insert a snapshot on a specific date
        db_conn.execute(
            "INSERT INTO citation_snapshots (paper_id, checked_at, total_citations, source) "
            "VALUES (?, ?, ?, ?)",
            ("p-1", _iso(date(2026, 4, 15)), 10, "semantic_scholar"),
        )
        # And one from 6 weeks ago
        db_conn.execute(
            "INSERT INTO citation_snapshots (paper_id, checked_at, total_citations, source) "
            "VALUES (?, ?, ?, ?)",
            ("p-1", _iso(date(2026, 3, 8)), 5, "openalex"),
        )

        out = get_weekly_citation_updates(db_conn, weeks=8, today=today)
        assert len(out) == 8
        # Oldest-first, weekly Monday spacing
        assert out[-1]["week_start"] == "2026-04-13"  # Monday of week containing today
        assert out[0]["week_start"] == "2026-02-23"

        by_week = {x["week_start"]: x["count"] for x in out}
        # 2026-04-15 is Wednesday → Monday 2026-04-13
        assert by_week["2026-04-13"] == 1
        # 2026-03-08 is Sunday → Monday 2026-03-02
        assert by_week["2026-03-02"] == 1

    def test_length_matches_weeks_param(self, db_conn):
        assert len(get_weekly_citation_updates(db_conn, weeks=1)) == 1
        assert len(get_weekly_citation_updates(db_conn, weeks=26)) == 26


# ---------------------------------------------------------------------------
# Route / template tests
# ---------------------------------------------------------------------------

class TestStatsRoute:
    def test_returns_200(self, client):
        resp = client.get("/stats")
        assert resp.status_code == 200

    def test_returns_html(self, client):
        resp = client.get("/stats")
        assert "text/html" in resp.headers["content-type"]

    def test_page_title(self, client):
        resp = client.get("/stats")
        assert b"Database Stats" in resp.content

    def test_nav_link_present(self, client):
        resp = client.get("/stats")
        # Tab link in the nav
        assert b'href="/stats"' in resp.content
        assert b">\n                        Stats\n" in resp.content

    def test_nav_link_active_on_stats_page(self, client):
        resp = client.get("/stats")
        # aria-current="page" should be on the Stats link
        content = resp.content.decode()
        idx = content.index('href="/stats"')
        # Look at the snippet around the stats link
        snippet = content[idx:idx + 200]
        assert 'aria-current="page"' in snippet

    def test_contains_three_section_headers(self, client):
        resp = client.get("/stats")
        assert b"Paper date coverage" in resp.content
        assert b"Last poll freshness" in resp.content
        assert b"Papers ingested per month" in resp.content
        assert b"Citation updates per week" in resp.content

    def test_contains_three_chart_canvases(self, client, web_config):
        # pollChart is hidden when there are no non-pruned papers, so we need
        # at least one paper for all three canvases to render.
        with get_connection(web_config.db_path) as conn:
            _insert_paper(conn, pid="p-1", ingested=date.today())

        resp = client.get("/stats")
        assert b'id="pollChart"' in resp.content
        assert b'id="monthlyChart"' in resp.content
        assert b'id="weeklyChart"' in resp.content


class TestStatsEmptyDatabase:
    def test_oldest_newest_show_dash(self, client):
        resp = client.get("/stats")
        # With no papers, both hero cards fall back to em-dash
        assert b"No papers with a publication date yet." in resp.content

    def test_non_pruned_zero_shows_empty_message(self, client):
        resp = client.get("/stats")
        assert b"No non-pruned papers to poll." in resp.content


class TestStatsWithData:
    def test_shows_oldest_and_newest(self, client, web_config):
        with get_connection(web_config.db_path) as conn:
            _insert_paper(conn, pid="oldest", ingested=date(2026, 1, 1),
                          published=date(2020, 1, 15))
            _insert_paper(conn, pid="newest", ingested=date(2026, 1, 2),
                          published=date(2024, 11, 30))

        resp = client.get("/stats")
        assert b"2020-01-15" in resp.content
        assert b"2024-11-30" in resp.content
        assert b"/papers/oldest" in resp.content
        assert b"/papers/newest" in resp.content

    def test_stale_count_headline(self, client, web_config):
        # One fresh, two stale
        now = date.today()
        with get_connection(web_config.db_path) as conn:
            _insert_paper(conn, pid="fresh", ingested=now - timedelta(days=30),
                          last_poll=now - timedelta(days=2))
            _insert_paper(conn, pid="old1", ingested=now - timedelta(days=30),
                          last_poll=now - timedelta(days=10))
            _insert_paper(conn, pid="never", ingested=now - timedelta(days=5))

        resp = client.get("/stats")
        # "2 of 3 non-pruned papers haven't been polled..."
        assert b"<strong>2</strong> of 3 non-pruned papers" in resp.content

    def test_chart_data_serialized_as_json(self, client, web_config):
        with get_connection(web_config.db_path) as conn:
            _insert_paper(conn, pid="p-1", ingested=date.today())

        resp = client.get("/stats")
        # The chart JS block should contain the JSON-serialized arrays
        assert b"const pollBuckets = [" in resp.content
        assert b"const monthly     = [" in resp.content
        assert b"const weekly      = [" in resp.content
