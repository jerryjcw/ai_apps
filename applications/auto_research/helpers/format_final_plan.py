"""Render final research plan .md from structured data.

Uses the 14-section template adapted from llm_research/spec.md
and the proven output patterns from output_zh.md.
"""

from __future__ import annotations


def format_plan(
    rank: int,
    idea_slug: str,
    title: str,
    hypothesis_text: str,
    plan_text: str,
    advisor_reviews: list[str],
    vp_reviews: list[str],
    scores: dict[str, int] | None = None,
    venue: str = "",
    confidence: str = "",
) -> str:
    """Render a comprehensive 14-section research plan.

    Parameters
    ----------
    rank : Position in final ranking (1-based).
    idea_slug : Short identifier.
    title : Paper-like title.
    hypothesis_text : Full hypothesis markdown (sections 2-6 extracted from it).
    plan_text : Full experiment plan markdown (sections 7-10 extracted from it).
    advisor_reviews : List of advisor review texts across rounds.
    vp_reviews : List of VP review texts across rounds.
    scores : 9-dimension score dict (optional).
    venue : Recommended target venue.
    confidence : Confidence level string.
    """
    scores = scores or {}
    score_table = _render_score_table(scores) if scores else "(scores not available)"

    review_appendix = _render_review_appendix(advisor_reviews, vp_reviews)

    return f"""# Research Plan #{rank}: {title}

> **Idea slug**: `{idea_slug}`
> **Confidence**: {confidence or "N/A"}
> **Recommended venue**: {venue or "N/A"}

---

## 1. Title

{title}

## 2. One-Sentence Thesis

{_extract_section(hypothesis_text, "Thesis statement", "thesis", "(not provided)")}

## 3. Research Area Classification

{_extract_section(hypothesis_text, "Research area", "area", "(not provided)")}

## 4. Closest Prior Work

{_extract_section(hypothesis_text, "Closest prior work", "prior", "(not provided)")}

## 5. Problem Gap

{_extract_section(hypothesis_text, "Problem gap", "gap", "(not provided)")}

## 6. Theoretical Basis

{_extract_section(hypothesis_text, "Theoretical basis", "theory", "(not provided)")}

## 7. Method Sketch

{_extract_section(plan_text, "Method sketch", "method", "(not provided)")}

## 8. Method Variants (Multi-Level Framework)

{_extract_section(plan_text, "Variant", "variant", "(not provided)")}

## 9. Implementation Plan

{_extract_section(plan_text, "Implementation plan", "implementation", "(not provided)")}

## 10. Experimental Plan

{_extract_section(plan_text, "Experimental plan", "experiment", "(not provided)")}

## 11. Paper Storyline

{_extract_section(plan_text, "storyline", "story", "(not provided)")}

## 12. Novelty Risk Assessment

{_extract_section(plan_text, "Novelty risk", "risk", "(not provided)")}

## 13. Quality Checklist Verification

- [ ] Core method unpacked to implementation-level granularity
- [ ] Cannot be reduced to a known method in one sentence
- [ ] No circular estimation steps (or acknowledged with fix)
- [ ] Cross-over claims have actionable closed-loop feedback
- [ ] 3+ failure cases addressed in method design
- [ ] Weakest assumption identified with graceful degradation
- [ ] Multi-level framework with independent scientific questions per level
- [ ] Adjacent-field techniques considered
- [ ] 5-8 prior works with detailed like/unlike analysis
- [ ] Direction/signal estimation non-circular
- [ ] Approximation gaps quantified
- [ ] Theoretical guarantees applicable to use scenario

## 14. Final Verdict

**Confidence**: {confidence or "N/A"}
**Recommended Venue**: {venue or "N/A"}

### 9-Dimension Score Summary

{score_table}

---

## Appendix: Review History

{review_appendix}
"""


def format_summary_table(plans: list[dict]) -> str:
    """Render a comparison table of all final plans.

    Each entry in `plans` should have keys:
        rank, title, area, novelty, feasibility, confidence, venue
    """
    header = "| Rank | Title | Area | Novelty | Feasibility | Confidence | Venue |"
    separator = "|------|-------|------|---------|-------------|------------|-------|"
    rows = []
    for p in plans:
        rows.append(
            f"| {p.get('rank', '')} "
            f"| {p.get('title', '')} "
            f"| {p.get('area', '')} "
            f"| {p.get('novelty', '')} "
            f"| {p.get('feasibility', '')} "
            f"| {p.get('confidence', '')} "
            f"| {p.get('venue', '')} |"
        )

    return f"""# Research Plan Summary

{header}
{separator}
{chr(10).join(rows)}
"""


def _render_score_table(scores: dict[str, int]) -> str:
    """Render 9-dimension score table."""
    dimensions = [
        "novelty_vs_base",
        "novelty_vs_recent",
        "theoretical_depth",
        "implementation_risk",
        "experimental_clarity",
        "storyline_strength",
        "reviewer_attack_risk",
        "six_month_executability",
        "twelve_month_upside",
    ]
    labels = {
        "novelty_vs_base": "Novelty vs base papers",
        "novelty_vs_recent": "Novelty vs recent neighbors",
        "theoretical_depth": "Theoretical depth",
        "implementation_risk": "Implementation risk",
        "experimental_clarity": "Experimental clarity",
        "storyline_strength": "Storyline strength",
        "reviewer_attack_risk": "Reviewer attack risk",
        "six_month_executability": "6-month executability",
        "twelve_month_upside": "12-month upside",
    }
    rows = []
    total = 0
    for dim in dimensions:
        score = scores.get(dim, scores.get(dim.replace("_", ""), 0))
        label = labels.get(dim, dim)
        rows.append(f"| {label} | {score}/5 |")
        total += score

    return (
        "| Dimension | Score |\n|-----------|-------|\n"
        + "\n".join(rows)
        + f"\n| **Total** | **{total}/45** |"
    )


def _render_review_appendix(
    advisor_reviews: list[str], vp_reviews: list[str]
) -> str:
    """Render review history appendix."""
    parts = []
    for i, review in enumerate(advisor_reviews, 1):
        parts.append(f"### Advisor Review (Round {i})\n\n{review}\n")
    for i, review in enumerate(vp_reviews, 1):
        parts.append(f"### Visiting Professor Review (Round {i})\n\n{review}\n")
    return "\n".join(parts) if parts else "(no reviews recorded)"


def _extract_section(
    text: str, *keywords: str, fallback: str = ""
) -> str:
    """Try to extract a section from markdown text by heading keywords.

    Looks for headings containing any of the keywords (case-insensitive).
    Returns the content under that heading until the next heading of same or
    higher level, or end of text. If not found, returns the full text as
    fallback (the content is likely already the right section).
    """
    import re

    for kw in keywords:
        # Match ## heading containing keyword
        pattern = rf"^(#{1,4})\s+[^\n]*{re.escape(kw)}[^\n]*\n(.*?)(?=^#{1,4}\s|\Z)"
        match = re.search(pattern, text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(2).strip()

    # If no section heading found, return fallback or trimmed text
    if fallback and fallback != text:
        return fallback
    return text.strip()
