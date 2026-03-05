"""Tests for the settings page and trigger routes."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from src.config import AppConfig
from src.db import get_connection, init_db, now_utc, upsert_paper
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


class TestSettingsRoute:
    def test_returns_200(self, client):
        resp = client.get("/settings")
        assert resp.status_code == 200

    def test_returns_html(self, client):
        resp = client.get("/settings")
        assert "text/html" in resp.headers["content-type"]

    def test_page_title(self, client):
        resp = client.get("/settings")
        assert b"Settings" in resp.content

    def test_shows_configuration_section(self, client):
        resp = client.get("/settings")
        assert b"Configuration" in resp.content

    def test_shows_manual_triggers_section(self, client):
        resp = client.get("/settings")
        assert b"Manual Triggers" in resp.content

    def test_shows_ingestion_history_section(self, client):
        resp = client.get("/settings")
        assert b"Ingestion History" in resp.content


class TestSettingsConfigDisplay:
    def test_shows_score_threshold(self, client):
        resp = client.get("/settings")
        assert b"Score Threshold" in resp.content
        assert b"60%" in resp.content

    def test_shows_schedule_cron(self, client):
        resp = client.get("/settings")
        assert b"0 8 * * 1" in resp.content

    def test_shows_cron_human_readable(self, client):
        resp = client.get("/settings")
        assert b"Every Monday" in resp.content

    def test_shows_citation_poll_schedule(self, client):
        resp = client.get("/settings")
        assert b"Citation Polling" in resp.content

    def test_shows_pruning_thresholds(self, client):
        resp = client.get("/settings")
        assert b"Pruning Thresholds" in resp.content
        assert b"Min Age" in resp.content

    def test_shows_promotion_thresholds(self, client):
        resp = client.get("/settings")
        assert b"Promotion Thresholds" in resp.content

    def test_shows_browser_settings(self, client):
        resp = client.get("/settings")
        assert b"Browser" in resp.content
        assert b"Profile Directory" in resp.content


class TestSettingsTriggerButtons:
    def test_shows_ingest_button(self, client):
        resp = client.get("/settings")
        assert b"Run Ingestion" in resp.content
        assert b"trigger-ingest" in resp.content

    def test_shows_poll_button(self, client):
        resp = client.get("/settings")
        assert b"Poll Citations" in resp.content
        assert b"trigger-poll" in resp.content

    def test_shows_rules_button(self, client):
        resp = client.get("/settings")
        assert b"Run Rules" in resp.content
        assert b"trigger-rules" in resp.content

    def test_shows_backfill_button(self, client):
        resp = client.get("/settings")
        assert b"Run Backfill" in resp.content
        assert b"trigger-backfill" in resp.content

    def test_shows_collect_button(self, client):
        resp = client.get("/settings")
        assert b"Collect Citations" in resp.content
        assert b"trigger-collect" in resp.content


class TestSettingsRunHistory:
    def test_empty_history_message(self, client):
        resp = client.get("/settings")
        assert b"No ingestion runs recorded yet" in resp.content

    def test_shows_run_history_with_data(self, client, web_config):
        with get_connection(web_config.db_path) as conn:
            from src.db import create_ingestion_run, update_ingestion_run
            run_id = create_ingestion_run(conn)
            update_ingestion_run(conn, run_id, papers_found=5, papers_ingested=3, status="completed")

        resp = client.get("/settings")
        assert b"Completed" in resp.content
        assert b"run-history-body" in resp.content


class TestTriggerRulesEndpoint:
    def test_returns_200(self, client):
        resp = client.post("/partials/trigger-rules")
        assert resp.status_code == 200

    def test_returns_html(self, client):
        resp = client.post("/partials/trigger-rules")
        assert "text/html" in resp.headers["content-type"]

    def test_returns_success_message(self, client):
        resp = client.post("/partials/trigger-rules")
        assert b"trigger-success" in resp.content or b"trigger-error" in resp.content

    def test_empty_db_shows_zero_evaluated(self, client):
        resp = client.post("/partials/trigger-rules")
        assert b"0 evaluated" in resp.content

    def test_prune_eligible_paper(self, client, web_config):
        with get_connection(web_config.db_path) as conn:
            upsert_paper(conn, {
                "id": "old-paper",
                "title": "Old Paper",
                "authors": "[]",
                "ingested_at": "2024-01-01T00:00:00+00:00",
                "citation_count": 1,
                "citation_velocity": 0.1,
                "status": "active",
            })
        resp = client.post("/partials/trigger-rules")
        assert b"trigger-success" in resp.content


class TestTriggerIngestEndpoint:
    def test_returns_200_with_mocked_ingest(self, web_config):
        """Ingest trigger must mock run_ingest to avoid actual browser launch."""
        async def mock_run_ingest(config):
            return {"papers_found": 5, "papers_ingested": 3, "run_id": 1}

        with patch("src.ingestion.orchestrate.run_ingest", new=mock_run_ingest):
            app = create_app(web_config)
            c = TestClient(app, follow_redirects=True)
            resp = c.post("/partials/trigger-ingest")
        assert resp.status_code == 200

    def test_returns_success_html_with_mocked_ingest(self, web_config):
        async def mock_run_ingest(config):
            return {"papers_found": 5, "papers_ingested": 3, "run_id": 1}

        with patch("src.ingestion.orchestrate.run_ingest", new=mock_run_ingest):
            app = create_app(web_config)
            c = TestClient(app, follow_redirects=True)
            resp = c.post("/partials/trigger-ingest")
        assert b"trigger-success" in resp.content
        assert b"Found 5 papers" in resp.content

    def test_returns_error_html_on_exception(self, web_config):
        async def failing_ingest(config):
            raise RuntimeError("Browser failed")

        with patch("src.ingestion.orchestrate.run_ingest", new=failing_ingest):
            app = create_app(web_config)
            c = TestClient(app, follow_redirects=True)
            resp = c.post("/partials/trigger-ingest")
        assert b"trigger-error" in resp.content


class TestTriggerPollEndpoint:
    def test_returns_200_with_mock(self, web_config):
        async def mock_poll(config, db_path):
            return 0

        with patch("src.citations.poller.run_citation_poll", new=mock_poll):
            app = create_app(web_config)
            c = TestClient(app, follow_redirects=True)
            resp = c.post("/partials/trigger-poll")
        assert resp.status_code == 200

    def test_returns_html(self, web_config):
        async def mock_poll(config, db_path):
            return 3

        with patch("src.citations.poller.run_citation_poll", new=mock_poll):
            app = create_app(web_config)
            c = TestClient(app, follow_redirects=True)
            resp = c.post("/partials/trigger-poll")
        assert "text/html" in resp.headers["content-type"]
        assert b"Updated 3 papers" in resp.content


class TestTriggerBackfillEndpoint:
    def test_returns_200_with_mock(self, web_config):
        from src.ingestion.backfill import BackfillResult

        async def mock_backfill(config):
            r = BackfillResult()
            r.dates_processed = 2
            r.papers_ingested = 4
            return r

        with patch("src.ingestion.backfill.run_backfill", new=mock_backfill):
            app = create_app(web_config)
            c = TestClient(app, follow_redirects=True)
            resp = c.post("/partials/trigger-backfill")
        assert resp.status_code == 200
        assert b"Backfilled 2 dates" in resp.content


class TestTriggerCollectEndpoint:
    def test_returns_200_with_mock(self, web_config):
        async def mock_collect(config, db_path):
            return 5

        with patch("src.citations.poller.collect_citations_for_unpolled", new=mock_collect):
            app = create_app(web_config)
            c = TestClient(app, follow_redirects=True)
            resp = c.post("/partials/trigger-collect")
        assert resp.status_code == 200
        assert b"Collected citations for 5 papers" in resp.content
