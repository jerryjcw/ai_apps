"""Tests for src.ingestion.orchestrate."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingestion.orchestrate import run_ingest, _resolved_to_db_dict
from src.ingestion.resolver import ResolvedPaper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_resolved(
    paper_id="s2-abc123",
    title="Test Paper",
    citation_count=5,
) -> ResolvedPaper:
    return ResolvedPaper(
        semantic_scholar_id=paper_id,
        title=title,
        authors=["Author A"],
        abstract="Abstract text",
        url="https://example.com/paper",
        arxiv_id="2401.00001",
        doi="10.1234/test",
        venue="NeurIPS",
        year=2024,
        published_date="2024-06-01",
        citation_count=citation_count,
        scholar_inbox_score=0.85,
        scholar_inbox_url="https://scholar-inbox.com/paper/1",
    )


def _make_raw_paper():
    """Return a mock RawPaper."""
    raw = MagicMock()
    raw.title = "Test Paper"
    raw.score = 0.85
    return raw


# ---------------------------------------------------------------------------
# _resolved_to_db_dict
# ---------------------------------------------------------------------------

class TestResolvedToDbDict:
    def test_converts_all_fields(self):
        import json
        paper = _make_resolved()
        d = _resolved_to_db_dict(paper)

        assert d["id"] == "s2-abc123"
        assert d["title"] == "Test Paper"
        assert json.loads(d["authors"]) == ["Author A"]  # Authors stored as JSON
        assert d["arxiv_id"] == "2401.00001"
        assert d["venue"] == "NeurIPS"
        assert d["year"] == 2024
        assert d["published_date"] == "2024-06-01"
        assert d["scholar_inbox_score"] == 0.85

    def test_url_falls_back_to_scholar_inbox(self):
        paper = _make_resolved()
        paper.url = None
        d = _resolved_to_db_dict(paper)
        assert d["url"] == "https://scholar-inbox.com/paper/1"


# ---------------------------------------------------------------------------
# run_ingest
# ---------------------------------------------------------------------------

class TestRunIngest:
    @pytest.mark.asyncio
    async def test_successful_ingest(self, tmp_path):
        """End-to-end: scrape → resolve → store."""
        from src.config import AppConfig
        from src.db import init_db, get_connection

        db_path = str(tmp_path / "test.db")
        config = AppConfig(db_path=db_path)
        init_db(db_path)

        raw = _make_raw_paper()
        resolved = _make_resolved(citation_count=10)

        with (
            patch(
                "src.ingestion.orchestrate.scrape_recommendations",
                new_callable=AsyncMock,
                return_value=[raw],
            ),
            patch(
                "src.ingestion.orchestrate.resolve_papers",
                new_callable=AsyncMock,
                return_value=[resolved],
            ),
        ):
            result = await run_ingest(config)

        assert result["papers_found"] == 1
        assert result["papers_ingested"] == 1
        assert result["run_id"] is not None

        # Verify paper stored in DB
        with get_connection(db_path) as conn:
            paper = conn.execute(
                "SELECT * FROM papers WHERE id = ?",
                (resolved.semantic_scholar_id,),
            ).fetchone()
            assert paper is not None
            assert paper["title"] == "Test Paper"

            # Verify initial snapshot created (citation_count > 0)
            snapshot = conn.execute(
                "SELECT * FROM citation_snapshots WHERE paper_id = ?",
                (resolved.semantic_scholar_id,),
            ).fetchone()
            assert snapshot is not None
            assert snapshot["total_citations"] == 10

    @pytest.mark.asyncio
    async def test_skips_existing_papers(self, tmp_path):
        """Papers already in DB are not counted as new."""
        from src.config import AppConfig
        from src.db import init_db, get_connection, upsert_paper, now_utc

        db_path = str(tmp_path / "test.db")
        config = AppConfig(db_path=db_path)
        init_db(db_path)

        # Pre-insert the paper
        with get_connection(db_path) as conn:
            upsert_paper(conn, {
                "id": "s2-abc123",
                "title": "Existing Paper",
                "authors": [],
                "ingested_at": now_utc(),
            })

        raw = _make_raw_paper()
        resolved = _make_resolved(paper_id="s2-abc123")

        with (
            patch(
                "src.ingestion.orchestrate.scrape_recommendations",
                new_callable=AsyncMock,
                return_value=[raw],
            ),
            patch(
                "src.ingestion.orchestrate.resolve_papers",
                new_callable=AsyncMock,
                return_value=[resolved],
            ),
        ):
            result = await run_ingest(config)

        assert result["papers_found"] == 1
        assert result["papers_ingested"] == 0

    @pytest.mark.asyncio
    async def test_no_snapshot_for_zero_citations(self, tmp_path):
        """Papers with 0 citations don't get an initial snapshot."""
        from src.config import AppConfig
        from src.db import init_db, get_connection

        db_path = str(tmp_path / "test.db")
        config = AppConfig(db_path=db_path)
        init_db(db_path)

        raw = _make_raw_paper()
        resolved = _make_resolved(citation_count=0)

        with (
            patch(
                "src.ingestion.orchestrate.scrape_recommendations",
                new_callable=AsyncMock,
                return_value=[raw],
            ),
            patch(
                "src.ingestion.orchestrate.resolve_papers",
                new_callable=AsyncMock,
                return_value=[resolved],
            ),
        ):
            await run_ingest(config)

        with get_connection(db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM citation_snapshots"
            ).fetchone()[0]
            assert count == 0

    @pytest.mark.asyncio
    async def test_failure_marks_run_failed(self, tmp_path):
        """If scraping raises, the ingestion run is marked as failed."""
        from src.config import AppConfig
        from src.db import init_db, get_connection

        db_path = str(tmp_path / "test.db")
        config = AppConfig(db_path=db_path)
        init_db(db_path)

        with (
            patch(
                "src.ingestion.orchestrate.scrape_recommendations",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API down"),
            ),
            pytest.raises(RuntimeError, match="API down"),
        ):
            await run_ingest(config)

        with get_connection(db_path) as conn:
            run = conn.execute(
                "SELECT * FROM ingestion_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert run["status"] == "failed"
            assert "API down" in run["error_message"]

    @pytest.mark.asyncio
    async def test_empty_scrape(self, tmp_path):
        """No papers found → 0 ingested, run completed."""
        from src.config import AppConfig
        from src.db import init_db, get_connection

        db_path = str(tmp_path / "test.db")
        config = AppConfig(db_path=db_path)
        init_db(db_path)

        with (
            patch(
                "src.ingestion.orchestrate.scrape_recommendations",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.ingestion.orchestrate.resolve_papers",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await run_ingest(config)

        assert result["papers_found"] == 0
        assert result["papers_ingested"] == 0

        with get_connection(db_path) as conn:
            run = conn.execute(
                "SELECT * FROM ingestion_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert run["status"] == "completed"
