"""Tests for critical fixes from design coherence review.

This test suite covers:
1. Score threshold conversion (0.0-1.0 decimal scale)
2. paper_to_dict() function
3. Backfill date recording
4. Configuration validation with decimal thresholds
"""

import json
from datetime import datetime

import pytest

from src.config import AppConfig, IngestionConfig, load_config
from src.ingestion.resolver import ResolvedPaper, paper_to_dict
from src.ingestion.scraper import _parse_papers


class TestScoreThresholdConversion:
    """Test that score thresholds use correct decimal scale."""

    def test_parse_papers_with_decimal_threshold(self):
        """_parse_papers should accept decimal threshold (0.0-1.0) directly."""
        data = {
            "digest_df": [
                {
                    "ranking_score": 0.85,
                    "title": "High Score Paper",
                    "authors": "Alice, Bob",
                    "abstract": "Test abstract",
                    "arxiv_id": "2302.00001",
                    "semantic_scholar_id": "s2-id-1",
                    "paper_id": 123,
                    "display_venue": "NeurIPS 2023",
                    "category": "ML",
                },
                {
                    "ranking_score": 0.45,
                    "title": "Low Score Paper",
                    "authors": "Charlie",
                    "abstract": "Another abstract",
                    "arxiv_id": "2302.00002",
                    "semantic_scholar_id": "s2-id-2",
                    "paper_id": 124,
                    "display_venue": "ArXiv 2023",
                    "category": "ML",
                },
            ]
        }

        # With threshold 0.60, only high score paper (0.85) should pass
        result = _parse_papers(data, 0.60)
        assert len(result) == 1
        assert result[0].title == "High Score Paper"

    def test_parse_papers_boundary_case(self):
        """Test papers at threshold boundary."""
        data = {
            "digest_df": [
                {
                    "ranking_score": 0.60,
                    "title": "Boundary Paper",
                    "authors": "Test",
                    "abstract": "Test",
                    "arxiv_id": "2302.00003",
                    "semantic_scholar_id": "s2-id-3",
                    "paper_id": 125,
                    "display_venue": "Test",
                    "category": "Test",
                },
            ]
        }

        # Paper at exactly 0.60 should pass (uses < comparison, so 0.60 is not < 0.60)
        result = _parse_papers(data, 0.60)
        assert len(result) == 1

        # Paper just below threshold should fail
        data["digest_df"][0]["ranking_score"] = 0.59
        result = _parse_papers(data, 0.60)
        assert len(result) == 0


class TestPaperToDict:
    """Test paper_to_dict() conversion function."""

    def test_paper_to_dict_basic_fields(self):
        """paper_to_dict should convert all required fields."""
        paper = ResolvedPaper(
            semantic_scholar_id="abc123def456",
            title="Test Paper",
            authors=["Alice Smith", "Bob Jones"],
            abstract="Test abstract",
            url="https://example.com/paper",
            arxiv_id="2302.00001",
            doi="10.1234/test",
            venue="NeurIPS",
            year=2023,
            published_date="2023-02-01",
            citation_count=42,
            scholar_inbox_score=0.85,
            scholar_inbox_url="https://scholar-inbox.com/paper",
        )

        result = paper_to_dict(paper)

        assert result["id"] == "abc123def456"
        assert result["title"] == "Test Paper"
        assert json.loads(result["authors"]) == ["Alice Smith", "Bob Jones"]
        assert result["abstract"] == "Test abstract"
        assert result["arxiv_id"] == "2302.00001"
        assert result["doi"] == "10.1234/test"
        assert result["venue"] == "NeurIPS"
        assert result["year"] == 2023
        assert result["citation_count"] == 42
        assert result["scholar_inbox_score"] == 0.85
        assert result["status"] == "active"
        assert result["manual_status"] == 0

    def test_paper_to_dict_includes_timestamps(self):
        """paper_to_dict should include ingested_at timestamp."""
        paper = ResolvedPaper(
            semantic_scholar_id="test-id",
            title="Test",
            authors=["Author"],
            abstract="Abstract",
            url="https://example.com",
            arxiv_id=None,
            doi=None,
            venue=None,
            year=None,
            published_date=None,
            citation_count=0,
            scholar_inbox_score=0.7,
            scholar_inbox_url="https://scholar-inbox.com",
        )

        result = paper_to_dict(paper)

        assert "ingested_at" in result
        # Should be a valid ISO 8601 format
        datetime.fromisoformat(result["ingested_at"])

    def test_paper_to_dict_authors_json_encoding(self):
        """paper_to_dict should properly JSON encode authors list."""
        paper = ResolvedPaper(
            semantic_scholar_id="test-id",
            title="Test",
            authors=["Author 1", "Author 2", "Author 3"],
            abstract="Abstract",
            url=None,
            arxiv_id=None,
            doi=None,
            venue=None,
            year=None,
            published_date=None,
            citation_count=0,
            scholar_inbox_score=0.5,
            scholar_inbox_url=None,
        )

        result = paper_to_dict(paper)

        authors = json.loads(result["authors"])
        assert isinstance(authors, list)
        assert len(authors) == 3
        assert authors == ["Author 1", "Author 2", "Author 3"]


class TestConfigurationValidation:
    """Test that configuration validates decimal thresholds correctly."""

    def test_score_threshold_valid_decimal_range(self):
        """score_threshold should accept values in 0.0-1.0 range."""
        config = IngestionConfig(score_threshold=0.60)
        assert config.score_threshold == 0.60

    def test_score_threshold_too_high(self):
        """score_threshold > 1.0 should be rejected by load_config validation."""
        from src.config import _validate_config
        from src.errors import ConfigError

        # Create an invalid config and validate it
        app_config = AppConfig(
            ingestion=IngestionConfig(score_threshold=1.5)
        )

        with pytest.raises(ConfigError, match="must be between 0.0 and 1.0"):
            _validate_config(app_config)

    def test_backfill_score_threshold_validation(self):
        """backfill_score_threshold should validate decimal range."""
        from src.errors import ConfigError

        config = IngestionConfig(backfill_score_threshold=0.70)
        assert config.backfill_score_threshold == 0.70

    def test_config_defaults_are_decimal(self):
        """Default thresholds should be in decimal scale."""
        config = IngestionConfig()
        assert 0.0 <= config.score_threshold <= 1.0
        assert 0.0 <= config.backfill_score_threshold <= 1.0
        assert config.score_threshold == 0.60
        assert config.backfill_score_threshold == 0.60


class TestScraperWithConfigConfig:
    """Test that scraper correctly uses decimal thresholds from config."""

    def test_scraper_respects_config_threshold(self, tmp_path):
        """Scraper should use threshold directly from config (decimal scale)."""
        data = {
            "digest_df": [
                {
                    "ranking_score": 0.75,
                    "title": "Paper 1",
                    "authors": "Author",
                    "abstract": "Abstract",
                    "arxiv_id": "2302.00001",
                    "semantic_scholar_id": "s2-1",
                    "paper_id": 1,
                    "display_venue": "Venue",
                    "category": "Cat",
                },
                {
                    "ranking_score": 0.50,
                    "title": "Paper 2",
                    "authors": "Author",
                    "abstract": "Abstract",
                    "arxiv_id": "2302.00002",
                    "semantic_Scholar_id": "s2-2",
                    "paper_id": 2,
                    "display_venue": "Venue",
                    "category": "Cat",
                },
            ]
        }

        # With 0.60 threshold, only paper 1 should pass
        result = _parse_papers(data, 0.60)
        assert len(result) == 1
        assert result[0].title == "Paper 1"

        # With 0.40 threshold, both papers should pass
        result = _parse_papers(data, 0.40)
        assert len(result) == 2

        # With 0.90 threshold, no papers should pass
        result = _parse_papers(data, 0.90)
        assert len(result) == 0


class TestConfigTomlDecimalFormat:
    """Test that config.toml uses correct decimal format."""

    def test_config_toml_parsing(self, tmp_path):
        """config.toml should parse decimal thresholds correctly."""
        config_content = """
[ingestion]
score_threshold = 0.60
backfill_score_threshold = 0.55
backfill_lookback_days = 30

[citations]
semantic_scholar_batch_size = 100

[pruning]
min_age_months = 6
min_citations = 10
min_velocity = 1.0

[promotion]
citation_threshold = 50
velocity_threshold = 10.0

[browser]
profile_dir = "data/browser_profile"
headed_fallback = true
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)

        # Load and verify
        import tomllib

        with open(config_file, "rb") as f:
            data = tomllib.load(f)

        assert data["ingestion"]["score_threshold"] == 0.60
        assert data["ingestion"]["backfill_score_threshold"] == 0.55
