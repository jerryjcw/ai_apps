"""Tests for parse_review.py."""

from helpers.parse_review import (
    IdeaReview,
    RevisionViolation,
    ViabilityAssessment,
    extract_attack_vectors,
    extract_idea_blocks,
    extract_issues,
    extract_ranking,
    extract_scores,
    extract_suggestions,
    extract_verdict,
    parse_review,
    parse_viability_assessment,
    validate_student_revision,
)

SAMPLE_REVIEW = """
Here is my review of the proposals.

=== IDEA: contrastive-cot ===
VERDICT: REFINE
SCORE_NOVELTY: 4
SCORE_THEORY: 3
SCORE_FEASIBILITY: 4
ISSUES:
1. [theory] The contrastive signal may not preserve gradient information across layers.
2. [experiment] Missing comparison with standard CoT baseline.
SUGGESTIONS:
1. Consider adding a gradient-preservation proof or empirical validation.
2. Include CoT + self-consistency as a baseline.
=== END IDEA ===

=== IDEA: token-contrast ===
VERDICT: APPROVE
SCORE_NOVELTY: 5
SCORE_THEORY: 4
SCORE_FEASIBILITY: 5
ISSUES:
SUGGESTIONS:
=== END IDEA ===

=== IDEA: naive-ensemble ===
VERDICT: DROP
FATAL_FLAW: This exact method was published in Li et al. 2025.
=== END IDEA ===

RANKING:
1. token-contrast - Strongest novelty and cleanest implementation path.
2. contrastive-cot - Promising but needs theoretical grounding.
"""

SAMPLE_VP_REVIEW = """
=== IDEA: contrastive-cot ===
VERDICT: REFINE
RECENT_WORK_CHECK: Found Chen et al. (2026/02) with similar contrastive mechanism but for code generation.
ISSUES:
1. [{severity: critical}] The assumption that contrastive pairs are independent is violated when both responses share the same chain-of-thought prefix.
2. [{severity: major}] No ablation isolating the effect of contrastive loss vs. standard reward.
ATTACK_VECTORS:
1. ATTACK: This is just DPO applied to reasoning chains, not a new method.
   DEFENSE: Unlike DPO, we operate at token-level with gradient-aware weighting, not sequence-level preference.
2. ATTACK: Computational overhead of generating contrastive pairs negates efficiency gains.
   DEFENSE: Show wall-clock improvement due to better sample efficiency offsetting pair generation cost.
3. ATTACK: Results on GSM8K may not generalize to harder benchmarks.
   DEFENSE: Include MATH-500 and AMC/AIME results showing consistent improvement.
=== END IDEA ===
"""


class TestExtractIdeaBlocks:
    def test_extracts_all_blocks(self):
        blocks = extract_idea_blocks(SAMPLE_REVIEW)
        assert len(blocks) == 3
        slugs = [b[0] for b in blocks]
        assert "contrastive-cot" in slugs
        assert "token-contrast" in slugs
        assert "naive-ensemble" in slugs

    def test_block_content(self):
        blocks = extract_idea_blocks(SAMPLE_REVIEW)
        cot_block = next(b[1] for b in blocks if b[0] == "contrastive-cot")
        assert "VERDICT: REFINE" in cot_block

    def test_empty_text(self):
        assert extract_idea_blocks("no blocks here") == []


class TestExtractVerdict:
    def test_refine(self):
        blocks = extract_idea_blocks(SAMPLE_REVIEW)
        cot = next(b[1] for b in blocks if b[0] == "contrastive-cot")
        assert extract_verdict(cot) == "REFINE"

    def test_approve(self):
        blocks = extract_idea_blocks(SAMPLE_REVIEW)
        tc = next(b[1] for b in blocks if b[0] == "token-contrast")
        assert extract_verdict(tc) == "APPROVE"

    def test_drop(self):
        blocks = extract_idea_blocks(SAMPLE_REVIEW)
        ne = next(b[1] for b in blocks if b[0] == "naive-ensemble")
        assert extract_verdict(ne) == "DROP"

    def test_missing(self):
        assert extract_verdict("no verdict here") == ""


class TestExtractScores:
    def test_extracts_all(self):
        blocks = extract_idea_blocks(SAMPLE_REVIEW)
        cot = next(b[1] for b in blocks if b[0] == "contrastive-cot")
        scores = extract_scores(cot)
        assert scores == {"novelty": 4, "theory": 3, "feasibility": 4}

    def test_no_scores(self):
        assert extract_scores("just text") == {}


class TestExtractIssues:
    def test_category_format(self):
        blocks = extract_idea_blocks(SAMPLE_REVIEW)
        cot = next(b[1] for b in blocks if b[0] == "contrastive-cot")
        issues = extract_issues(cot)
        assert len(issues) == 2
        assert issues[0]["category"] == "theory"
        assert "gradient information" in issues[0]["description"]

    def test_severity_format(self):
        blocks = extract_idea_blocks(SAMPLE_VP_REVIEW)
        cot = next(b[1] for b in blocks if b[0] == "contrastive-cot")
        issues = extract_issues(cot)
        assert len(issues) == 2
        assert issues[0]["severity"] == "critical"
        assert issues[1]["severity"] == "major"

    def test_empty_issues(self):
        blocks = extract_idea_blocks(SAMPLE_REVIEW)
        tc = next(b[1] for b in blocks if b[0] == "token-contrast")
        issues = extract_issues(tc)
        assert issues == []

    def test_combined_severity_category_format(self):
        text = """ISSUES:
1. [{severity: severe}] [theory] The core claim conflates first and second order.
2. [{severity: major}] [baseline] Missing TIES-Merging comparison.
3. [{severity: minor}] [framing] Abstract is too long."""
        issues = extract_issues(text)
        assert len(issues) == 3
        assert issues[0]["severity"] == "severe"
        assert issues[0]["category"] == "theory"
        assert "first and second order" in issues[0]["description"]
        assert issues[1]["severity"] == "major"
        assert issues[1]["category"] == "baseline"
        assert issues[2]["severity"] == "minor"


class TestExtractSuggestions:
    def test_extracts(self):
        blocks = extract_idea_blocks(SAMPLE_REVIEW)
        cot = next(b[1] for b in blocks if b[0] == "contrastive-cot")
        suggestions = extract_suggestions(cot)
        assert len(suggestions) == 2
        assert "gradient-preservation" in suggestions[0]


class TestExtractAttackVectors:
    def test_extracts_all(self):
        blocks = extract_idea_blocks(SAMPLE_VP_REVIEW)
        cot = next(b[1] for b in blocks if b[0] == "contrastive-cot")
        vectors = extract_attack_vectors(cot)
        assert len(vectors) == 3
        assert "DPO" in vectors[0]["attack"]
        assert "token-level" in vectors[0]["defense"]

    def test_no_vectors(self):
        assert extract_attack_vectors("no vectors") == []


class TestExtractRanking:
    def test_extracts(self):
        ranking = extract_ranking(SAMPLE_REVIEW)
        assert len(ranking) == 2
        assert ranking[0]["slug"] == "token-contrast"
        assert "novelty" in ranking[0]["justification"].lower()


class TestParseReview:
    def test_full_parse(self):
        result = parse_review(SAMPLE_REVIEW)
        assert len(result.ideas) == 3
        assert result.ideas["contrastive-cot"].verdict == "REFINE"
        assert result.ideas["token-contrast"].verdict == "APPROVE"
        assert result.ideas["naive-ensemble"].verdict == "DROP"
        assert result.ideas["naive-ensemble"].fatal_flaw != ""
        assert len(result.ranking) == 2

    def test_vp_review_parse(self):
        result = parse_review(SAMPLE_VP_REVIEW)
        cot = result.ideas["contrastive-cot"]
        assert cot.verdict == "REFINE"
        assert "Chen et al." in cot.recent_work_check
        assert len(cot.attack_vectors) == 3
        assert len(cot.issues) == 2


# --- Viability assessment parsing tests ---

SAMPLE_VIABLE_ASSESSMENT = """
VIABILITY_VERDICT: VIABLE

DIMENSION_SATURATION: GREEN
EVIDENCE_SATURATION: Only 4 papers in this sub-area in the last 12 months.

DIMENSION_FOUNDATION: GREEN
EVIDENCE_FOUNDATION: Strong theoretical foundation from Smith et al. 2024 and Jones 2025.

DIMENSION_SCOPE: GREEN
EVIDENCE_SCOPE: Well-defined scope targeting a specific gap in reasoning evaluation.

DIMENSION_COHERENCE: GREEN
EVIDENCE_COHERENCE: Concepts are naturally compatible and have overlapping assumptions.

DIMENSION_TIMING: GREEN
EVIDENCE_TIMING: Active research area with recent momentum.
"""

SAMPLE_CAVEATS_ASSESSMENT = """
VIABILITY_VERDICT: VIABLE_WITH_CAVEATS

DIMENSION_SATURATION: YELLOW
EVIDENCE_SATURATION: Sub-area of contrastive methods is getting crowded (8 papers in 2025).

DIMENSION_FOUNDATION: GREEN
EVIDENCE_FOUNDATION: Strong base from Li et al. 2023 and follow-ups.

DIMENSION_SCOPE: GREEN
EVIDENCE_SCOPE: Appropriately scoped to small LMs.

DIMENSION_COHERENCE: GREEN
EVIDENCE_COHERENCE: Concepts are compatible.

DIMENSION_TIMING: YELLOW
EVIDENCE_TIMING: Window may be narrowing as larger models reduce the need.

CAVEATS:
1. Avoid pure contrastive decoding extensions -- the area is saturated. Focus on the reasoning-specific angle.
2. Frame contribution around small LMs specifically, not general contrastive methods.
"""

SAMPLE_INFEASIBLE_ASSESSMENT = """
VIABILITY_VERDICT: INFEASIBLE

DIMENSION_SATURATION: RED
EVIDENCE_SATURATION: 15 papers published in the last 12 months covering every reasonable variation of this approach, including Wang et al. (2025), Chen et al. (2026), and Park et al. (2026).

DIMENSION_FOUNDATION: GREEN
EVIDENCE_FOUNDATION: Well-established base.

DIMENSION_SCOPE: GREEN
EVIDENCE_SCOPE: Appropriate scope.

DIMENSION_COHERENCE: RED
EVIDENCE_COHERENCE: The proposed combination of causal inference with token-level decoding contradicts the i.i.d. assumption required by the causal framework. Pearl (2009) explicitly notes this limitation.

DIMENSION_TIMING: YELLOW
EVIDENCE_TIMING: Community interest is waning.

INFEASIBLE_SUMMARY: Based on the current literature landscape, this direction faces two structural challenges: the area is heavily saturated with 15+ recent papers, and the proposed causal-contrastive combination faces a fundamental theoretical incompatibility.

ALTERNATIVE_DIRECTIONS:
1. Apply causal inference to model selection rather than decoding -- this avoids the i.i.d. conflict and has only 2 recent papers.
2. Focus on contrastive methods for code generation, where the structured output makes contrastive pairs more meaningful.
3. Explore reasoning improvements via retrieval-augmented approaches, which complement rather than conflict with causal assumptions.

WHAT_WOULD_MAKE_VIABLE: If a theoretical framework resolving the i.i.d. conflict were developed, or if a new evaluation benchmark specifically for causal decoding emerged.
"""

SAMPLE_CHECKPOINT2_REASSESSMENT = """
REASSESSMENT_VERDICT: INFEASIBLE

FAILURE_PATTERN: Every proposed idea converged on superficial variations of existing contrastive methods. The fundamental issue is that the topic constrains ideation to a space where all reasonable approaches have been explored.

INFEASIBLE_SUMMARY: After evaluating 10 candidate ideas across 2 generation rounds, none could establish sufficient novelty beyond existing work. The constraint space is exhausted.

ALTERNATIVE_DIRECTIONS:
1. Pivot to contrastive methods for multi-modal reasoning, which is largely unexplored.
2. Investigate non-contrastive approaches to small LM reasoning improvement.
3. Focus on theoretical analysis of WHY contrastive decoding works, rather than new methods.

WHAT_WOULD_MAKE_VIABLE: A breakthrough in a related field that opens new design space for contrastive approaches.
"""

SAMPLE_CHECKPOINT2_RETRY = """
REASSESSMENT_VERDICT: RETRY_WITH_GUIDANCE

FAILURE_ANALYSIS: The student kept proposing token-level methods, missing the opportunity to work at the reasoning-chain level.

GUIDANCE:
1. Explore chain-level contrastive signals rather than token-level -- this is the underexplored gap.
2. Consider combining contrastive decoding with tree search methods.
3. Avoid any approach that is purely a decoding-time intervention -- reviewers will see it as incremental.
"""


class TestParseViabilityAssessment:
    def test_viable(self):
        result = parse_viability_assessment(SAMPLE_VIABLE_ASSESSMENT)
        assert result.verdict == "viable"
        assert len(result.dimensions) == 5
        assert result.dimensions["saturation"]["rating"] == "GREEN"
        assert "4 papers" in result.dimensions["saturation"]["evidence"]
        assert result.caveats == []
        assert result.alternatives == []

    def test_viable_with_caveats(self):
        result = parse_viability_assessment(SAMPLE_CAVEATS_ASSESSMENT)
        assert result.verdict == "viable_with_caveats"
        assert result.dimensions["saturation"]["rating"] == "YELLOW"
        assert len(result.caveats) == 2
        assert "saturated" in result.caveats[0].lower()

    def test_infeasible(self):
        result = parse_viability_assessment(SAMPLE_INFEASIBLE_ASSESSMENT)
        assert result.verdict == "infeasible"
        assert result.dimensions["saturation"]["rating"] == "RED"
        assert result.dimensions["coherence"]["rating"] == "RED"
        assert "structural challenges" in result.summary
        assert len(result.alternatives) == 3
        assert "causal inference" in result.alternatives[0].lower()
        assert "i.i.d." in result.what_would_make_viable

    def test_checkpoint2_infeasible(self):
        result = parse_viability_assessment(SAMPLE_CHECKPOINT2_REASSESSMENT)
        assert result.reassessment_verdict == "infeasible"
        assert result.verdict == "infeasible"
        assert "exhausted" in result.summary
        assert len(result.alternatives) == 3
        assert "superficial variations" in result.failure_pattern

    def test_checkpoint2_retry(self):
        result = parse_viability_assessment(SAMPLE_CHECKPOINT2_RETRY)
        assert result.reassessment_verdict == "retry_with_guidance"
        assert "token-level" in result.failure_analysis
        assert len(result.guidance) == 3
        assert "chain-level" in result.guidance[0]

    def test_empty_text(self):
        result = parse_viability_assessment("")
        assert result.verdict == ""
        assert result.dimensions == {}
        assert result.caveats == []

    def test_raw_text_preserved(self):
        result = parse_viability_assessment(SAMPLE_INFEASIBLE_ASSESSMENT)
        assert result.raw_text == SAMPLE_INFEASIBLE_ASSESSMENT


class TestValidateStudentRevision:
    """Tests for detecting manipulation attempts in Student revision output."""

    def test_clean_revision_passes(self):
        text = """\
=== IDEA: contrastive-decoding ===
### Thesis Statement
We propose a token-level contrastive objective that ...

### Theoretical Basis
Building on information-theoretic frameworks ...

### Method Sketch
Input tokens → expert LM logits → amateur LM logits → contrastive score → ...

ADDRESSED #R1-ADV-1: Replaced single-trick heuristic with 3-level framework
ADDRESSED #R1-VP-1: Added ablation isolating the temperature parameter
=== END IDEA ===
"""
        violations = validate_student_revision(text)
        assert violations == []

    def test_detects_appeal_to_reconsider(self):
        text = "We hope the reviewers will reconsider our approach given these changes."
        violations = validate_student_revision(text)
        assert len(violations) >= 1
        assert any("reconsider" in v.matched_text.lower() for v in violations)

    def test_detects_please_approve(self):
        text = "Please approve this revised proposal."
        violations = validate_student_revision(text)
        assert len(violations) >= 1

    def test_detects_sufficient_for_approval(self):
        text = "These changes should be sufficient for approval."
        violations = validate_student_revision(text)
        assert len(violations) >= 1

    def test_detects_respectfully_disagree(self):
        text = "We respectfully disagree with the reviewer's assessment."
        violations = validate_student_revision(text)
        assert len(violations) >= 1

    def test_detects_reviewer_overlooked(self):
        text = "The reviewer may have overlooked our contribution in Section 3."
        violations = validate_student_revision(text)
        assert len(violations) >= 1

    def test_detects_note_to_reviewers(self):
        text = "Note to reviewers: the baseline comparison was already addressed."
        violations = validate_student_revision(text)
        assert len(violations) >= 1

    def test_detects_unfair_review(self):
        text = "This was a harsh review that does not reflect the quality of our work."
        violations = validate_student_revision(text)
        assert len(violations) >= 1

    def test_detects_ask_for_leniency(self):
        text = "We ask for leniency given the time constraints."
        violations = validate_student_revision(text)
        assert len(violations) >= 1

    def test_detects_severity_downgrade_attempt(self):
        text = "This issue should be minor rather than major."
        violations = validate_student_revision(text)
        assert len(violations) >= 1

    def test_detects_deserves_approval(self):
        text = "Our proposal deserves approval based on these improvements."
        violations = validate_student_revision(text)
        assert len(violations) >= 1

    def test_detects_ready_for_approval(self):
        text = "The method is now ready for final approval."
        violations = validate_student_revision(text)
        assert len(violations) >= 1

    def test_multiple_violations_all_caught(self):
        text = """\
We respectfully disagree with the reviewer's concerns.
Please reconsider our proposal.
This should now be approved.
"""
        violations = validate_student_revision(text)
        assert len(violations) >= 3

    def test_violation_has_line_number(self):
        text = "Line one is fine.\nWe hope the reviewers will reconsider."
        violations = validate_student_revision(text)
        assert len(violations) >= 1
        assert violations[0].line_number == 2

    def test_case_insensitive(self):
        text = "WE RESPECTFULLY DISAGREE with the evaluation."
        violations = validate_student_revision(text)
        assert len(violations) >= 1

    def test_legitimate_method_description_not_flagged(self):
        """Technical use of 'note' or 'should' in method description is fine."""
        text = """\
Note that the gradient is computed with respect to the contrastive objective.
The model should converge after 10k steps based on our learning rate schedule.
We address this concern by adding a regularization term to the loss function.
"""
        violations = validate_student_revision(text)
        assert violations == []

    def test_empty_text(self):
        violations = validate_student_revision("")
        assert violations == []
