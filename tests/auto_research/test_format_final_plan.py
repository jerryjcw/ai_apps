"""Tests for format_final_plan.py."""

from helpers.format_final_plan import format_plan, format_summary_table


class TestFormatPlan:
    def test_basic_rendering(self):
        result = format_plan(
            rank=1,
            idea_slug="contrastive-cot",
            title="Contrastive Chain-of-Thought Decoding",
            hypothesis_text="## Thesis statement\nSmall LMs can reason better with contrastive signals.",
            plan_text="## Method sketch\nCompute contrastive logits between expert and amateur.",
            advisor_reviews=["Round 1: APPROVE - strong novelty."],
            vp_reviews=["Round 1: REFINE - needs more baselines."],
            scores={"novelty_vs_base": 5, "novelty_vs_recent": 4},
            venue="ICML 2027",
            confidence="High",
        )
        assert "Research Plan #1" in result
        assert "contrastive-cot" in result
        assert "ICML 2027" in result
        assert "High" in result
        assert "Small LMs can reason better" in result
        assert "Contrastive Chain-of-Thought" in result
        assert "5/5" in result  # novelty_vs_base score
        assert "Round 1: APPROVE" in result
        assert "Quality Checklist" in result

    def test_14_sections_present(self):
        result = format_plan(
            rank=1,
            idea_slug="test",
            title="Test Plan",
            hypothesis_text="hypothesis",
            plan_text="plan",
            advisor_reviews=[],
            vp_reviews=[],
        )
        for section_num in range(1, 15):
            assert f"## {section_num}." in result

    def test_checklist_present(self):
        result = format_plan(
            rank=1,
            idea_slug="test",
            title="Test",
            hypothesis_text="",
            plan_text="",
            advisor_reviews=[],
            vp_reviews=[],
        )
        assert "- [ ] Core method unpacked" in result
        assert "- [ ] Cannot be reduced" in result
        assert "- [ ] No circular estimation" in result


class TestFormatSummaryTable:
    def test_renders_table(self):
        plans = [
            {
                "rank": 1,
                "title": "Idea A",
                "area": "LLM",
                "novelty": "5/5",
                "feasibility": "4/5",
                "confidence": "High",
                "venue": "ICML",
            },
            {
                "rank": 2,
                "title": "Idea B",
                "area": "RL",
                "novelty": "4/5",
                "feasibility": "3/5",
                "confidence": "Medium",
                "venue": "NeurIPS",
            },
        ]
        result = format_summary_table(plans)
        assert "Research Plan Summary" in result
        assert "Idea A" in result
        assert "Idea B" in result
        assert "ICML" in result
        assert "NeurIPS" in result

    def test_empty_plans(self):
        result = format_summary_table([])
        assert "Research Plan Summary" in result
