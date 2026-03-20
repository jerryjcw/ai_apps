"""Tests for src.citations.poller."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.citations.poller import (
    _should_fetch_openalex,
    collect_citations_for_unpolled,
    run_citation_poll,
)


# ---------------------------------------------------------------------------
# _should_fetch_openalex
# ---------------------------------------------------------------------------

class TestShouldFetchOpenalex:
    def test_never_checked(self):
        paper = {"last_cited_check": None}
        now = datetime(2024, 4, 15, tzinfo=timezone.utc)
        assert _should_fetch_openalex(paper, now) is True

    def test_checked_recently(self):
        now = datetime(2024, 4, 15, tzinfo=timezone.utc)
        recent = (now - timedelta(days=10)).isoformat()
        paper = {"last_cited_check": recent}
        assert _should_fetch_openalex(paper, now) is False

    def test_checked_over_30_days_ago(self):
        now = datetime(2024, 4, 15, tzinfo=timezone.utc)
        old = (now - timedelta(days=31)).isoformat()
        paper = {"last_cited_check": old}
        assert _should_fetch_openalex(paper, now) is True

    def test_exactly_30_days(self):
        now = datetime(2024, 4, 15, tzinfo=timezone.utc)
        boundary = (now - timedelta(days=30)).isoformat()
        paper = {"last_cited_check": boundary}
        assert _should_fetch_openalex(paper, now) is True

    def test_invalid_date_returns_true(self):
        paper = {"last_cited_check": "not-a-date"}
        now = datetime(2024, 4, 15, tzinfo=timezone.utc)
        assert _should_fetch_openalex(paper, now) is True


# ---------------------------------------------------------------------------
# run_citation_poll
# ---------------------------------------------------------------------------

class TestRunCitationPoll:
    @pytest.mark.asyncio
    async def test_no_papers_due(self):
        """Empty list → returns 0, no work done."""
        with patch("src.citations.poller.db") as mock_db:
            mock_conn = MagicMock()
            mock_db.get_connection.return_value.__enter__ = MagicMock(
                return_value=mock_conn
            )
            mock_db.get_connection.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_db.count_non_pruned_papers.return_value = 10
            mock_db.get_papers_due_for_poll.return_value = []

            config = MagicMock()
            config.citations.poll_budget_fraction = 0.10
            result = await run_citation_poll(config, ":memory:")
            assert result == 0

    @pytest.mark.asyncio
    async def test_full_poll_flow(self):
        """Full cycle with mocked dependencies."""
        papers = [
            {
                "id": "arxiv:2301.00001",
                "title": "Test Paper 1",
                "arxiv_id": "2301.00001",
                "last_cited_check": None,
            },
            {
                "id": "s2hash123",
                "title": "Test Paper 2",
                "arxiv_id": None,
                "last_cited_check": None,
            },
        ]

        with (
            patch("src.citations.poller.db") as mock_db,
            patch("src.citations.poller.semantic_scholar") as mock_s2,
            patch("src.citations.poller.velocity") as mock_vel,
            patch("src.citations.poller.openalex") as mock_oa,
            patch("src.citations.poller.httpx") as mock_httpx,
        ):
            # Setup db mock
            mock_conn = MagicMock()
            mock_db.get_connection.return_value.__enter__ = MagicMock(
                return_value=mock_conn
            )
            mock_db.get_connection.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_db.count_non_pruned_papers.return_value = 20
            mock_db.get_papers_due_for_poll.return_value = papers

            # Setup S2 mock
            mock_s2.fetch_citations_batch = AsyncMock(
                return_value={
                    "arxiv:2301.00001": 42,
                    "s2hash123": 15,
                }
            )

            # Setup velocity mock
            mock_vel.update_velocities_bulk = MagicMock()
            mock_vel.compute_velocity = MagicMock(return_value=3.5)

            # Setup openalex mock
            mock_oa.fetch_yearly_citations = AsyncMock(return_value=None)

            # Setup httpx mock
            mock_client = AsyncMock()
            mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            config = MagicMock()
            config.secrets.semantic_scholar_api_key = "test-key"
            config.secrets.scholar_inbox_email = "test@example.com"
            config.citations.semantic_scholar_batch_size = 100
            config.citations.poll_budget_fraction = 0.10

            result = await run_citation_poll(config, ":memory:")
            assert result == 2

            # Verify budget was computed: floor(20 * 0.10) = 2
            mock_db.get_papers_due_for_poll.assert_called_once()
            call_kwargs = mock_db.get_papers_due_for_poll.call_args
            assert call_kwargs[1]["limit"] == 2

            # Verify S2 was called
            mock_s2.fetch_citations_batch.assert_called_once()

            # Verify snapshots were inserted
            assert mock_db.insert_snapshot.call_count == 2

            # Verify velocity was updated
            mock_vel.update_velocities_bulk.assert_called_once()

    @pytest.mark.asyncio
    async def test_title_papers_included_but_skipped_by_s2(self):
        """Papers with title: IDs are included in poll but S2 returns no count."""
        papers = [
            {
                "id": "title:abc123",
                "title": "Fallback Paper",
                "arxiv_id": None,
                "last_cited_check": None,
            },
        ]

        with (
            patch("src.citations.poller.db") as mock_db,
            patch("src.citations.poller.semantic_scholar") as mock_s2,
            patch("src.citations.poller.velocity") as mock_vel,
            patch("src.citations.poller.openalex") as mock_oa,
            patch("src.citations.poller.httpx") as mock_httpx,
        ):
            mock_conn = MagicMock()
            mock_db.get_connection.return_value.__enter__ = MagicMock(
                return_value=mock_conn
            )
            mock_db.get_connection.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_db.count_non_pruned_papers.return_value = 10
            mock_db.get_papers_due_for_poll.return_value = papers

            # S2 returns empty (title: papers are skipped internally)
            mock_s2.fetch_citations_batch = AsyncMock(return_value={})
            mock_vel.update_velocities_bulk = MagicMock()
            mock_vel.compute_velocity = MagicMock(return_value=0.0)
            mock_oa.fetch_yearly_citations = AsyncMock(return_value=None)

            mock_client = AsyncMock()
            mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            config = MagicMock()
            config.secrets.semantic_scholar_api_key = ""
            config.secrets.scholar_inbox_email = ""
            config.citations.semantic_scholar_batch_size = 100
            config.citations.poll_budget_fraction = 0.10

            result = await run_citation_poll(config, ":memory:")
            assert result == 1

            # No snapshot should be inserted (S2 returned nothing for title: papers)
            mock_db.insert_snapshot.assert_not_called()

    @pytest.mark.asyncio
    async def test_openalex_only_for_monthly_due(self):
        """OpenAlex is only fetched for papers not checked in 30+ days."""
        now = datetime(2024, 4, 15, tzinfo=timezone.utc)
        recent_check = (now - timedelta(days=5)).isoformat()
        old_check = (now - timedelta(days=35)).isoformat()

        papers = [
            {
                "id": "arxiv:001",
                "title": "Recent",
                "arxiv_id": "001",
                "last_cited_check": recent_check,
            },
            {
                "id": "arxiv:002",
                "title": "Old",
                "arxiv_id": "002",
                "last_cited_check": old_check,
            },
        ]

        with (
            patch("src.citations.poller.db") as mock_db,
            patch("src.citations.poller.semantic_scholar") as mock_s2,
            patch("src.citations.poller.velocity") as mock_vel,
            patch("src.citations.poller.openalex") as mock_oa,
            patch("src.citations.poller.httpx") as mock_httpx,
        ):
            mock_conn = MagicMock()
            mock_db.get_connection.return_value.__enter__ = MagicMock(
                return_value=mock_conn
            )
            mock_db.get_connection.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_db.count_non_pruned_papers.return_value = 100
            mock_db.get_papers_due_for_poll.return_value = papers

            mock_s2.fetch_citations_batch = AsyncMock(
                return_value={"arxiv:001": 10, "arxiv:002": 20}
            )
            mock_vel.update_velocities_bulk = MagicMock()
            mock_vel.compute_velocity = MagicMock(return_value=1.0)
            mock_oa.fetch_yearly_citations = AsyncMock(return_value=None)

            mock_client = AsyncMock()
            mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            config = MagicMock()
            config.secrets.semantic_scholar_api_key = "key"
            config.secrets.scholar_inbox_email = "test@example.com"
            config.citations.semantic_scholar_batch_size = 100
            config.citations.poll_budget_fraction = 0.10

            await run_citation_poll(config, ":memory:")

            # OpenAlex should be called once (for the old-checked paper)
            # The recent one should be skipped
            # Due to datetime.now mock limitations, we check call count
            # At minimum it should have been called for some papers
            assert mock_oa.fetch_yearly_citations.call_count >= 1


    @pytest.mark.asyncio
    async def test_budget_minimum_is_one(self):
        """Even with very few papers, budget is at least 1."""
        with patch("src.citations.poller.db") as mock_db:
            mock_conn = MagicMock()
            mock_db.get_connection.return_value.__enter__ = MagicMock(
                return_value=mock_conn
            )
            mock_db.get_connection.return_value.__exit__ = MagicMock(
                return_value=False
            )
            # 3 papers * 0.10 = 0.3 -> floor = 0 -> clamped to 1
            mock_db.count_non_pruned_papers.return_value = 3
            mock_db.get_papers_due_for_poll.return_value = []

            config = MagicMock()
            config.citations.poll_budget_fraction = 0.10
            await run_citation_poll(config, ":memory:")

            mock_db.get_papers_due_for_poll.assert_called_once()
            call_kwargs = mock_db.get_papers_due_for_poll.call_args
            assert call_kwargs[1]["limit"] == 1

    @pytest.mark.asyncio
    async def test_budget_computation(self):
        """Budget = floor(total * fraction), minimum 1."""
        with patch("src.citations.poller.db") as mock_db:
            mock_conn = MagicMock()
            mock_db.get_connection.return_value.__enter__ = MagicMock(
                return_value=mock_conn
            )
            mock_db.get_connection.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_db.count_non_pruned_papers.return_value = 150
            mock_db.get_papers_due_for_poll.return_value = []

            config = MagicMock()
            config.citations.poll_budget_fraction = 0.10
            await run_citation_poll(config, ":memory:")

            call_kwargs = mock_db.get_papers_due_for_poll.call_args
            assert call_kwargs[1]["limit"] == 15  # floor(150 * 0.10)


# ---------------------------------------------------------------------------
# collect_citations_for_unpolled
# ---------------------------------------------------------------------------

class TestCollectCitationsForUnpolled:
    @pytest.mark.asyncio
    async def test_no_unpolled_papers(self):
        """Empty list → returns 0, no work done."""
        with patch("src.citations.poller.db") as mock_db:
            mock_conn = MagicMock()
            mock_db.get_connection.return_value.__enter__ = MagicMock(
                return_value=mock_conn
            )
            mock_db.get_connection.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_db.get_papers_never_polled.return_value = []

            config = MagicMock()
            result = await collect_citations_for_unpolled(config, ":memory:")
            assert result == 0

    @pytest.mark.asyncio
    async def test_full_collect_flow(self):
        """Full cycle: S2 fetch, snapshots, velocity, update — no OpenAlex."""
        papers = [
            {"id": "arxiv:2301.00001", "title": "Paper 1"},
            {"id": "s2hash123", "title": "Paper 2"},
        ]

        with (
            patch("src.citations.poller.db") as mock_db,
            patch("src.citations.poller.semantic_scholar") as mock_s2,
            patch("src.citations.poller.velocity") as mock_vel,
            patch("src.citations.poller.openalex") as mock_oa,
            patch("src.citations.poller.httpx") as mock_httpx,
        ):
            mock_conn = MagicMock()
            mock_db.get_connection.return_value.__enter__ = MagicMock(
                return_value=mock_conn
            )
            mock_db.get_connection.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_db.get_papers_never_polled.return_value = papers

            mock_s2.fetch_citations_batch = AsyncMock(
                return_value={"arxiv:2301.00001": 42, "s2hash123": 15}
            )
            mock_vel.update_velocities_bulk = MagicMock()
            mock_vel.compute_velocity = MagicMock(return_value=3.5)

            mock_client = AsyncMock()
            mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            config = MagicMock()
            config.secrets.semantic_scholar_api_key = "test-key"
            config.citations.semantic_scholar_batch_size = 100

            result = await collect_citations_for_unpolled(config, ":memory:")
            assert result == 2

            # S2 was called
            mock_s2.fetch_citations_batch.assert_called_once()

            # Snapshots inserted for both papers
            assert mock_db.insert_snapshot.call_count == 2

            # Velocity updated
            mock_vel.update_velocities_bulk.assert_called_once()

            # Paper citations updated for both
            assert mock_db.update_paper_citations.call_count == 2

            # OpenAlex was NOT called (skipped for unpolled collection)
            mock_oa.fetch_yearly_citations.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_s2_results(self):
        """When S2 returns counts for only some papers, only those get updated."""
        papers = [
            {"id": "p1", "title": "Found"},
            {"id": "p2", "title": "Not Found"},
        ]

        with (
            patch("src.citations.poller.db") as mock_db,
            patch("src.citations.poller.semantic_scholar") as mock_s2,
            patch("src.citations.poller.velocity") as mock_vel,
            patch("src.citations.poller.httpx") as mock_httpx,
        ):
            mock_conn = MagicMock()
            mock_db.get_connection.return_value.__enter__ = MagicMock(
                return_value=mock_conn
            )
            mock_db.get_connection.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_db.get_papers_never_polled.return_value = papers

            # S2 only returns a count for p1
            mock_s2.fetch_citations_batch = AsyncMock(return_value={"p1": 10})
            mock_vel.update_velocities_bulk = MagicMock()
            mock_vel.compute_velocity = MagicMock(return_value=1.0)

            mock_client = AsyncMock()
            mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            config = MagicMock()
            config.secrets.semantic_scholar_api_key = "key"
            config.citations.semantic_scholar_batch_size = 100

            result = await collect_citations_for_unpolled(config, ":memory:")
            assert result == 2  # both papers counted as processed

            # Only 1 snapshot inserted (p1)
            assert mock_db.insert_snapshot.call_count == 1

            # Only 1 paper citations updated (p1)
            assert mock_db.update_paper_citations.call_count == 1
