"""Interaction logging for complete audit trail."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def log_interaction(
    workspace: Path,
    stage: str,
    round_num: int,
    role: str,
    input_summary: str,
    full_output: str,
    decision: str | None = None,
    idea_slug: str | None = None,
) -> Path:
    """Write an interaction record to the log directory.

    Returns the path to the written log file.
    """
    log_dir = workspace / "proposal_space" / "interaction_log"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Build filename
    parts = [stage, role.lower().replace(" ", "_")]
    if idea_slug:
        parts.append(idea_slug)
    parts.append(f"round{round_num}")
    filename = "_".join(parts) + ".md"
    filepath = log_dir / filename

    # If file already exists, append a counter
    if filepath.exists():
        counter = 2
        while True:
            alt = log_dir / f"{'_'.join(parts)}_v{counter}.md"
            if not alt.exists():
                filepath = alt
                break
            counter += 1

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    decision_text = decision if decision else "N/A"

    content = f"""# {stage} -- {role} (Round {round_num})

**Timestamp**: {timestamp}
**Role**: {role}
**Round**: {round_num}
{f'**Idea**: {idea_slug}' if idea_slug else ''}
**Input Context**: {input_summary}

---

## Full Output

{full_output}

---

## Decision

{decision_text}
"""
    filepath.write_text(content, encoding="utf-8")
    return filepath


REQUIRED_REVIEW_SECTIONS = [
    "## Overall Assessment",
    "## Issues Raised",
    "## Verdict",
]


def save_review(
    workspace: Path,
    reviewer: str,
    slug: str,
    round_num: int,
    content: str,
) -> Path:
    """Save a complete review to the reviews directory and validate it.

    This is the ONLY correct way to persist a review. The orchestrator
    must call this immediately after a reviewer agent returns, BEFORE
    parsing issues or updating the tracker.

    Args:
        workspace: Workspace root path.
        reviewer: "advisor" or "vp".
        slug: Idea slug.
        round_num: Review round number.
        content: The COMPLETE, unabridged reviewer agent output.

    Returns:
        Path to the saved review file.

    Raises:
        ValueError: If the review content fails validation.
    """
    reviews_dir = workspace / "proposal_space" / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{reviewer}_{slug}_round{round_num}.md"
    filepath = reviews_dir / filename
    filepath.write_text(content, encoding="utf-8")

    # Validate
    errors = validate_review_file(filepath)
    if errors:
        raise ValueError(
            f"Review file {filename} failed validation:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
    return filepath


def validate_review_file(filepath: Path) -> list[str]:
    """Validate that a review file meets minimum quality requirements.

    Returns a list of error messages. Empty list means the file is valid.
    """
    errors: list[str] = []

    if not filepath.exists():
        errors.append(f"File does not exist: {filepath}")
        return errors

    content = filepath.read_text(encoding="utf-8")
    size = len(content.encode("utf-8"))

    if size < 500:
        errors.append(
            f"File too short ({size} bytes). A substantive review should be "
            f"at least 500 bytes. This likely means the review was truncated "
            f"or summarized instead of saved in full."
        )

    for section in REQUIRED_REVIEW_SECTIONS:
        if section not in content:
            errors.append(f"Missing required section: '{section}'")

    return errors


def write_pipeline_summary(
    workspace: Path,
    topic: str,
    total_rounds: int,
    agent_calls: dict[str, int],
    idea_lifecycle: list[dict],
    key_decisions: list[str],
    review_highlights: str = "",
) -> Path:
    """Generate the pipeline_summary.md at end of run."""
    log_dir = workspace / "proposal_space" / "interaction_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    filepath = log_dir / "pipeline_summary.md"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total = sum(agent_calls.values())
    calls_breakdown = ", ".join(f"{k}: {v}" for k, v in agent_calls.items())

    # Build lifecycle table
    lifecycle_rows = []
    for idea in idea_lifecycle:
        row = f"| {idea.get('slug', '')} | {idea.get('created', '')} |"
        for r in idea.get("rounds", []):
            row += f" {r} |"
        row += f" {idea.get('final_status', '')} |"
        lifecycle_rows.append(row)

    # Build round headers
    round_headers = " | ".join(f"Round {i}" for i in range(1, total_rounds + 1))
    round_separators = " | ".join("---" for _ in range(total_rounds))

    decisions_md = "\n".join(f"{i+1}. {d}" for i, d in enumerate(key_decisions))

    content = f"""# Pipeline Summary

**Topic**: {topic}
**Run Date**: {timestamp}
**Total Rounds**: {total_rounds}
**Total Agent Calls**: {total} ({calls_breakdown})

## Idea Lifecycle

| Idea | Created | {round_headers} | Final Status |
|------|---------|{' ' + round_separators + ' ' if round_separators else ''}|-------------|
{chr(10).join(lifecycle_rows)}

## Key Decision Points

{decisions_md}

## Review Highlights

{review_highlights if review_highlights else "(none recorded)"}
"""
    filepath.write_text(content, encoding="utf-8")
    return filepath
