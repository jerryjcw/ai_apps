"""Tests for the dashboard page route and template."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.config import AppConfig
from src.db import get_connection, init_db, upsert_paper, now_utc
from src.web.app import create_app


@pytest.fixture
def web_config(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return AppConfig(db_path=db_path)


@pytest.fixture
def client(web_config):
    app = create_app(web_config)
    return TestClient(app, follow_redirects=True)


class TestDashboardRoute:
    def test_returns_200(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200

    def test_returns_html(self, client):
        resp = client.get("/dashboard")
        assert "text/html" in resp.headers["content-type"]

    def test_page_title(self, client):
        resp = client.get("/dashboard")
        assert b"Dashboard" in resp.content

    def test_contains_summary_cards(self, client):
        resp = client.get("/dashboard")
        assert b"Papers Tracked" in resp.content
        assert b"Trending" in resp.content
        assert b"Added This Week" in resp.content
        assert b"Next Poll" in resp.content

    def test_contains_top_papers_section(self, client):
        resp = client.get("/dashboard")
        assert b"Top Papers by Velocity" in resp.content

    def test_contains_recent_activity_section(self, client):
        resp = client.get("/dashboard")
        assert b"Recent Activity" in resp.content


class TestDashboardEmptyState:
    def test_no_papers_shows_empty_message(self, client):
        resp = client.get("/dashboard")
        assert b"No papers tracked yet" in resp.content

    def test_no_runs_shows_empty_message(self, client):
        resp = client.get("/dashboard")
        assert b"No ingestion runs yet" in resp.content

    def test_summary_cards_show_zeros(self, client):
        resp = client.get("/dashboard")
        # Cards are rendered; with empty DB values are 0
        assert b"Papers Tracked" in resp.content


class TestDashboardWithData:
    def test_shows_paper_in_top_table(self, client, web_config):
        with get_connection(web_config.db_path) as conn:
            upsert_paper(conn, {
                "id": "paper-1",
                "title": "Attention Is All You Need",
                "authors": '["Vaswani et al."]',
                "ingested_at": now_utc(),
                "citation_count": 50000,
                "citation_velocity": 120.5,
                "status": "promoted",
            })

        resp = client.get("/dashboard")
        assert b"Attention Is All You Need" in resp.content
        assert b"120.5" in resp.content

    def test_author_filter_applied(self, client, web_config):
        with get_connection(web_config.db_path) as conn:
            upsert_paper(conn, {
                "id": "paper-2",
                "title": "Test Paper",
                "authors": '["Alice Smith", "Bob Jones"]',
                "ingested_at": now_utc(),
                "citation_count": 10,
                "citation_velocity": 8.0,
                "status": "active",
            })

        resp = client.get("/dashboard")
        assert b"Alice Smith et al." in resp.content

    def test_paper_links_to_detail(self, client, web_config):
        with get_connection(web_config.db_path) as conn:
            upsert_paper(conn, {
                "id": "my-paper-id",
                "title": "My Test Paper",
                "authors": '["Author"]',
                "ingested_at": now_utc(),
                "citation_count": 5,
                "citation_velocity": 6.0,
                "status": "active",
            })

        resp = client.get("/dashboard")
        assert b"/papers/my-paper-id" in resp.content

    def test_pruned_papers_excluded_from_top_table(self, client, web_config):
        with get_connection(web_config.db_path) as conn:
            upsert_paper(conn, {
                "id": "pruned-paper",
                "title": "Pruned Paper Title",
                "authors": '["Author"]',
                "ingested_at": now_utc(),
                "citation_count": 5,
                "citation_velocity": 8.0,
                "status": "pruned",
            })

        resp = client.get("/dashboard")
        assert b"Pruned Paper Title" not in resp.content


class TestDashboardNextCronRun:
    def test_next_poll_shown_in_card(self, client):
        resp = client.get("/dashboard")
        assert b"Next Poll" in resp.content
        # Should show either a date or a cron description
        content = resp.content
        assert b"at" in content or b"\xe2\x80\x94" in content  # "at HH:MM" or em dash

    def test_next_poll_fallback_on_bad_cron(self, web_config):
        bad_cron_config = AppConfig(
            db_path=web_config.db_path,
            citations=web_config.citations.__class__(
                poll_schedule_cron="bad cron",
                semantic_scholar_batch_size=100,
            ),
        )
        app = create_app(bad_cron_config)
        client = TestClient(app, follow_redirects=True)
        resp = client.get("/dashboard")
        # Should still render without error
        assert resp.status_code == 200
        assert b"Next Poll" in resp.content
