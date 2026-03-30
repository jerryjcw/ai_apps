"""Tests for state_manager.py."""

import json

import pytest

from helpers.state_manager import (
    STAGE_SEQUENCE,
    add_idea,
    add_review_issue,
    advance_stage,
    all_ideas_dead,
    can_approve,
    can_pivot,
    can_refine,
    check_convergence,
    get_active_ideas,
    get_ideas_by_status,
    get_next_stage,
    get_open_issues,
    get_quality_standard,
    get_viability_caveats,
    has_blocking_issues,
    init_state,
    init_workspace,
    is_infeasible,
    load_review_tracker,
    load_state,
    record_round_history,
    log_review_event,
    record_verdict,
    record_viability_assessment,
    resolve_review_issue,
    save_state,
    slugify,
    start_new_round,
    update_idea_status,
)


class TestSlugify:
    def test_basic(self):
        assert slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        assert slugify("Use contrastive decoding!") == "use-contrastive-decoding"

    def test_multiple_spaces(self):
        assert slugify("a   b   c") == "a-b-c"

    def test_truncation(self):
        long = "a" * 100
        assert len(slugify(long)) <= 80


class TestInitWorkspace:
    def test_creates_dirs(self, tmp_path):
        init_workspace(tmp_path)
        assert (tmp_path / "proposal_space" / "state").is_dir()
        assert (tmp_path / "proposal_space" / "literature").is_dir()
        assert (tmp_path / "proposal_space" / "ideas").is_dir()
        assert (tmp_path / "proposal_space" / "hypotheses").is_dir()
        assert (tmp_path / "proposal_space" / "plans").is_dir()
        assert (tmp_path / "proposal_space" / "reviews").is_dir()
        assert (tmp_path / "proposal_space" / "interaction_log").is_dir()
        assert (tmp_path / "proposal_space" / "final").is_dir()


class TestInitAndLoadState:
    def test_init_creates_state_file(self, workspace):
        state = init_state(workspace, "test topic", ["Paper A"])
        assert state["topic"] == "test topic"
        assert state["paper_titles"] == ["Paper A"]
        assert state["current_round"] == 1
        assert state["current_stage"] == STAGE_SEQUENCE[0]
        assert state["quality_standard"] == "lenient"

        # Verify file on disk
        loaded = load_state(workspace)
        assert loaded["topic"] == "test topic"

    def test_init_default_constraints(self, workspace):
        state = init_state(workspace, "topic")
        assert state["constraints"]["max_gpus"] == 8
        assert "ICML" in state["constraints"]["target_venues"]

    def test_init_custom_constraints(self, workspace):
        state = init_state(workspace, "topic", constraints={"max_gpus": 4})
        assert state["constraints"]["max_gpus"] == 4


class TestSaveAndLoad:
    def test_roundtrip(self, workspace):
        init_state(workspace, "roundtrip test")
        state = load_state(workspace)
        state["custom_field"] = 42
        save_state(workspace, state)
        loaded = load_state(workspace)
        assert loaded["custom_field"] == 42
        assert "updated_at" in loaded


class TestAdvanceStage:
    def test_advance(self, workspace):
        init_state(workspace, "topic")
        state = advance_stage(workspace, "stage_2_ideation")
        assert state["current_stage"] == "stage_2_ideation"

    def test_invalid_stage(self, workspace):
        init_state(workspace, "topic")
        with pytest.raises(ValueError, match="Unknown stage"):
            advance_stage(workspace, "nonexistent_stage")


class TestGetNextStage:
    def test_normal(self):
        assert get_next_stage("stage_1_literature") == "stage_2_ideation"

    def test_last(self):
        assert get_next_stage("stage_9_final_output") is None

    def test_invalid(self):
        assert get_next_stage("bogus") is None


class TestIdeaManagement:
    def test_add_idea(self, workspace):
        init_state(workspace, "topic")
        state = add_idea(workspace, "cool-idea", "A Cool Idea")
        assert "cool-idea" in state["ideas"]
        assert state["ideas"]["cool-idea"]["status"] == "candidate"
        assert state["ideas"]["cool-idea"]["title"] == "A Cool Idea"

    def test_update_status(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "idea1", "Idea 1")
        state = update_idea_status(workspace, "idea1", "planning")
        assert state["ideas"]["idea1"]["status"] == "planning"

    def test_update_invalid_status(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "idea1", "Idea 1")
        with pytest.raises(ValueError, match="Unknown status"):
            update_idea_status(workspace, "idea1", "invalid_status")

    def test_update_nonexistent_idea(self, workspace):
        init_state(workspace, "topic")
        with pytest.raises(KeyError, match="not found"):
            update_idea_status(workspace, "ghost", "approved")

    def test_refine_increments_count(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "idea1", "Idea 1")
        state = update_idea_status(workspace, "idea1", "refine", "needs work")
        assert state["ideas"]["idea1"]["refine_count"] == 1
        state = update_idea_status(workspace, "idea1", "refine", "still needs work")
        assert state["ideas"]["idea1"]["refine_count"] == 2

    def test_approved_records_round(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "idea1", "Idea 1")
        state = update_idea_status(workspace, "idea1", "approved")
        assert state["ideas"]["idea1"]["round_approved"] == 1

    def test_pivot_increments_count(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "idea1", "Idea 1")
        state = update_idea_status(workspace, "idea1", "pivoted")
        assert state["pivot_count"] == 1


class TestRecordVerdict:
    def test_advisor_verdict(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "idea1", "Idea 1")
        state = record_verdict(
            workspace,
            "idea1",
            "advisor",
            round_num=1,
            verdict="DEVELOP",
            scores={"novelty": 4, "theory": 3},
            issues=["minor concern"],
        )
        verdicts = state["ideas"]["idea1"]["advisor_verdicts"]
        assert len(verdicts) == 1
        assert verdicts[0]["verdict"] == "DEVELOP"
        assert verdicts[0]["scores"]["novelty"] == 4

    def test_vp_verdict(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "idea1", "Idea 1")
        state = record_verdict(workspace, "idea1", "vp", 1, "REFINE")
        assert len(state["ideas"]["idea1"]["vp_verdicts"]) == 1


class TestQualityStandard:
    def test_round_1(self):
        assert get_quality_standard(1) == "lenient"

    def test_round_2(self):
        assert get_quality_standard(2) == "moderate"

    def test_round_3(self):
        assert get_quality_standard(3) == "strict"

    def test_round_4_clamps(self):
        assert get_quality_standard(4) == "strict"


class TestIdeaQueries:
    def test_get_by_status(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "a", "A")
        add_idea(workspace, "b", "B")
        update_idea_status(workspace, "a", "approved")
        state = load_state(workspace)
        assert get_ideas_by_status(state, "approved") == ["a"]
        assert get_ideas_by_status(state, "candidate") == ["b"]

    def test_get_active(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "a", "A")
        add_idea(workspace, "b", "B")
        add_idea(workspace, "c", "C")
        update_idea_status(workspace, "b", "dropped")
        update_idea_status(workspace, "c", "pivoted")
        state = load_state(workspace)
        assert get_active_ideas(state) == ["a"]


class TestCanRefineAndPivot:
    def test_can_refine(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "a", "A")
        state = load_state(workspace)
        assert can_refine(state, "a") is True

    def test_cannot_refine_after_max(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "a", "A")
        for _ in range(3):
            update_idea_status(workspace, "a", "refine")
        state = load_state(workspace)
        assert can_refine(state, "a") is False

    def test_can_pivot(self, workspace):
        init_state(workspace, "topic")
        state = load_state(workspace)
        assert can_pivot(state) is True

    def test_cannot_pivot_after_max(self, workspace):
        init_state(workspace, "topic")
        for i in range(3):
            add_idea(workspace, f"idea{i}", f"Idea {i}")
            update_idea_status(workspace, f"idea{i}", "pivoted")
        state = load_state(workspace)
        assert can_pivot(state) is False


class TestConvergence:
    def test_converges_with_3_approved(self, workspace):
        init_state(workspace, "topic")
        for name in ["a", "b", "c"]:
            add_idea(workspace, name, name.upper())
            update_idea_status(workspace, name, "approved")
        state = load_state(workspace)
        assert check_convergence(state) is True

    def test_not_converged_with_2(self, workspace):
        init_state(workspace, "topic")
        for name in ["a", "b"]:
            add_idea(workspace, name, name.upper())
            update_idea_status(workspace, name, "approved")
        state = load_state(workspace)
        assert check_convergence(state) is False

    def test_converges_at_max_round(self, workspace):
        state = init_state(workspace, "topic")
        state["current_round"] = 3
        save_state(workspace, state)
        state = load_state(workspace)
        assert check_convergence(state) is True

    def test_converges_with_3_approved_exact(self, workspace):
        init_state(workspace, "topic")
        for name in ["a", "b", "c"]:
            add_idea(workspace, name, name.upper())
            update_idea_status(workspace, name, "approved")
        # Also add a non-approved idea — should not prevent convergence
        add_idea(workspace, "d", "D")
        update_idea_status(workspace, "d", "refine")
        state = load_state(workspace)
        assert check_convergence(state) is True


class TestRoundManagement:
    def test_record_history(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "a", "A")
        update_idea_status(workspace, "a", "approved")
        state = record_round_history(workspace)
        assert len(state["iteration_history"]) == 1
        assert state["iteration_history"][0]["round"] == 1

    def test_start_new_round(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "a", "A")
        update_idea_status(workspace, "a", "refine")
        state = start_new_round(workspace)
        assert state["current_round"] == 2
        assert state["quality_standard"] == "moderate"
        assert state["current_stage"] == "stage_3_hypothesis"


class TestViabilityAssessment:
    """Tests for topic viability assessment (INFEASIBLE early termination)."""

    def test_init_state_has_viability_fields(self, workspace):
        state = init_state(workspace, "topic")
        assert state["pipeline_status"] == "running"
        assert state["viability"] is None

    def test_record_viable(self, workspace):
        init_state(workspace, "topic")
        dims = {
            "saturation": {"rating": "GREEN", "evidence": "only 3 papers in area"},
            "foundation": {"rating": "GREEN", "evidence": "strong base"},
        }
        state = record_viability_assessment(
            workspace, checkpoint=1, verdict="viable", dimensions=dims
        )
        assert state["viability"]["verdict"] == "viable"
        assert state["viability"]["checkpoint"] == 1
        assert state["pipeline_status"] == "running"

    def test_record_viable_with_caveats(self, workspace):
        init_state(workspace, "topic")
        dims = {
            "saturation": {"rating": "YELLOW", "evidence": "getting crowded"},
            "scope": {"rating": "GREEN", "evidence": "well-scoped"},
        }
        caveats = ["Avoid sub-area X, already saturated", "Reframe as Y instead of Z"]
        state = record_viability_assessment(
            workspace,
            checkpoint=1,
            verdict="viable_with_caveats",
            dimensions=dims,
            caveats=caveats,
        )
        assert state["viability"]["verdict"] == "viable_with_caveats"
        assert state["viability"]["caveats"] == caveats
        assert state["pipeline_status"] == "running"

    def test_record_infeasible_sets_pipeline_status(self, workspace):
        init_state(workspace, "topic")
        dims = {
            "saturation": {"rating": "RED", "evidence": "15 papers in 12 months"},
            "timing": {"rating": "RED", "evidence": "community moved on"},
        }
        state = record_viability_assessment(
            workspace,
            checkpoint=1,
            verdict="infeasible",
            dimensions=dims,
            summary="Topic is oversaturated and the community has moved on.",
            alternatives=["Try direction A", "Try direction B"],
            what_would_make_viable="A new dataset or benchmark would reopen interest.",
        )
        assert state["pipeline_status"] == "infeasible"
        assert state["viability"]["verdict"] == "infeasible"
        assert state["viability"]["summary"] == "Topic is oversaturated and the community has moved on."
        assert len(state["viability"]["alternatives"]) == 2
        assert state["viability"]["what_would_make_viable"] != ""

    def test_is_infeasible_helper(self, workspace):
        state = init_state(workspace, "topic")
        assert is_infeasible(state) is False
        record_viability_assessment(
            workspace,
            checkpoint=1,
            verdict="infeasible",
            dimensions={"saturation": {"rating": "RED", "evidence": "crowded"}},
        )
        state = load_state(workspace)
        assert is_infeasible(state) is True

    def test_get_viability_caveats_empty_when_viable(self, workspace):
        state = init_state(workspace, "topic")
        assert get_viability_caveats(state) == []

    def test_get_viability_caveats_returns_caveats(self, workspace):
        init_state(workspace, "topic")
        record_viability_assessment(
            workspace,
            checkpoint=1,
            verdict="viable_with_caveats",
            dimensions={},
            caveats=["Avoid X", "Reframe Y"],
        )
        state = load_state(workspace)
        assert get_viability_caveats(state) == ["Avoid X", "Reframe Y"]

    def test_checkpoint_2_infeasible(self, workspace):
        init_state(workspace, "topic")
        state = record_viability_assessment(
            workspace,
            checkpoint=2,
            verdict="infeasible",
            dimensions={
                "coherence": {"rating": "RED", "evidence": "concepts incompatible"},
                "foundation": {"rating": "RED", "evidence": "no base papers"},
            },
            summary="After evaluating all proposed hypotheses, none could overcome the fundamental incompatibility.",
            alternatives=["Direction A", "Direction B", "Direction C"],
        )
        assert state["pipeline_status"] == "infeasible"
        assert state["viability"]["checkpoint"] == 2

    def test_invalid_verdict_raises(self, workspace):
        init_state(workspace, "topic")
        with pytest.raises(ValueError, match="Unknown viability verdict"):
            record_viability_assessment(
                workspace, checkpoint=1, verdict="maybe", dimensions={}
            )

    def test_invalid_checkpoint_raises(self, workspace):
        init_state(workspace, "topic")
        with pytest.raises(ValueError, match="Checkpoint must be 1 or 2"):
            record_viability_assessment(
                workspace, checkpoint=3, verdict="viable", dimensions={}
            )


class TestReviewTracker:
    """Tests for review issue tracking (severity-gated approval)."""

    def test_empty_tracker(self, workspace):
        init_state(workspace, "topic")
        tracker = load_review_tracker(workspace)
        assert tracker == {}

    def test_add_review_issue(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "idea-a", "Idea A")
        tracker = add_review_issue(
            workspace, "idea-a", "R1-ADV-1", "advisor", 1,
            "severe", "theory", "Core claim is unfounded",
            "Prove it or remove it",
        )
        assert len(tracker["idea-a"]["issues"]) == 1
        issue = tracker["idea-a"]["issues"][0]
        assert issue["id"] == "R1-ADV-1"
        assert issue["severity"] == "severe"
        assert issue["status"] == "open"
        assert issue["category"] == "theory"

    def test_add_multiple_issues(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "idea-a", "Idea A")
        add_review_issue(workspace, "idea-a", "R1-ADV-1", "advisor", 1,
                         "severe", "theory", "Claim unfounded")
        add_review_issue(workspace, "idea-a", "R1-ADV-2", "advisor", 1,
                         "minor", "experiment", "Missing ablation")
        add_review_issue(workspace, "idea-a", "R1-VP-1", "vp", 1,
                         "major", "novelty", "Too similar to prior work")
        tracker = load_review_tracker(workspace)
        assert len(tracker["idea-a"]["issues"]) == 3

    def test_invalid_severity_raises(self, workspace):
        init_state(workspace, "topic")
        with pytest.raises(ValueError, match="Unknown severity"):
            add_review_issue(workspace, "idea-a", "R1-ADV-1", "advisor", 1,
                             "critical", "theory", "bad severity label")

    def test_add_issue_has_history(self, workspace):
        init_state(workspace, "topic")
        tracker = add_review_issue(workspace, "idea-a", "R1-ADV-1", "advisor", 1,
                                   "severe", "theory", "Claim unfounded")
        issue = tracker["idea-a"]["issues"][0]
        assert "history" in issue
        assert len(issue["history"]) == 1
        assert issue["history"][0]["event"] == "opened"
        assert issue["history"][0]["by"] == "advisor"

    def test_resolve_issue(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "idea-a", "Idea A")
        add_review_issue(workspace, "idea-a", "R1-ADV-1", "advisor", 1,
                         "severe", "theory", "Claim unfounded")
        tracker = resolve_review_issue(
            workspace, "idea-a", "R1-ADV-1", "addressed",
            resolved_by="advisor",
            addressed_in="R2_revision", resolution_note="Added proof in Section 3",
        )
        issue = tracker["idea-a"]["issues"][0]
        assert issue["status"] == "addressed"
        assert issue["resolved_by"] == "advisor"
        assert issue["addressed_in"] == "R2_revision"
        assert issue["resolution_note"] == "Added proof in Section 3"
        # History should have: opened + addressed
        assert len(issue["history"]) == 2
        assert issue["history"][1]["event"] == "addressed"
        assert issue["history"][1]["by"] == "advisor"

    def test_resolve_by_cross_reviewer(self, workspace):
        """VP can resolve an advisor-raised issue and vice versa."""
        init_state(workspace, "topic")
        add_review_issue(workspace, "idea-a", "R1-ADV-1", "advisor", 1,
                         "minor", "theory", "issue")
        tracker = resolve_review_issue(
            workspace, "idea-a", "R1-ADV-1", "addressed",
            resolved_by="vp", resolution_note="VP confirmed fix",
        )
        assert tracker["idea-a"]["issues"][0]["resolved_by"] == "vp"

    def test_resolve_by_non_reviewer_raises(self, workspace):
        """Orchestrator, student, or any non-reviewer cannot resolve issues."""
        init_state(workspace, "topic")
        add_review_issue(workspace, "idea-a", "R1-ADV-1", "advisor", 1,
                         "minor", "theory", "issue")
        with pytest.raises(ValueError, match="Only a reviewer"):
            resolve_review_issue(workspace, "idea-a", "R1-ADV-1", "addressed",
                                 resolved_by="orchestrator")
        with pytest.raises(ValueError, match="Only a reviewer"):
            resolve_review_issue(workspace, "idea-a", "R1-ADV-1", "addressed",
                                 resolved_by="student")

    def test_resolve_nonexistent_issue_raises(self, workspace):
        init_state(workspace, "topic")
        add_review_issue(workspace, "idea-a", "R1-ADV-1", "advisor", 1,
                         "minor", "theory", "issue")
        with pytest.raises(KeyError, match="R1-ADV-99"):
            resolve_review_issue(workspace, "idea-a", "R1-ADV-99", "addressed",
                                 resolved_by="advisor")

    def test_resolve_nonexistent_idea_raises(self, workspace):
        init_state(workspace, "topic")
        with pytest.raises(KeyError, match="no-idea"):
            resolve_review_issue(workspace, "no-idea", "R1-ADV-1", "addressed",
                                 resolved_by="advisor")

    def test_resolve_invalid_status_raises(self, workspace):
        init_state(workspace, "topic")
        add_review_issue(workspace, "idea-a", "R1-ADV-1", "advisor", 1,
                         "minor", "theory", "issue")
        with pytest.raises(ValueError, match="'addressed' or 'wontfix'"):
            resolve_review_issue(workspace, "idea-a", "R1-ADV-1", "maybe",
                                 resolved_by="advisor")

    def test_get_open_issues(self, workspace):
        init_state(workspace, "topic")
        add_review_issue(workspace, "idea-a", "R1-ADV-1", "advisor", 1,
                         "severe", "theory", "Claim unfounded")
        add_review_issue(workspace, "idea-a", "R1-ADV-2", "advisor", 1,
                         "minor", "experiment", "Missing ablation")
        add_review_issue(workspace, "idea-a", "R1-VP-1", "vp", 1,
                         "major", "novelty", "Similar to prior work")

        # All 3 open
        assert len(get_open_issues(workspace, "idea-a")) == 3

        # Filter to severe/major only
        blocking = get_open_issues(workspace, "idea-a", {"severe", "major"})
        assert len(blocking) == 2

        # Resolve one (by advisor)
        resolve_review_issue(workspace, "idea-a", "R1-ADV-1", "addressed",
                             resolved_by="advisor")
        blocking = get_open_issues(workspace, "idea-a", {"severe", "major"})
        assert len(blocking) == 1
        assert blocking[0]["id"] == "R1-VP-1"

    def test_has_blocking_issues(self, workspace):
        init_state(workspace, "topic")
        add_review_issue(workspace, "idea-a", "R1-ADV-1", "advisor", 1,
                         "severe", "theory", "Claim unfounded")
        assert has_blocking_issues(workspace, "idea-a") is True

        resolve_review_issue(workspace, "idea-a", "R1-ADV-1", "addressed",
                             resolved_by="advisor")
        assert has_blocking_issues(workspace, "idea-a") is False

    def test_can_approve(self, workspace):
        init_state(workspace, "topic")
        # No issues = can approve
        assert can_approve(workspace, "idea-b") is True

        # Add severe issue = cannot approve
        add_review_issue(workspace, "idea-b", "R1-ADV-1", "advisor", 1,
                         "severe", "theory", "Fatal flaw")
        assert can_approve(workspace, "idea-b") is False

        # Resolve it (by vp) = can approve
        resolve_review_issue(workspace, "idea-b", "R1-ADV-1", "addressed",
                             resolved_by="vp")
        assert can_approve(workspace, "idea-b") is True

    def test_minor_issues_dont_block(self, workspace):
        init_state(workspace, "topic")
        add_review_issue(workspace, "idea-c", "R1-ADV-1", "advisor", 1,
                         "minor", "experiment", "Could add one more baseline")
        add_review_issue(workspace, "idea-c", "R1-VP-1", "vp", 1,
                         "slight", "framing", "Notation could be cleaner")
        assert can_approve(workspace, "idea-c") is True

    def test_mixed_severity_blocks_until_resolved(self, workspace):
        init_state(workspace, "topic")
        add_review_issue(workspace, "idea-d", "R1-ADV-1", "advisor", 1,
                         "major", "baseline", "Missing TIES baseline")
        add_review_issue(workspace, "idea-d", "R1-ADV-2", "advisor", 1,
                         "minor", "framing", "Abstract too long")
        add_review_issue(workspace, "idea-d", "R1-VP-1", "vp", 1,
                         "slight", "notation", "Use consistent subscripts")

        # Major blocks
        assert can_approve(workspace, "idea-d") is False

        # Resolve major (by advisor)
        resolve_review_issue(workspace, "idea-d", "R1-ADV-1", "addressed",
                             resolved_by="advisor",
                             resolution_note="Added TIES as baseline 4")

        # Now can approve (minor + slight don't block)
        assert can_approve(workspace, "idea-d") is True

    def test_wontfix_rejected_for_severe(self, workspace):
        init_state(workspace, "topic")
        add_review_issue(workspace, "idea-e", "R1-ADV-1", "advisor", 1,
                         "severe", "theory", "Method provably wrong")
        with pytest.raises(ValueError, match="must be addressed"):
            resolve_review_issue(workspace, "idea-e", "R1-ADV-1", "wontfix",
                                 resolved_by="advisor",
                                 resolution_note="Disagree with reviewer")
        # Issue remains open and blocking
        assert can_approve(workspace, "idea-e") is False

    def test_wontfix_rejected_for_major(self, workspace):
        init_state(workspace, "topic")
        add_review_issue(workspace, "idea-f", "R1-ADV-1", "advisor", 1,
                         "major", "baseline", "Missing key baseline")
        with pytest.raises(ValueError, match="must be addressed"):
            resolve_review_issue(workspace, "idea-f", "R1-ADV-1", "wontfix",
                                 resolved_by="vp")
        assert can_approve(workspace, "idea-f") is False

    def test_wontfix_allowed_for_minor(self, workspace):
        init_state(workspace, "topic")
        add_review_issue(workspace, "idea-g", "R1-ADV-1", "advisor", 1,
                         "minor", "experiment", "Could add ablation")
        resolve_review_issue(workspace, "idea-g", "R1-ADV-1", "wontfix",
                             resolved_by="advisor",
                             resolution_note="Not needed for core claim")
        assert can_approve(workspace, "idea-g") is True

    def test_wontfix_allowed_for_slight(self, workspace):
        init_state(workspace, "topic")
        add_review_issue(workspace, "idea-h", "R1-ADV-1", "advisor", 1,
                         "slight", "framing", "Notation nitpick")
        resolve_review_issue(workspace, "idea-h", "R1-ADV-1", "wontfix",
                             resolved_by="vp",
                             resolution_note="Stylistic choice")
        assert can_approve(workspace, "idea-h") is True

    def test_log_review_event_still_open(self, workspace):
        init_state(workspace, "topic")
        add_review_issue(workspace, "idea-x", "R1-VP-1", "vp", 1,
                         "major", "novelty", "Too similar to prior work")
        tracker = log_review_event(
            workspace, "idea-x", "R1-VP-1", "still_open",
            by="vp", detail="Student added a paragraph but did not differentiate")
        issue = tracker["idea-x"]["issues"][0]
        # Status unchanged — still open
        assert issue["status"] == "open"
        # History has: opened + still_open
        assert len(issue["history"]) == 2
        assert issue["history"][1]["event"] == "still_open"
        assert issue["history"][1]["by"] == "vp"

    def test_log_review_event_nonexistent_raises(self, workspace):
        init_state(workspace, "topic")
        with pytest.raises(KeyError, match="no-idea"):
            log_review_event(workspace, "no-idea", "R1-VP-1", "still_open",
                             by="vp")

    def test_full_issue_lifecycle(self, workspace):
        """Full lifecycle: opened → still_open → still_open → addressed."""
        init_state(workspace, "topic")
        add_review_issue(workspace, "idea-y", "R1-ADV-1", "advisor", 1,
                         "severe", "theory", "Core flaw")
        # Round 1 re-review: still open
        log_review_event(workspace, "idea-y", "R1-ADV-1", "still_open",
                         by="advisor", detail="Student tried but flaw remains")
        # Round 2 re-review: still open (VP checks this time)
        log_review_event(workspace, "idea-y", "R1-ADV-1", "still_open",
                         by="vp", detail="Agree with advisor, still flawed")
        # Round 3 re-review: finally resolved
        resolve_review_issue(workspace, "idea-y", "R1-ADV-1", "addressed",
                             resolved_by="advisor",
                             addressed_in="R3_revision",
                             resolution_note="Proof now correct")
        tracker = load_review_tracker(workspace)
        issue = tracker["idea-y"]["issues"][0]
        assert issue["status"] == "addressed"
        assert len(issue["history"]) == 4
        events = [h["event"] for h in issue["history"]]
        assert events == ["opened", "still_open", "still_open", "addressed"]
        assert issue["history"][1]["by"] == "advisor"
        assert issue["history"][2]["by"] == "vp"
        assert issue["history"][3]["by"] == "advisor"


class TestAllIdeasDead:
    """Tests for all-proposals-dead detection."""

    def test_no_ideas(self, workspace):
        state = init_state(workspace, "topic")
        assert all_ideas_dead(state) is True  # vacuously true

    def test_active_ideas_exist(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "a", "Idea A")
        state = load_state(workspace)
        assert all_ideas_dead(state) is False

    def test_all_dropped(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "a", "Idea A")
        add_idea(workspace, "b", "Idea B")
        update_idea_status(workspace, "a", "dropped")
        update_idea_status(workspace, "b", "dropped")
        state = load_state(workspace)
        assert all_ideas_dead(state) is True

    def test_all_pivoted(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "a", "Idea A")
        update_idea_status(workspace, "a", "pivoted")
        state = load_state(workspace)
        assert all_ideas_dead(state) is True

    def test_mixed_dead_and_alive(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "a", "Idea A")
        add_idea(workspace, "b", "Idea B")
        add_idea(workspace, "c", "Idea C")
        update_idea_status(workspace, "a", "dropped")
        update_idea_status(workspace, "b", "pivoted")
        # c is still candidate (active)
        state = load_state(workspace)
        assert all_ideas_dead(state) is False

    def test_approved_is_not_dead(self, workspace):
        init_state(workspace, "topic")
        add_idea(workspace, "a", "Idea A")
        add_idea(workspace, "b", "Idea B")
        update_idea_status(workspace, "a", "approved")
        update_idea_status(workspace, "b", "dropped")
        state = load_state(workspace)
        assert all_ideas_dead(state) is False
