"""Extract structured data from reviewer text output.

Reviewers output blocks delimited by:
    === IDEA: slug ===
    ... content with VERDICT:, SCORE_*, ISSUES:, SUGGESTIONS:, ATTACK_VECTORS: ...
    === END IDEA ===

This module parses those blocks into structured dicts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class IdeaReview:
    slug: str
    verdict: str = ""
    scores: dict[str, int] = field(default_factory=dict)
    issues: list[dict[str, str]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    attack_vectors: list[dict[str, str]] = field(default_factory=list)
    recent_work_check: str = ""
    fatal_flaw: str = ""
    raw_text: str = ""


@dataclass
class ReviewResult:
    ideas: dict[str, IdeaReview] = field(default_factory=dict)
    ranking: list[dict[str, str]] = field(default_factory=list)
    raw_text: str = ""


def parse_review(review_text: str) -> ReviewResult:
    """Parse a full review text into structured ReviewResult."""
    result = ReviewResult(raw_text=review_text)

    # Extract idea blocks
    blocks = extract_idea_blocks(review_text)
    for slug, block_text in blocks:
        idea = IdeaReview(slug=slug, raw_text=block_text)
        idea.verdict = extract_verdict(block_text)
        idea.scores = extract_scores(block_text)
        idea.issues = extract_issues(block_text)
        idea.suggestions = extract_suggestions(block_text)
        idea.attack_vectors = extract_attack_vectors(block_text)
        idea.recent_work_check = _extract_single_field(
            block_text, "RECENT_WORK_CHECK"
        )
        idea.fatal_flaw = _extract_single_field(block_text, "FATAL_FLAW")
        result.ideas[slug] = idea

    # Extract ranking (after all idea blocks)
    result.ranking = extract_ranking(review_text)

    return result


def extract_idea_blocks(text: str) -> list[tuple[str, str]]:
    """Extract (slug, block_content) pairs from === IDEA: slug === markers."""
    pattern = r"===\s*IDEA:\s*(.+?)\s*===\s*\n(.*?)===\s*END\s+IDEA\s*==="
    matches = re.findall(pattern, text, re.DOTALL)
    return [(slug.strip(), content.strip()) for slug, content in matches]


def extract_verdict(block: str) -> str:
    """Extract VERDICT: line from an idea block."""
    match = re.search(r"^VERDICT:\s*(.+)$", block, re.MULTILINE)
    if match:
        return match.group(1).strip().upper()
    return ""


def extract_scores(block: str) -> dict[str, int]:
    """Extract SCORE_* lines into {dimension: int} dict."""
    scores: dict[str, int] = {}
    for match in re.finditer(r"^SCORE_(\w+):\s*(\d+)", block, re.MULTILINE):
        dimension = match.group(1).lower()
        scores[dimension] = int(match.group(2))
    return scores


def extract_issues(block: str) -> list[dict[str, str]]:
    """Extract numbered ISSUES into structured list.

    Supports multiple formats:
    1. [category] description
    2. [{severity: level}] description
    3. [{severity: level}] [category] description  (new combined format)
    """
    issues: list[dict[str, str]] = []
    issues_section = _extract_section(block, "ISSUES")
    if not issues_section:
        return issues

    for match in re.finditer(
        r"^\d+\.\s*\[([^\]]*)\]\s*(.+?)(?=\n\d+\.|\Z)",
        issues_section,
        re.MULTILINE | re.DOTALL,
    ):
        tag = match.group(1).strip()
        rest = match.group(2).strip()

        # Check if tag is a severity marker like "severity: severe"
        severity_match = re.match(r"\{?severity:\s*(\w+)\}?", tag, re.IGNORECASE)
        if severity_match:
            severity = severity_match.group(1).lower()
            # Check if rest starts with [category]
            cat_match = re.match(r"\[([^\]]*)\]\s*(.*)", rest, re.DOTALL)
            if cat_match:
                issues.append({
                    "severity": severity,
                    "category": cat_match.group(1).strip(),
                    "description": cat_match.group(2).strip(),
                })
            else:
                issues.append({
                    "severity": severity,
                    "description": rest,
                })
        else:
            issues.append({
                "category": tag,
                "description": rest,
            })
    return issues


def extract_suggestions(block: str) -> list[str]:
    """Extract numbered SUGGESTIONS into a list."""
    suggestions: list[str] = []
    section = _extract_section(block, "SUGGESTIONS")
    if not section:
        return suggestions

    for match in re.finditer(
        r"^\d+\.\s*(.+?)(?=\n\d+\.|\Z)",
        section,
        re.MULTILINE | re.DOTALL,
    ):
        suggestions.append(match.group(1).strip())
    return suggestions


def extract_attack_vectors(block: str) -> list[dict[str, str]]:
    """Extract ATTACK_VECTORS section.

    Expects format:
    ATTACK_VECTORS:
    1. ATTACK: ...
       DEFENSE: ...
    """
    vectors: list[dict[str, str]] = []
    section = _extract_section(block, "ATTACK_VECTORS")
    if not section:
        return vectors

    # Split by numbered items
    items = re.split(r"\n(?=\d+\.)", section)
    for item in items:
        item = item.strip()
        if not item:
            continue
        attack_match = re.search(
            r"ATTACK:\s*(.+?)(?=\n\s*DEFENSE:|\Z)", item, re.DOTALL
        )
        defense_match = re.search(r"DEFENSE:\s*(.+?)(?=\Z)", item, re.DOTALL)
        if attack_match:
            vectors.append({
                "attack": attack_match.group(1).strip(),
                "defense": defense_match.group(1).strip()
                if defense_match
                else "",
            })
    return vectors


def extract_ranking(text: str) -> list[dict[str, str]]:
    """Extract RANKING section from the full review text."""
    ranking: list[dict[str, str]] = []
    section = _extract_section(text, "RANKING")
    if not section:
        return ranking

    for match in re.finditer(
        r"^\d+\.\s*(\S+)\s*[-:]\s*(.+?)(?=\n\d+\.|\Z)",
        section,
        re.MULTILINE | re.DOTALL,
    ):
        ranking.append({
            "slug": match.group(1).strip(),
            "justification": match.group(2).strip(),
        })
    return ranking


def _extract_section(text: str, header: str) -> str:
    """Extract content after a HEADER: line until the next known header or end."""
    known_headers = (
        "VERDICT",
        "SCORE_",
        "ISSUES",
        "SUGGESTIONS",
        "ATTACK_VECTORS",
        "RANKING",
        "RECENT_WORK_CHECK",
        "FATAL_FLAW",
        "GAP_ADDRESSED",
        "CLOSEST_PRIOR",
        "NOVELTY_CONFIDENCE",
        "FEASIBILITY",
        "TITLE",
        "DESCRIPTION",
        "VIABILITY_VERDICT",
        "REASSESSMENT_VERDICT",
        "DIMENSION_",
        "EVIDENCE_",
        "INFEASIBLE_SUMMARY",
        "CAVEATS",
        "ALTERNATIVE_DIRECTIONS",
        "WHAT_WOULD_MAKE_VIABLE",
        "FAILURE_PATTERN",
        "FAILURE_ANALYSIS",
        "GUIDANCE",
    )
    pattern = rf"^{re.escape(header)}:\s*\n?(.*?)(?=^(?:{'|'.join(re.escape(h) for h in known_headers)})[\s_\w]*:|\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: single-line extraction
    match = re.search(rf"^{re.escape(header)}:\s*(.+)$", text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return ""


def _extract_single_field(block: str, field_name: str) -> str:
    """Extract a single-line field value."""
    match = re.search(
        rf"^{re.escape(field_name)}:\s*(.+)$", block, re.MULTILINE
    )
    return match.group(1).strip() if match else ""


# --- Viability assessment parsing ---


@dataclass
class ViabilityAssessment:
    """Parsed result of a topic viability assessment."""

    verdict: str = ""
    dimensions: dict[str, dict[str, str]] = field(default_factory=dict)
    summary: str = ""
    caveats: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    what_would_make_viable: str = ""
    failure_pattern: str = ""
    reassessment_verdict: str = ""
    guidance: list[str] = field(default_factory=list)
    failure_analysis: str = ""
    raw_text: str = ""


_VIABILITY_DIMENSIONS = ["saturation", "foundation", "scope", "coherence", "timing"]


def parse_viability_assessment(text: str) -> ViabilityAssessment:
    """Parse an Advisor's viability assessment output.

    Handles both Checkpoint 1 (VIABILITY_VERDICT) and
    Checkpoint 2 (REASSESSMENT_VERDICT) formats.
    """
    result = ViabilityAssessment(raw_text=text)

    # Checkpoint 1 verdict
    result.verdict = _extract_single_field(text, "VIABILITY_VERDICT").lower()

    # Checkpoint 2 verdict
    result.reassessment_verdict = _extract_single_field(
        text, "REASSESSMENT_VERDICT"
    ).lower()

    # If checkpoint 2, may override verdict
    if result.reassessment_verdict == "infeasible" and not result.verdict:
        result.verdict = "infeasible"

    # Dimensions
    for dim in _VIABILITY_DIMENSIONS:
        dim_upper = dim.upper()
        rating = _extract_single_field(text, f"DIMENSION_{dim_upper}").upper()
        evidence = _extract_single_field(text, f"EVIDENCE_{dim_upper}")
        if rating or evidence:
            result.dimensions[dim] = {"rating": rating, "evidence": evidence}

    # Infeasible summary
    result.summary = _extract_single_field(text, "INFEASIBLE_SUMMARY")

    # Caveats (for viable_with_caveats)
    caveats_section = _extract_section(text, "CAVEATS")
    if caveats_section:
        result.caveats = _extract_numbered_items(caveats_section)

    # Alternative directions
    alt_section = _extract_section(text, "ALTERNATIVE_DIRECTIONS")
    if alt_section:
        result.alternatives = _extract_numbered_items(alt_section)

    # What would make viable
    result.what_would_make_viable = _extract_single_field(
        text, "WHAT_WOULD_MAKE_VIABLE"
    )

    # Checkpoint 2 specific fields
    result.failure_pattern = _extract_single_field(text, "FAILURE_PATTERN")
    result.failure_analysis = _extract_single_field(text, "FAILURE_ANALYSIS")

    guidance_section = _extract_section(text, "GUIDANCE")
    if guidance_section:
        result.guidance = _extract_numbered_items(guidance_section)

    return result


def _extract_numbered_items(section: str) -> list[str]:
    """Extract numbered items (1. xxx, 2. xxx) from a section."""
    items: list[str] = []
    for match in re.finditer(
        r"^\d+\.\s*(.+?)(?=\n\d+\.|\Z)",
        section,
        re.MULTILINE | re.DOTALL,
    ):
        items.append(match.group(1).strip())
    return items


# ---------------------------------------------------------------------------
# Student revision output validation
# ---------------------------------------------------------------------------

# Phrases that indicate the Student is trying to influence reviewers rather
# than improving the proposal content.  Each pattern is compiled as
# case-insensitive.  The list intentionally errs on the side of catching
# borderline cases — false positives are cheap (the orchestrator re-prompts),
# false negatives let manipulation through.
_MANIPULATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        # Direct appeals / persuasion aimed at reviewers
        r"(?:I|we)\s+(?:hope|ask|request|urge|beg|plead|implore)\b.*\breview",
        r"(?:please|kindly)\s+(?:reconsider|approve|accept|pass)\b",
        r"(?:should|must)\s+be\s+(?:sufficient|enough)\s+for\s+approval",
        r"\breviewers?\s+(?:should|will|must|may)\s+(?:reconsider|agree|approve|accept)\b",
        r"\bwe\s+respectfully\s+disagree\b",
        r"\bthe\s+reviewer\s+(?:may\s+have\s+)?(?:overlooked|missed|misunderstood|misread)\b",
        r"\bnote\s+to\s+(?:the\s+)?reviewers?\b",
        # Arguing about the review process
        r"\b(?:unfair|harsh|unjust|biased|too strict)\s+(?:review|assessment|evaluation|criticism)\b",
        r"\bask\s+for\s+(?:leniency|reconsideration|another\s+chance)\b",
        r"\bdowngrade\s+(?:the\s+)?(?:severity|issue)\b",
        r"\bthis\s+(?:issue|concern)\s+(?:should|could)\s+be\s+(?:minor|slight)\b",
        # Self-declared approval worthiness
        r"\b(?:this|our)\s+(?:proposal|work|method)\s+(?:deserves?|merits?|warrants?)\s+approval\b",
        r"\bready\s+for\s+(?:final\s+)?approval\b",
        r"\bshould\s+(?:now\s+)?(?:be\s+)?approv(?:ed|able)\b",
    ]
]


@dataclass
class RevisionViolation:
    """A detected manipulation attempt in Student revision output."""

    pattern_description: str
    matched_text: str
    line_number: int


def validate_student_revision(text: str) -> list[RevisionViolation]:
    """Check Student revision output for attempts to influence reviewers.

    Returns a list of violations. Empty list means the output is clean.
    The orchestrator should reject the revision and re-prompt the Student
    if any violations are found.
    """
    violations: list[RevisionViolation] = []
    lines = text.split("\n")

    for line_idx, line in enumerate(lines, start=1):
        for pattern in _MANIPULATION_PATTERNS:
            match = pattern.search(line)
            if match:
                violations.append(
                    RevisionViolation(
                        pattern_description=pattern.pattern,
                        matched_text=match.group(0),
                        line_number=line_idx,
                    )
                )
    return violations
