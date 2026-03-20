"""Tests for src.ingestion.reresolver — re-resolution of dangling papers."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db import (
    get_connection,
    get_dangling_papers,
    get_paper,
    increment_resolve_failures,
    init_db,
    paper_exists,
    replace_paper_id,
    reset_resolve_failures,
    upsert_paper,
)
from src.ingestion.reresolver import (
    ReResolveResult,
    _paper_dict_to_raw,
    _resolved_to_update_fields,
    re_resolve_dangling,
)
from src.ingestion.resolver import ResolvedPaper
from src.ingestion.scraper import RawPaper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_paper(paper_id, title="Test Paper", **overrides):
    defaults = dict(
        id=paper_id,
        title=title,
        authors='["Alice", "Bob"]',
        abstract="An abstract.",
        url="https://example.com",
        arxiv_id=None,
        doi=None,
        venue="ArXiv 2026",
        year=2026,
        published_date="2026-01-14",
        scholar_inbox_score=85.0,
        status="active",
        manual_status=0,
        ingested_at="2026-01-14T00:00:00+00:00",
        last_cited_check=None,
        citation_count=0,
        citation_velocity=0.0,
        category="CS",
    )
    defaults.update(overrides)
    return defaults


def _make_config(tmp_path):
    config = MagicMock()
    config.db_path = str(tmp_path / "test.db")
    config.secrets.semantic_scholar_api_key = None
    return config


def _make_resolved_paper(s2_id="real_s2_id_abc123"):
    return ResolvedPaper(
        semantic_scholar_id=s2_id,
        title="Test Paper (Resolved)",
        authors=["Alice", "Bob"],
        abstract="An abstract.",
        url="https://semanticscholar.org/paper/abc123",
        arxiv_id="2601.12345",
        doi="10.1234/test",
        venue="NeurIPS 2026",
        year=2026,
        published_date="2026-01-14",
        citation_count=42,
        scholar_inbox_score=85.0,
        scholar_inbox_url="https://example.com",
        category="CS",
    )


# ---------------------------------------------------------------------------
# DB function tests
# ---------------------------------------------------------------------------

class TestGetDanglingPapers:
    def test_returns_title_prefix_papers(self, db_conn):
        upsert_paper(db_conn, _make_paper("title:abc123def456"))
        upsert_paper(db_conn, _make_paper("real_s2_id_xyz"))

        dangling = get_dangling_papers(db_conn)
        assert len(dangling) == 1
        assert dangling[0]["id"] == "title:abc123def456"

    def test_returns_si_prefix_papers(self, db_conn):
        upsert_paper(db_conn, _make_paper("si-12345"))
        upsert_paper(db_conn, _make_paper("real_s2_id_xyz"))

        dangling = get_dangling_papers(db_conn)
        assert len(dangling) == 1
        assert dangling[0]["id"] == "si-12345"

    def test_returns_both_prefixes(self, db_conn):
        upsert_paper(db_conn, _make_paper("title:aaa"))
        upsert_paper(db_conn, _make_paper("si-999"))
        upsert_paper(db_conn, _make_paper("normal_id"))

        dangling = get_dangling_papers(db_conn)
        assert len(dangling) == 2
        ids = {p["id"] for p in dangling}
        assert ids == {"title:aaa", "si-999"}

    def test_returns_empty_when_none(self, db_conn):
        upsert_paper(db_conn, _make_paper("normal_id"))
        assert get_dangling_papers(db_conn) == []

    def test_excludes_papers_at_max_failures(self, db_conn):
        upsert_paper(db_conn, _make_paper("title:aaa", resolve_failures=3))
        upsert_paper(db_conn, _make_paper("title:bbb", resolve_failures=0))

        dangling = get_dangling_papers(db_conn, max_failures=3)
        assert len(dangling) == 1
        assert dangling[0]["id"] == "title:bbb"

    def test_includes_papers_below_max_failures(self, db_conn):
        upsert_paper(db_conn, _make_paper("title:aaa", resolve_failures=2))
        upsert_paper(db_conn, _make_paper("si-123", resolve_failures=1))

        dangling = get_dangling_papers(db_conn, max_failures=3)
        assert len(dangling) == 2


class TestIncrementResolveFailures:
    def test_increments_counter(self, db_conn):
        upsert_paper(db_conn, _make_paper("title:abc"))
        increment_resolve_failures(db_conn, "title:abc")
        paper = get_paper(db_conn, "title:abc")
        assert paper["resolve_failures"] == 1

    def test_increments_multiple_times(self, db_conn):
        upsert_paper(db_conn, _make_paper("title:abc"))
        increment_resolve_failures(db_conn, "title:abc")
        increment_resolve_failures(db_conn, "title:abc")
        increment_resolve_failures(db_conn, "title:abc")
        paper = get_paper(db_conn, "title:abc")
        assert paper["resolve_failures"] == 3


class TestResetResolveFailures:
    def test_resets_dangling_papers(self, db_conn):
        upsert_paper(db_conn, _make_paper("title:aaa", resolve_failures=3))
        upsert_paper(db_conn, _make_paper("si-123", resolve_failures=2))
        upsert_paper(db_conn, _make_paper("normal_id", resolve_failures=0))

        reset_resolve_failures(db_conn)

        assert get_paper(db_conn, "title:aaa")["resolve_failures"] == 0
        assert get_paper(db_conn, "si-123")["resolve_failures"] == 0
        assert get_paper(db_conn, "normal_id")["resolve_failures"] == 0

    def test_no_op_when_all_zero(self, db_conn):
        upsert_paper(db_conn, _make_paper("title:aaa", resolve_failures=0))
        reset_resolve_failures(db_conn)
        assert get_paper(db_conn, "title:aaa")["resolve_failures"] == 0


class TestReplacePaperId:
    def test_successful_replacement(self, db_conn):
        upsert_paper(db_conn, _make_paper("title:old_id"))

        replaced = replace_paper_id(
            db_conn,
            "title:old_id",
            "new_real_id",
            {"title": "Updated Title", "doi": "10.1234/test"},
        )

        assert replaced is True
        assert not paper_exists(db_conn, "title:old_id")
        new_paper = get_paper(db_conn, "new_real_id")
        assert new_paper is not None
        assert new_paper["title"] == "Updated Title"
        assert new_paper["doi"] == "10.1234/test"

    def test_duplicate_target_deletes_old(self, db_conn):
        upsert_paper(db_conn, _make_paper("title:old_id"))
        upsert_paper(db_conn, _make_paper("existing_id"))

        replaced = replace_paper_id(
            db_conn, "title:old_id", "existing_id", {"title": "New"}
        )

        assert replaced is False
        assert not paper_exists(db_conn, "title:old_id")
        assert paper_exists(db_conn, "existing_id")

    def test_nonexistent_old_id(self, db_conn):
        replaced = replace_paper_id(
            db_conn, "title:no_such_id", "new_id", {"title": "X"}
        )
        assert replaced is False

    def test_cascade_deletes_snapshots(self, db_conn):
        from src.db import insert_snapshot, get_snapshots

        upsert_paper(db_conn, _make_paper("title:old_id"))
        insert_snapshot(db_conn, "title:old_id", 5, "semantic_scholar")
        assert len(get_snapshots(db_conn, "title:old_id")) == 1

        replace_paper_id(
            db_conn, "title:old_id", "new_id", {"title": "Updated"}
        )

        assert get_snapshots(db_conn, "title:old_id") == []
        assert paper_exists(db_conn, "new_id")


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestPaperDictToRaw:
    def test_json_authors(self):
        paper = _make_paper("title:x", authors='["Alice", "Bob"]')
        raw = _paper_dict_to_raw(paper)
        assert raw.authors == ["Alice", "Bob"]
        assert raw.title == "Test Paper"
        assert raw.semantic_scholar_id is None  # Force re-resolution

    def test_comma_separated_authors(self):
        paper = _make_paper("title:x", authors="Alice, Bob, Charlie")
        raw = _paper_dict_to_raw(paper)
        assert raw.authors == ["Alice", "Bob", "Charlie"]

    def test_preserves_arxiv_id(self):
        paper = _make_paper("title:x", arxiv_id="2601.12345")
        raw = _paper_dict_to_raw(paper)
        assert raw.arxiv_id == "2601.12345"

    def test_none_authors(self):
        paper = _make_paper("title:x", authors=None)
        raw = _paper_dict_to_raw(paper)
        assert raw.authors == []


class TestResolvedToUpdateFields:
    def test_extracts_fields(self):
        resolved = _make_resolved_paper()
        fields = _resolved_to_update_fields(resolved)

        assert fields["doi"] == "10.1234/test"
        assert fields["citation_count"] == 42
        assert fields["arxiv_id"] == "2601.12345"
        assert "semantic_scholar_id" not in fields  # ID handled separately


# ---------------------------------------------------------------------------
# Integration tests for re_resolve_dangling
# ---------------------------------------------------------------------------

class TestReResolveDangling:
    @pytest.mark.asyncio
    async def test_resolves_dangling_paper(self, tmp_path):
        config = _make_config(tmp_path)
        init_db(config.db_path)

        from src.db import get_connection

        with get_connection(config.db_path) as conn:
            upsert_paper(conn, _make_paper("title:old_hash", arxiv_id="2601.12345"))

        resolved = _make_resolved_paper("real_s2_id")

        with patch(
            "src.ingestion.reresolver.resolve_paper",
            new_callable=AsyncMock,
            return_value=resolved,
        ):
            result = await re_resolve_dangling(config)

        assert result.total_dangling == 1
        assert result.resolved == 1
        assert result.still_unresolved == 0

        with get_connection(config.db_path) as conn:
            assert not paper_exists(conn, "title:old_hash")
            paper = get_paper(conn, "real_s2_id")
            assert paper is not None
            assert paper["doi"] == "10.1234/test"
            assert paper["citation_count"] == 42

    @pytest.mark.asyncio
    async def test_still_unresolved(self, tmp_path):
        config = _make_config(tmp_path)
        init_db(config.db_path)

        from src.db import get_connection

        with get_connection(config.db_path) as conn:
            upsert_paper(conn, _make_paper("title:old_hash"))

        with patch(
            "src.ingestion.reresolver.resolve_paper",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await re_resolve_dangling(config)

        assert result.total_dangling == 1
        assert result.resolved == 0
        assert result.still_unresolved == 1

        with get_connection(config.db_path) as conn:
            assert paper_exists(conn, "title:old_hash")

    @pytest.mark.asyncio
    async def test_skips_fallback_resolution(self, tmp_path):
        """If re-resolution returns another synthetic ID, don't replace."""
        config = _make_config(tmp_path)
        init_db(config.db_path)

        from src.db import get_connection

        with get_connection(config.db_path) as conn:
            upsert_paper(conn, _make_paper("title:old_hash"))

        # resolve_paper returns None, but resolve_papers would wrap it in
        # a fallback — we call resolve_paper directly, so None means not found.
        # Test the case where resolve_paper returns a ResolvedPaper with
        # another fallback ID (shouldn't happen normally, but defensive).
        fallback = _make_resolved_paper("title:another_hash")

        with patch(
            "src.ingestion.reresolver.resolve_paper",
            new_callable=AsyncMock,
            return_value=fallback,
        ):
            result = await re_resolve_dangling(config)

        assert result.still_unresolved == 1
        assert result.resolved == 0

        with get_connection(config.db_path) as conn:
            assert paper_exists(conn, "title:old_hash")

    @pytest.mark.asyncio
    async def test_duplicate_removal(self, tmp_path):
        """If resolved ID already exists, delete the dangling duplicate."""
        config = _make_config(tmp_path)
        init_db(config.db_path)

        from src.db import get_connection

        with get_connection(config.db_path) as conn:
            upsert_paper(conn, _make_paper("title:old_hash"))
            upsert_paper(conn, _make_paper("real_s2_id"))

        resolved = _make_resolved_paper("real_s2_id")

        with patch(
            "src.ingestion.reresolver.resolve_paper",
            new_callable=AsyncMock,
            return_value=resolved,
        ):
            result = await re_resolve_dangling(config)

        assert result.already_exists == 1
        assert result.resolved == 0

        with get_connection(config.db_path) as conn:
            assert not paper_exists(conn, "title:old_hash")
            assert paper_exists(conn, "real_s2_id")

    @pytest.mark.asyncio
    async def test_empty_db(self, tmp_path):
        config = _make_config(tmp_path)
        init_db(config.db_path)

        result = await re_resolve_dangling(config)

        assert result.total_dangling == 0
        assert result.resolved == 0

    @pytest.mark.asyncio
    async def test_handles_resolution_error(self, tmp_path):
        config = _make_config(tmp_path)
        init_db(config.db_path)

        from src.db import get_connection

        with get_connection(config.db_path) as conn:
            upsert_paper(conn, _make_paper("si-999"))

        with patch(
            "src.ingestion.reresolver.resolve_paper",
            new_callable=AsyncMock,
            side_effect=Exception("S2 API down"),
        ):
            result = await re_resolve_dangling(config)

        assert result.total_dangling == 1
        assert result.resolved == 0
        assert len(result.errors) == 1
        assert "S2 API down" in result.errors[0]

        # Paper should still exist
        with get_connection(config.db_path) as conn:
            assert paper_exists(conn, "si-999")

    @pytest.mark.asyncio
    async def test_si_prefix_papers_resolved(self, tmp_path):
        """Papers with si- prefix from backfill are also re-resolved."""
        config = _make_config(tmp_path)
        init_db(config.db_path)

        with get_connection(config.db_path) as conn:
            upsert_paper(conn, _make_paper("si-42"))

        resolved = _make_resolved_paper("real_s2_id_for_si")

        with patch(
            "src.ingestion.reresolver.resolve_paper",
            new_callable=AsyncMock,
            return_value=resolved,
        ):
            result = await re_resolve_dangling(config)

        assert result.resolved == 1

        with get_connection(config.db_path) as conn:
            assert not paper_exists(conn, "si-42")
            assert paper_exists(conn, "real_s2_id_for_si")

    @pytest.mark.asyncio
    async def test_increments_failures_on_error(self, tmp_path):
        """resolve_paper raising an exception increments resolve_failures."""
        config = _make_config(tmp_path)
        init_db(config.db_path)

        with get_connection(config.db_path) as conn:
            upsert_paper(conn, _make_paper("title:fail_me"))

        with patch(
            "src.ingestion.reresolver.resolve_paper",
            new_callable=AsyncMock,
            side_effect=Exception("S2 down"),
        ):
            result = await re_resolve_dangling(config)

        assert len(result.errors) == 1
        with get_connection(config.db_path) as conn:
            paper = get_paper(conn, "title:fail_me")
            assert paper["resolve_failures"] == 1

    @pytest.mark.asyncio
    async def test_increments_failures_on_unresolved(self, tmp_path):
        """resolve_paper returning None increments resolve_failures."""
        config = _make_config(tmp_path)
        init_db(config.db_path)

        with get_connection(config.db_path) as conn:
            upsert_paper(conn, _make_paper("title:no_match"))

        with patch(
            "src.ingestion.reresolver.resolve_paper",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await re_resolve_dangling(config)

        assert result.still_unresolved == 1
        with get_connection(config.db_path) as conn:
            paper = get_paper(conn, "title:no_match")
            assert paper["resolve_failures"] == 1

    @pytest.mark.asyncio
    async def test_skips_papers_at_max_failures(self, tmp_path):
        """Papers with resolve_failures >= MAX are not attempted."""
        config = _make_config(tmp_path)
        init_db(config.db_path)

        with get_connection(config.db_path) as conn:
            upsert_paper(conn, _make_paper("title:exhausted", resolve_failures=3))

        mock_resolve = AsyncMock(return_value=None)
        with patch("src.ingestion.reresolver.resolve_paper", mock_resolve):
            result = await re_resolve_dangling(config)

        # Should NOT have been called at all
        mock_resolve.assert_not_called()
        assert result.total_dangling == 1
        assert result.skipped_max_failures == 1
        assert result.still_unresolved == 0

    @pytest.mark.asyncio
    async def test_failure_counter_accumulates_across_runs(self, tmp_path):
        """Multiple re-resolve runs accumulate the failure counter."""
        config = _make_config(tmp_path)
        init_db(config.db_path)

        with get_connection(config.db_path) as conn:
            upsert_paper(conn, _make_paper("title:stubborn"))

        with patch(
            "src.ingestion.reresolver.resolve_paper",
            new_callable=AsyncMock,
            return_value=None,
        ):
            # Run 1: failures -> 1
            await re_resolve_dangling(config)
            # Run 2: failures -> 2
            await re_resolve_dangling(config)
            # Run 3: failures -> 3
            await re_resolve_dangling(config)
            # Run 4: should be skipped (failures == 3 == MAX)
            result = await re_resolve_dangling(config)

        assert result.skipped_max_failures == 1
        with get_connection(config.db_path) as conn:
            paper = get_paper(conn, "title:stubborn")
            assert paper["resolve_failures"] == 3
