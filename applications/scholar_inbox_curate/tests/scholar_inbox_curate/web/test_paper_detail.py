"""Tests for the paper detail page and status update route."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.config import AppConfig
from src.db import get_connection, init_db, insert_snapshot, now_utc, upsert_paper
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


def _add_paper(db_path, paper_id="paper-1", title="Test Paper", status="active",
               authors='["Alice Smith", "Bob Jones"]'):
    with get_connection(db_path) as conn:
        upsert_paper(conn, {
            "id": paper_id,
            "title": title,
            "authors": authors,
            "ingested_at": now_utc(),
            "citation_count": 42,
            "citation_velocity": 5.3,
            "status": status,
            "scholar_inbox_score": 85.0,
            "abstract": "This is an abstract.",
        })


class TestPaperDetailRoute:
    def test_returns_200(self, client, web_config):
        _add_paper(web_config.db_path)
        resp = client.get("/papers/paper-1")
        assert resp.status_code == 200

    def test_returns_html(self, client, web_config):
        _add_paper(web_config.db_path)
        resp = client.get("/papers/paper-1")
        assert "text/html" in resp.headers["content-type"]

    def test_shows_paper_title(self, client, web_config):
        _add_paper(web_config.db_path, title="Attention Is All You Need")
        resp = client.get("/papers/paper-1")
        assert b"Attention Is All You Need" in resp.content

    def test_404_for_unknown_paper(self, client):
        resp = client.get("/papers/nonexistent-id")
        assert resp.status_code == 404
        assert b"404" in resp.content

    def test_shows_authors(self, client, web_config):
        _add_paper(web_config.db_path, authors='["Alice Smith", "Bob Jones"]')
        resp = client.get("/papers/paper-1")
        assert b"Alice Smith" in resp.content
        assert b"Bob Jones" in resp.content

    def test_shows_score_badge(self, client, web_config):
        _add_paper(web_config.db_path)
        resp = client.get("/papers/paper-1")
        assert b"85" in resp.content

    def test_shows_stats_sidebar(self, client, web_config):
        _add_paper(web_config.db_path)
        resp = client.get("/papers/paper-1")
        assert b"Current Citations" in resp.content
        assert b"Velocity" in resp.content
        assert b"First Tracked" in resp.content

    def test_shows_citation_history_section(self, client, web_config):
        _add_paper(web_config.db_path)
        resp = client.get("/papers/paper-1")
        assert b"Citation History" in resp.content

    def test_no_snapshots_shows_empty_message(self, client, web_config):
        _add_paper(web_config.db_path)
        resp = client.get("/papers/paper-1")
        assert b"No citation data yet" in resp.content

    def test_shows_abstract_when_present(self, client, web_config):
        _add_paper(web_config.db_path)
        resp = client.get("/papers/paper-1")
        assert b"Show abstract" in resp.content


class TestPaperDetailWithSnapshots:
    def test_one_snapshot_shows_static_count(self, client, web_config):
        _add_paper(web_config.db_path)
        with get_connection(web_config.db_path) as conn:
            insert_snapshot(conn, "paper-1", 100, "semantic_scholar")
        resp = client.get("/papers/paper-1")
        assert b"100" in resp.content
        assert b"More data points needed for a chart" in resp.content

    def test_two_snapshots_shows_chart_canvas(self, client, web_config):
        _add_paper(web_config.db_path)
        with get_connection(web_config.db_path) as conn:
            insert_snapshot(conn, "paper-1", 50, "semantic_scholar")
            insert_snapshot(conn, "paper-1", 100, "semantic_scholar")
        resp = client.get("/papers/paper-1")
        assert b"citationChart" in resp.content
        assert b"chart.js" in resp.content

    def test_snapshot_count_shown(self, client, web_config):
        _add_paper(web_config.db_path)
        with get_connection(web_config.db_path) as conn:
            insert_snapshot(conn, "paper-1", 10, "semantic_scholar")
            insert_snapshot(conn, "paper-1", 20, "semantic_scholar")
            insert_snapshot(conn, "paper-1", 30, "semantic_scholar")
        resp = client.get("/papers/paper-1")
        assert b"Citation Snapshots (3)" in resp.content

    def test_snapshots_json_in_script(self, client, web_config):
        _add_paper(web_config.db_path)
        with get_connection(web_config.db_path) as conn:
            insert_snapshot(conn, "paper-1", 50, "semantic_scholar")
            insert_snapshot(conn, "paper-1", 100, "semantic_scholar")
        resp = client.get("/papers/paper-1")
        assert b'"total"' in resp.content


class TestPaperDetailStatusSection:
    def test_shows_status_badge(self, client, web_config):
        _add_paper(web_config.db_path, status="active")
        resp = client.get("/papers/paper-1")
        assert b"status-active" in resp.content

    def test_active_paper_shows_promote_button(self, client, web_config):
        _add_paper(web_config.db_path, status="active")
        resp = client.get("/papers/paper-1")
        assert b"Promote" in resp.content

    def test_active_paper_shows_prune_button(self, client, web_config):
        _add_paper(web_config.db_path, status="active")
        resp = client.get("/papers/paper-1")
        assert b"Prune" in resp.content

    def test_pruned_paper_shows_restore_button(self, client, web_config):
        _add_paper(web_config.db_path, status="pruned")
        resp = client.get("/papers/paper-1")
        assert b"Restore to Active" in resp.content

    def test_promoted_paper_shows_demote_button(self, client, web_config):
        _add_paper(web_config.db_path, status="promoted")
        resp = client.get("/papers/paper-1")
        assert b"Demote to Active" in resp.content


class TestUpdateStatusRoute:
    def test_promote_paper(self, client, web_config):
        _add_paper(web_config.db_path, status="active")
        resp = client.post("/papers/paper-1/status", data={"status": "promoted"})
        assert resp.status_code == 200
        assert b"status-promoted" in resp.content

    def test_prune_paper(self, client, web_config):
        _add_paper(web_config.db_path, status="active")
        resp = client.post("/papers/paper-1/status", data={"status": "pruned"})
        assert resp.status_code == 200
        assert b"status-pruned" in resp.content

    def test_restore_paper(self, client, web_config):
        _add_paper(web_config.db_path, status="pruned")
        resp = client.post("/papers/paper-1/status", data={"status": "active"})
        assert resp.status_code == 200
        assert b"status-active" in resp.content

    def test_update_status_returns_partial_only(self, client, web_config):
        _add_paper(web_config.db_path, status="active")
        resp = client.post("/papers/paper-1/status", data={"status": "promoted"})
        assert b"<!DOCTYPE" not in resp.content
        assert b"status-section" in resp.content

    def test_invalid_status_falls_back(self, client, web_config):
        _add_paper(web_config.db_path, status="active")
        resp = client.post("/papers/paper-1/status", data={"status": "unknown_status"})
        assert resp.status_code == 200

    def test_update_nonexistent_paper(self, client):
        resp = client.post("/papers/nonexistent/status", data={"status": "promoted"})
        assert resp.status_code == 404

    def test_status_persisted_in_db(self, client, web_config):
        _add_paper(web_config.db_path, status="active")
        client.post("/papers/paper-1/status", data={"status": "promoted"})
        from src.db import get_paper
        with get_connection(web_config.db_path) as conn:
            paper = get_paper(conn, "paper-1")
        assert paper["status"] == "promoted"
        assert paper["manual_status"] == 1
