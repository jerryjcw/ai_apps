"""Tests for the paper list page and partial routes."""

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


def _add_paper(db_path, paper_id, title, status="active", velocity=5.0, authors='["Author"]'):
    with get_connection(db_path) as conn:
        upsert_paper(conn, {
            "id": paper_id,
            "title": title,
            "authors": authors,
            "ingested_at": now_utc(),
            "citation_count": 10,
            "citation_velocity": velocity,
            "status": status,
        })


class TestPaperListRoute:
    def test_returns_200(self, client):
        resp = client.get("/papers")
        assert resp.status_code == 200

    def test_returns_html(self, client):
        resp = client.get("/papers")
        assert "text/html" in resp.headers["content-type"]

    def test_page_title(self, client):
        resp = client.get("/papers")
        assert b"Papers" in resp.content

    def test_contains_filter_form(self, client):
        resp = client.get("/papers")
        assert b"paper-filters" in resp.content
        assert b"status" in resp.content
        assert b"Search" in resp.content

    def test_contains_table_headers(self, client):
        resp = client.get("/papers")
        assert b"Title" in resp.content
        assert b"Citations" in resp.content
        assert b"Velocity" in resp.content
        assert b"Status" in resp.content


class TestPaperListWithData:
    def test_shows_paper(self, client, web_config):
        _add_paper(web_config.db_path, "p1", "My Research Paper")
        resp = client.get("/papers")
        assert b"My Research Paper" in resp.content

    def test_paper_links_to_detail(self, client, web_config):
        _add_paper(web_config.db_path, "paper-abc", "Linked Paper")
        resp = client.get("/papers")
        assert b"/papers/paper-abc" in resp.content

    def test_author_filter_applied(self, client, web_config):
        _add_paper(web_config.db_path, "p2", "T", authors='["Alice Smith", "Bob"]')
        resp = client.get("/papers")
        assert b"Alice Smith et al." in resp.content

    def test_empty_state_no_papers(self, client):
        resp = client.get("/papers")
        assert b"No papers tracked yet" in resp.content

    def test_empty_state_no_filter_match(self, client, web_config):
        _add_paper(web_config.db_path, "p3", "Active Paper", status="active")
        resp = client.get("/papers?status=promoted")
        assert b"No papers match your filters" in resp.content


class TestPaperListFiltering:
    def test_status_filter_active(self, client, web_config):
        _add_paper(web_config.db_path, "a1", "Active Paper", status="active")
        _add_paper(web_config.db_path, "p1", "Pruned Paper", status="pruned")
        resp = client.get("/papers?status=active")
        assert b"Active Paper" in resp.content
        assert b"Pruned Paper" not in resp.content

    def test_status_filter_promoted(self, client, web_config):
        _add_paper(web_config.db_path, "pr1", "Promoted Paper", status="promoted")
        _add_paper(web_config.db_path, "a1", "Active Paper", status="active")
        resp = client.get("/papers?status=promoted")
        assert b"Promoted Paper" in resp.content
        assert b"Active Paper" not in resp.content

    def test_search_filter(self, client, web_config):
        _add_paper(web_config.db_path, "t1", "Transformer Architecture")
        _add_paper(web_config.db_path, "t2", "Diffusion Models")
        resp = client.get("/papers?q=Transformer")
        assert b"Transformer Architecture" in resp.content
        assert b"Diffusion Models" not in resp.content

    def test_invalid_sort_falls_back_to_default(self, client, web_config):
        _add_paper(web_config.db_path, "p1", "A Paper")
        resp = client.get("/papers?sort=malicious_col;DROP+TABLE")
        assert resp.status_code == 200

    def test_invalid_order_falls_back_to_desc(self, client, web_config):
        _add_paper(web_config.db_path, "p1", "A Paper")
        resp = client.get("/papers?order=INVALID")
        assert resp.status_code == 200

    def test_status_filter_preserved_in_select(self, client, web_config):
        _add_paper(web_config.db_path, "p1", "A Paper", status="promoted")
        resp = client.get("/papers?status=promoted")
        assert b'value="promoted"' in resp.content
        assert b"selected" in resp.content

    def test_search_query_preserved_in_input(self, client, web_config):
        _add_paper(web_config.db_path, "p1", "Transformer Paper")
        resp = client.get("/papers?q=Transformer")
        assert b'value="Transformer"' in resp.content


class TestPaperRowsPartial:
    def test_returns_200(self, client):
        resp = client.get("/partials/paper-rows")
        assert resp.status_code == 200

    def test_returns_html_partial(self, client, web_config):
        _add_paper(web_config.db_path, "p1", "Partial Paper")
        resp = client.get("/partials/paper-rows")
        assert b"Partial Paper" in resp.content
        # Should NOT contain full page structure
        assert b"<!DOCTYPE" not in resp.content
        assert b"<nav>" not in resp.content

    def test_filtering_works_in_partial(self, client, web_config):
        _add_paper(web_config.db_path, "a1", "Active Paper", status="active")
        _add_paper(web_config.db_path, "p1", "Pruned Paper", status="pruned")
        resp = client.get("/partials/paper-rows?status=active")
        assert b"Active Paper" in resp.content
        assert b"Pruned Paper" not in resp.content

    def test_pagination_shown_for_many_papers(self, client, web_config):
        for i in range(30):
            _add_paper(web_config.db_path, f"paper-{i}", f"Paper {i}", velocity=float(i))
        resp = client.get("/partials/paper-rows")
        assert b"Page 1 of 2" in resp.content

    def test_page_2_shows_different_papers(self, client, web_config):
        # Create 30 papers with different titles
        for i in range(30):
            _add_paper(web_config.db_path, f"paper-{i:02d}", f"Paper Title {i:02d}", velocity=float(i))
        resp1 = client.get("/partials/paper-rows?page=1")
        resp2 = client.get("/partials/paper-rows?page=2")
        # At least some content differs between pages
        assert resp1.content != resp2.content
