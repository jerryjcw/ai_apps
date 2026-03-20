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


def _add_paper(db_path, paper_id, title, status="active", velocity=5.0, authors='["Author"]', abstract=None):
    paper = {
        "id": paper_id,
        "title": title,
        "authors": authors,
        "ingested_at": now_utc(),
        "citation_count": 10,
        "citation_velocity": velocity,
        "status": status,
    }
    if abstract is not None:
        paper["abstract"] = abstract
    with get_connection(db_path) as conn:
        upsert_paper(conn, paper)


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

    def test_multi_word_search_matches_both_words(self, client, web_config):
        _add_paper(web_config.db_path, "d1", "Video Generation with Latent Diffusion Models")
        _add_paper(web_config.db_path, "d2", "Diffusion Policies for Robotics")
        _add_paper(web_config.db_path, "d3", "Video Compression Algorithms")
        resp = client.get("/papers?q=Diffusion+Video")
        assert b"Video Generation with Latent Diffusion" in resp.content
        assert b"Diffusion Policies" not in resp.content
        assert b"Video Compression" not in resp.content

    def test_multi_word_search_excludes_partial_match(self, client, web_config):
        _add_paper(web_config.db_path, "d1", "Only Diffusion Here")
        resp = client.get("/papers?q=Diffusion+Video")
        assert b"Only Diffusion Here" not in resp.content

    def test_multi_word_search_across_fields(self, client, web_config):
        _add_paper(web_config.db_path, "d1", "Novel Diffusion Approach",
                   abstract="Applied to video synthesis tasks")
        _add_paper(web_config.db_path, "d2", "Unrelated Paper", abstract="Nothing here")
        resp = client.get("/papers?q=Diffusion+video")
        assert b"Novel Diffusion Approach" in resp.content
        assert b"Unrelated Paper" not in resp.content

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
    """Tests for the HTMX partial endpoint (with HX-Request header)."""

    HTMX_HEADERS = {"HX-Request": "true"}

    def test_returns_200(self, client):
        resp = client.get("/partials/paper-rows", headers=self.HTMX_HEADERS)
        assert resp.status_code == 200

    def test_returns_html_partial(self, client, web_config):
        _add_paper(web_config.db_path, "p1", "Partial Paper")
        resp = client.get("/partials/paper-rows", headers=self.HTMX_HEADERS)
        assert b"Partial Paper" in resp.content
        # Should NOT contain full page structure (no base.html wrapper)
        assert b"<!DOCTYPE" not in resp.content

    def test_filtering_works_in_partial(self, client, web_config):
        _add_paper(web_config.db_path, "a1", "Active Paper", status="active")
        _add_paper(web_config.db_path, "p1", "Pruned Paper", status="pruned")
        resp = client.get("/partials/paper-rows?status=active", headers=self.HTMX_HEADERS)
        assert b"Active Paper" in resp.content
        assert b"Pruned Paper" not in resp.content

    def test_pagination_shown_for_many_papers(self, client, web_config):
        for i in range(30):
            _add_paper(web_config.db_path, f"paper-{i}", f"Paper {i}", velocity=float(i))
        resp = client.get("/partials/paper-rows", headers=self.HTMX_HEADERS)
        assert b"Page 1 of 2" in resp.content

    def test_page_2_shows_different_papers(self, client, web_config):
        # Create 30 papers with different titles
        for i in range(30):
            _add_paper(web_config.db_path, f"paper-{i:02d}", f"Paper Title {i:02d}", velocity=float(i))
        resp1 = client.get("/partials/paper-rows?page=1", headers=self.HTMX_HEADERS)
        resp2 = client.get("/partials/paper-rows?page=2", headers=self.HTMX_HEADERS)
        # At least some content differs between pages
        assert resp1.content != resp2.content

    def test_partial_includes_column_headers(self, client, web_config):
        """Column headers must be present in the HTMX partial so they survive swaps."""
        _add_paper(web_config.db_path, "p1", "A Paper")
        resp = client.get("/partials/paper-rows", headers=self.HTMX_HEADERS)
        assert b"<thead>" in resp.content
        assert b"Title" in resp.content
        assert b"Citations" in resp.content
        assert b"Velocity" in resp.content
        assert b"Status" in resp.content

    def test_partial_has_valid_table_structure(self, client, web_config):
        """The partial must use <tbody> inside <table>, not a <div>."""
        _add_paper(web_config.db_path, "p1", "A Paper")
        resp = client.get("/partials/paper-rows", headers=self.HTMX_HEADERS)
        html = resp.content.decode()
        # Table must contain thead and tbody, not a bare div
        assert "<table>" in html
        assert "<thead>" in html
        assert "<tbody>" in html

    def test_column_headers_preserved_after_status_filter(self, client, web_config):
        """Switching status filter must not lose column headers."""
        _add_paper(web_config.db_path, "p1", "Active Paper", status="active")
        _add_paper(web_config.db_path, "p2", "Pruned Paper", status="pruned")
        resp = client.get("/partials/paper-rows?status=active", headers=self.HTMX_HEADERS)
        assert b"<thead>" in resp.content
        assert b"Title" in resp.content
        assert b"Citations" in resp.content


class TestPartialRedirectOnRefresh:
    """Direct browser loads of /partials/paper-rows should redirect to /papers."""

    def test_redirects_to_papers(self, client, web_config):
        _add_paper(web_config.db_path, "p1", "A Paper")
        # follow_redirects=True is on by default, so we get the full page
        resp = client.get("/partials/paper-rows")
        assert resp.status_code == 200
        assert b"<!DOCTYPE" in resp.content
        assert b"Papers" in resp.content

    def test_preserves_query_params_on_redirect(self, client, web_config):
        _add_paper(web_config.db_path, "p1", "Active Paper", status="active")
        resp = client.get("/partials/paper-rows?status=active&q=Active")
        assert resp.status_code == 200
        assert b"Active Paper" in resp.content
        assert b"<!DOCTYPE" in resp.content

    def test_redirect_status_code(self, web_config):
        """Without follow_redirects, should return 302."""
        from src.web.app import create_app
        no_follow_client = TestClient(create_app(web_config), follow_redirects=False)
        resp = no_follow_client.get("/partials/paper-rows?status=active")
        assert resp.status_code == 302
        assert "/papers" in resp.headers["location"]
        assert "status=active" in resp.headers["location"]


class TestPaperTitleHover:
    def test_title_attribute_on_paper_link(self, client, web_config):
        """Paper link must have a title attribute showing the full title on hover."""
        full_title = "A Very Long Paper Title That Would Normally Be Truncated In The Table View"
        _add_paper(web_config.db_path, "p1", full_title)
        resp = client.get("/papers")
        html = resp.content.decode()
        assert f'title="{full_title}"' in html

    def test_title_attribute_in_partial(self, client, web_config):
        """Title attribute must also be present in the HTMX partial."""
        full_title = "Another Long Title For Testing Hover Tooltip Behavior In Partials"
        _add_paper(web_config.db_path, "p1", full_title)
        resp = client.get("/partials/paper-rows")
        html = resp.content.decode()
        assert f'title="{full_title}"' in html
