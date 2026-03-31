"""Tests for log_interaction.py."""

import pytest

from helpers.log_interaction import (
    log_interaction,
    save_review,
    validate_review_file,
    write_pipeline_summary,
)


class TestLogInteraction:
    def test_creates_log_file(self, workspace):
        path = log_interaction(
            workspace,
            stage="stage_1_literature",
            round_num=1,
            role="Student",
            input_summary="Topic: test topic",
            full_output="Found 15 papers...",
            decision=None,
        )
        assert path.exists()
        content = path.read_text()
        assert "stage_1_literature" in content
        assert "Student" in content
        assert "**Round**: 1" in content
        assert "Found 15 papers..." in content
        assert "N/A" in content  # decision

    def test_with_decision(self, workspace):
        path = log_interaction(
            workspace,
            stage="stage_6_advisor_review",
            round_num=2,
            role="Advisor",
            input_summary="5 plans",
            full_output="Review content...",
            decision="idea1: APPROVE, idea2: REFINE",
        )
        content = path.read_text()
        assert "idea1: APPROVE" in content

    def test_with_idea_slug(self, workspace):
        path = log_interaction(
            workspace,
            stage="stage_3_hypothesis",
            round_num=1,
            role="Student",
            input_summary="Developing idea",
            full_output="Hypothesis...",
            idea_slug="cool-idea",
        )
        assert "cool-idea" in path.name
        content = path.read_text()
        assert "cool-idea" in content

    def test_duplicate_filename_handled(self, workspace):
        kwargs = dict(
            workspace=workspace,
            stage="stage_1_literature",
            round_num=1,
            role="Student",
            input_summary="...",
            full_output="...",
        )
        path1 = log_interaction(**kwargs)
        path2 = log_interaction(**kwargs)
        assert path1 != path2
        assert path2.exists()
        assert "v2" in path2.name


VALID_REVIEW = """\
# Round 1 Advisor Review — test-idea
**Reviewer**: Advisor
**Standard**: lenient
**Date**: 2026-03-29

## Overall Assessment
This is a thorough assessment of the proposal covering theory, experiments,
and baselines. The method is well-motivated but has several issues.

## Per-Section Critique
Section 3 claims X but provides no proof. Section 5 baseline list is incomplete.

## Issues Raised
### R1-ADV-1 [major, theory]
**Problem**: The core theorem assumes independence that does not hold.
**Suggested fix direction**: Add a conditional independence proof or weaken the claim.
**Relevant citations**: arXiv:2503.12345

### R1-ADV-2 [minor, experiment]
**Problem**: Missing ablation on learning rate sensitivity.
**Suggested fix direction**: Add LR sweep {1e-4, 3e-4, 1e-3}.

## Evaluation Technique Results
Analogy test: passes. Counterexample test: found 2 failure cases.

## Verdict
REFINE
"""


class TestSaveReview:
    def test_saves_valid_review(self, workspace):
        path = save_review(workspace, "advisor", "test-idea", 1, VALID_REVIEW)
        assert path.exists()
        assert path.name == "advisor_test-idea_round1.md"
        assert path.read_text() == VALID_REVIEW

    def test_saves_to_reviews_dir(self, workspace):
        path = save_review(workspace, "vp", "my-idea", 2, VALID_REVIEW)
        assert "reviews" in str(path)
        assert path.name == "vp_my-idea_round2.md"

    def test_rejects_truncated_review(self, workspace):
        short = "VERDICT: APPROVE"
        with pytest.raises(ValueError, match="too short"):
            save_review(workspace, "advisor", "idea", 1, short)

    def test_rejects_missing_sections(self, workspace):
        no_verdict = "## Overall Assessment\nGood.\n## Issues Raised\nNone.\n" + ("x" * 500)
        with pytest.raises(ValueError, match="Missing required section.*Verdict"):
            save_review(workspace, "advisor", "idea", 1, no_verdict)

    def test_rejects_missing_assessment(self, workspace):
        no_assessment = "## Issues Raised\nNone.\n## Verdict\nAPPROVE\n" + ("x" * 500)
        with pytest.raises(ValueError, match="Missing required section.*Overall Assessment"):
            save_review(workspace, "advisor", "idea", 1, no_assessment)


class TestValidateReviewFile:
    def test_valid_file(self, workspace):
        path = workspace / "proposal_space" / "reviews" / "test.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(VALID_REVIEW)
        assert validate_review_file(path) == []

    def test_nonexistent_file(self, workspace):
        path = workspace / "nope.md"
        errors = validate_review_file(path)
        assert len(errors) == 1
        assert "does not exist" in errors[0]

    def test_short_file(self, workspace):
        path = workspace / "proposal_space" / "reviews" / "short.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("## Overall Assessment\n## Issues Raised\n## Verdict\nAPPROVE")
        errors = validate_review_file(path)
        assert any("too short" in e for e in errors)

    def test_missing_section(self, workspace):
        path = workspace / "proposal_space" / "reviews" / "bad.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("## Overall Assessment\nStuff.\n## Verdict\nAPPROVE\n" + ("x" * 500))
        errors = validate_review_file(path)
        assert any("Issues Raised" in e for e in errors)


class TestPipelineSummary:
    def test_creates_summary(self, workspace):
        path = write_pipeline_summary(
            workspace,
            topic="test topic",
            total_rounds=2,
            agent_calls={"Student": 14, "Advisor": 6, "VP": 3},
            idea_lifecycle=[
                {
                    "slug": "idea1",
                    "created": "R1",
                    "rounds": ["REFINE", "APPROVE"],
                    "final_status": "Final Plan #1",
                },
            ],
            key_decisions=["Round 1: Advisor dropped idea2"],
            review_highlights="Good novelty overall",
        )
        assert path.exists()
        content = path.read_text()
        assert "test topic" in content
        assert "Total Rounds**: 2" in content
        assert "Student: 14" in content
        assert "idea1" in content
        assert "Advisor dropped idea2" in content
