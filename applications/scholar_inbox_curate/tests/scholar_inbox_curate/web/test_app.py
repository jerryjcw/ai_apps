"""Tests for src.web.app — FastAPI web application structure and base routes."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.config import AppConfig
from src.db import get_connection, init_db
from src.web.app import create_app


@pytest.fixture
def web_config(tmp_path):
    """Create a minimal AppConfig with a temp database."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return AppConfig(db_path=db_path)


@pytest.fixture
def client(web_config):
    """Create a FastAPI test client (redirects not followed by default)."""
    app = create_app(web_config)
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def client_follow(web_config):
    """Create a FastAPI test client that follows redirects."""
    app = create_app(web_config)
    return TestClient(app, follow_redirects=True)


class TestAppFactory:
    def test_create_app_returns_fastapi(self, web_config):
        app = create_app(web_config)
        assert isinstance(app, FastAPI)

    def test_config_stored_on_state(self, web_config):
        app = create_app(web_config)
        assert app.state.config is web_config

    def test_db_path_stored_on_state(self, web_config):
        app = create_app(web_config)
        assert app.state.db_path == web_config.db_path

    def test_docs_url_disabled(self, web_config):
        app = create_app(web_config)
        assert app.docs_url is None

    def test_redoc_url_disabled(self, web_config):
        app = create_app(web_config)
        assert app.redoc_url is None


class TestRootRedirect:
    def test_root_redirects_to_dashboard(self, client):
        resp = client.get("/")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/dashboard"


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "scholar-inbox-curate"

    def test_health_db_unreachable(self, web_config, tmp_path):
        bad_config = AppConfig(db_path=str(tmp_path / "nonexistent" / "db.sqlite"))
        app = create_app(bad_config)
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/health")
        assert resp.status_code == 503
        assert resp.json()["status"] == "error"


class TestPageRoutes:
    def test_dashboard_returns_html(self, client_follow):
        resp = client_follow.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_dashboard_contains_nav(self, client_follow):
        resp = client_follow.get("/dashboard")
        assert b"Dashboard" in resp.content
        assert b"Papers" in resp.content
        assert b"Settings" in resp.content

    def test_papers_returns_html(self, client_follow):
        resp = client_follow.get("/papers")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_settings_returns_html(self, client_follow):
        resp = client_follow.get("/settings")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_paper_detail_returns_html(self, web_config):
        from src.db import get_connection, upsert_paper, now_utc
        with get_connection(web_config.db_path) as conn:
            upsert_paper(conn, {
                "id": "arxiv-1234-5678",
                "title": "Test Paper",
                "authors": "[]",
                "ingested_at": now_utc(),
            })
        app = create_app(web_config)
        client = TestClient(app, follow_redirects=True)
        resp = client.get("/papers/arxiv-1234-5678")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


class TestBaseTemplate:
    def test_base_template_includes_pico_css(self, client_follow):
        resp = client_follow.get("/dashboard")
        assert b"picocss" in resp.content

    def test_base_template_includes_htmx(self, client_follow):
        resp = client_follow.get("/dashboard")
        assert b"htmx.org" in resp.content

    def test_base_template_includes_custom_css(self, client_follow):
        resp = client_follow.get("/dashboard")
        assert b"style.css" in resp.content

    def test_base_template_data_theme_auto(self, client_follow):
        resp = client_follow.get("/dashboard")
        assert b'data-theme="auto"' in resp.content

    def test_dashboard_nav_link_active(self, client_follow):
        resp = client_follow.get("/dashboard")
        assert b'aria-current="page"' in resp.content

    def test_papers_nav_link_active(self, client_follow):
        resp = client_follow.get("/papers")
        assert b'aria-current="page"' in resp.content

    def test_settings_nav_link_active(self, client_follow):
        resp = client_follow.get("/settings")
        assert b'aria-current="page"' in resp.content


class TestPartialRoutes:
    def test_paper_rows_partial_returns_html(self, client):
        resp = client.get("/partials/paper-rows", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_paper_rows_redirects_without_hx_header(self, client):
        """Direct browser access to partial should redirect to full page."""
        resp = client.get("/partials/paper-rows", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/papers"

    def test_trigger_rules_returns_html(self, client):
        resp = client.post("/partials/trigger-rules")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_paper_rows_accepts_query_params(self, client):
        resp = client.get(
            "/partials/paper-rows?q=test&status=active&sort=score&order=desc&page=2",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200


class TestPaginationPreservesSort:
    """Pagination links must carry current sort/order so page changes don't reset sort."""

    @pytest.fixture
    def client_with_many_papers(self, web_config):
        """Insert 30 papers (> PAGE_SIZE=25) so pagination appears."""
        with get_connection(web_config.db_path) as conn:
            for i in range(30):
                conn.execute(
                    """INSERT INTO papers
                       (id, title, authors, status, citation_velocity, ingested_at)
                       VALUES (?, ?, ?, 'active', ?, datetime('now', ?))""",
                    (f"paper-{i}", f"Paper {i}", "Author A", float(i), f"-{i} minutes"),
                )
        app = create_app(web_config)
        return TestClient(app, follow_redirects=False)

    def test_partial_pagination_includes_sort_params(self, client_with_many_papers):
        """When sort=ingested_at, pagination links must include that sort value."""
        resp = client_with_many_papers.get(
            "/partials/paper-rows?sort=ingested_at&order=desc&page=1",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        body = resp.text
        # "Next" link must carry sort=ingested_at
        assert '"sort": "ingested_at"' in body
        assert '"order": "desc"' in body
        # Page 2 link must also carry sort
        assert '"page": "2"' in body

    def test_pagination_does_not_revert_to_default_sort(self, client_with_many_papers):
        """Page 2 with sort=ingested_at must still render sorted by ingested_at."""
        resp = client_with_many_papers.get(
            "/partials/paper-rows?sort=ingested_at&order=asc&page=2",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        body = resp.text
        # The column header should show ingested_at as the active sort
        assert 'aria-sort=' in body
        # Previous link must preserve sort
        assert '"sort": "ingested_at"' in body
        assert '"order": "asc"' in body


class TestErrorHandlers:
    def test_404_returns_html_error_page(self, client):
        resp = client.get("/nonexistent-route")
        assert resp.status_code == 404
        assert "text/html" in resp.headers["content-type"]
        assert b"404" in resp.content

    def test_404_page_has_back_link(self, client):
        resp = client.get("/nonexistent-route")
        assert b"/dashboard" in resp.content
