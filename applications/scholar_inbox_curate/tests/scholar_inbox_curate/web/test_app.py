"""Tests for src.web.app — FastAPI web application endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.config import AppConfig
from src.db import get_connection, init_db, upsert_paper, now_utc
from src.web.app import create_app


@pytest.fixture
def web_config(tmp_path):
    """Create a minimal AppConfig with a temp database."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return AppConfig(db_path=db_path)


@pytest.fixture
def client(web_config):
    """Create a FastAPI test client."""
    app = create_app(web_config)
    return TestClient(app)


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestStats:
    def test_stats_empty_db(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_papers"] == 0

    def test_stats_with_papers(self, client, web_config):
        with get_connection(web_config.db_path) as conn:
            upsert_paper(conn, {
                "id": "p1", "title": "Test Paper", "authors": [],
                "ingested_at": now_utc(),
            })
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_papers"] == 1


class TestTrending:
    def test_trending_empty(self, client):
        resp = client.get("/api/trending")
        assert resp.status_code == 200
        assert resp.json() == []


class TestTriggerRules:
    def test_trigger_rules_empty_db(self, client):
        resp = client.post("/partials/trigger-rules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["papers_evaluated"] == 0
        assert data["papers_pruned"] == 0
        assert data["papers_promoted"] == 0

    def test_trigger_rules_prunes_eligible_paper(self, client, web_config):
        with get_connection(web_config.db_path) as conn:
            upsert_paper(conn, {
                "id": "old_paper",
                "title": "Old Low-Citation Paper",
                "authors": [],
                "ingested_at": "2024-01-01T00:00:00+00:00",
                "citation_count": 1,
                "citation_velocity": 0.1,
            })

        resp = client.post("/partials/trigger-rules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["papers_pruned"] == 1

    def test_trigger_rules_promotes_eligible_paper(self, client, web_config):
        with get_connection(web_config.db_path) as conn:
            upsert_paper(conn, {
                "id": "hot_paper",
                "title": "Highly Cited Paper",
                "authors": [],
                "ingested_at": "2025-06-01T00:00:00+00:00",
                "citation_count": 100,
                "citation_velocity": 15.0,
            })

        resp = client.post("/partials/trigger-rules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["papers_promoted"] == 1
