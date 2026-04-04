"""Pipeline state management for the research-ideate system."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

QUALITY_STANDARDS: dict[int, str] = {1: "lenient", 2: "moderate", 3: "strict"}

STAGE_SEQUENCE = [
    "stage_1_literature",
    "stage_2_ideation",
    "stage_3_hypothesis",
    "stage_4_planning",
    "stage_5_submission",
    "stage_6_advisor_review",
    "stage_7_vp_review",
    "stage_8_decision",
    "stage_9_final_output",
]

IDEA_STATUSES = {
    "candidate",
    "planning",
    "in_review",
    "approved",
    "refine",
    "pivoted",
    "dropped",
}

MAX_REFINES_PER_IDEA = 3
MAX_PIVOTS = 3
MAX_ROUNDS = 3

PIPELINE_STATUSES = {"running", "completed", "infeasible"}

VIABILITY_VERDICTS = {"viable", "viable_with_caveats", "infeasible"}

ISSUE_SEVERITIES = {"severe", "major", "minor", "slight"}
ISSUE_STATUSES = {"open", "addressed", "wontfix"}

VIABILITY_DIMENSIONS = [
    "saturation",
    "foundation",
    "scope",
    "coherence",
    "timing",
]


def slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:80].strip("-")


def init_workspace(base_dir: Path) -> None:
    """Create the proposal_space directory tree."""
    dirs = [
        "state",
        "literature",
        "ideas",
        "hypotheses",
        "plans",
        "reviews",
        "interaction_log",
        "final",
    ]
    for d in dirs:
        (base_dir / "proposal_space" / d).mkdir(parents=True, exist_ok=True)


def init_state(
    workspace: Path,
    topic: str,
    paper_titles: list[str] | None = None,
    constraints: dict[str, Any] | None = None,
    intent_constraints: list[str] | None = None,
) -> dict[str, Any]:
    """Initialize a new pipeline state and write to disk.

    Args:
        intent_constraints: 1-3 hard requirements from the user about what
            kind of output they want (e.g., "Must produce a new optimization
            algorithm", "Must demonstrate faster convergence"). These are
            checked at idea generation and review time to prevent the
            pipeline from drifting away from the user's actual goal.
    """
    state: dict[str, Any] = {
        "topic": topic,
        "intent_constraints": intent_constraints or [],
        "paper_titles": paper_titles or [],
        "constraints": constraints or {
            "max_gpus": 8,
            "gpu_model": "H100",
            "focus_areas": [],
            "target_venues": ["ICML", "NeurIPS", "ICLR"],
        },
        "pipeline_status": "running",
        "current_round": 1,
        "current_stage": STAGE_SEQUENCE[0],
        "quality_standard": get_quality_standard(1),
        "ideas": {},
        "pivot_count": 0,
        "max_pivots": MAX_PIVOTS,
        "max_rounds": MAX_ROUNDS,
        "max_refines_per_idea": MAX_REFINES_PER_IDEA,
        "iteration_history": [],
        "viability": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    save_state(workspace, state)
    return state


def load_state(workspace: Path) -> dict[str, Any]:
    """Load state from state.json."""
    path = workspace / "proposal_space" / "state" / "state.json"
    with open(path) as f:
        return json.load(f)


def save_state(workspace: Path, state: dict[str, Any]) -> None:
    """Write state to state.json with updated timestamp."""
    state["updated_at"] = _now()
    path = workspace / "proposal_space" / "state" / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def advance_stage(workspace: Path, next_stage: str) -> dict[str, Any]:
    """Move pipeline to next stage. Returns updated state."""
    if next_stage not in STAGE_SEQUENCE:
        raise ValueError(f"Unknown stage: {next_stage}. Valid: {STAGE_SEQUENCE}")
    state = load_state(workspace)
    state["current_stage"] = next_stage
    save_state(workspace, state)
    return state


def get_next_stage(current_stage: str) -> str | None:
    """Return the stage after current_stage, or None if at end."""
    try:
        idx = STAGE_SEQUENCE.index(current_stage)
    except ValueError:
        return None
    if idx + 1 < len(STAGE_SEQUENCE):
        return STAGE_SEQUENCE[idx + 1]
    return None


def add_idea(
    workspace: Path,
    slug: str,
    title: str,
    round_created: int | None = None,
) -> dict[str, Any]:
    """Add a new idea to state."""
    state = load_state(workspace)
    if round_created is None:
        round_created = state["current_round"]
    state["ideas"][slug] = {
        "title": title,
        "status": "candidate",
        "round_created": round_created,
        "refine_count": 0,
        "advisor_verdicts": [],
        "vp_verdicts": [],
    }
    save_state(workspace, state)
    return state


def update_idea_status(
    workspace: Path,
    slug: str,
    status: str,
    reason: str = "",
) -> dict[str, Any]:
    """Update a single idea's status."""
    if status not in IDEA_STATUSES:
        raise ValueError(f"Unknown status: {status}. Valid: {IDEA_STATUSES}")
    state = load_state(workspace)
    if slug not in state["ideas"]:
        raise KeyError(f"Idea '{slug}' not found in state")
    idea = state["ideas"][slug]
    idea["status"] = status
    if reason:
        idea["last_reason"] = reason
    if status == "refine":
        idea["refine_count"] = idea.get("refine_count", 0) + 1
    if status == "approved":
        idea["round_approved"] = state["current_round"]
        idea["quality_approved"] = state.get("quality_standard", "lenient")
    if status == "pivoted":
        state["pivot_count"] = state.get("pivot_count", 0) + 1
    save_state(workspace, state)
    return state


def record_verdict(
    workspace: Path,
    slug: str,
    role: str,
    round_num: int,
    verdict: str,
    scores: dict[str, int] | None = None,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    """Record a reviewer verdict for an idea."""
    state = load_state(workspace)
    if slug not in state["ideas"]:
        raise KeyError(f"Idea '{slug}' not found in state")
    entry = {
        "round": round_num,
        "verdict": verdict,
        "scores": scores or {},
        "issues": issues or [],
        "timestamp": _now(),
    }
    key = "advisor_verdicts" if role == "advisor" else "vp_verdicts"
    state["ideas"][slug][key].append(entry)
    save_state(workspace, state)
    return state


def get_quality_standard(round_num: int) -> str:
    """Return quality standard name for given round number."""
    clamped = min(round_num, max(QUALITY_STANDARDS.keys()))
    return QUALITY_STANDARDS.get(clamped, "strict")


def get_ideas_by_status(state: dict[str, Any], status: str) -> list[str]:
    """Return idea slugs with the given status."""
    return [
        slug
        for slug, idea in state["ideas"].items()
        if idea.get("status") == status
    ]


def get_active_ideas(state: dict[str, Any]) -> list[str]:
    """Return slugs of ideas not dropped/pivoted."""
    terminal = {"dropped", "pivoted"}
    return [
        slug
        for slug, idea in state["ideas"].items()
        if idea.get("status") not in terminal
    ]


def can_refine(state: dict[str, Any], slug: str) -> bool:
    """Check if an idea can be refined again."""
    idea = state["ideas"].get(slug)
    if not idea:
        return False
    return idea.get("refine_count", 0) < state.get(
        "max_refines_per_idea", MAX_REFINES_PER_IDEA
    )


def can_pivot(state: dict[str, Any]) -> bool:
    """Check if the pipeline can still pivot."""
    return state.get("pivot_count", 0) < state.get("max_pivots", MAX_PIVOTS)


def check_convergence(state: dict[str, Any]) -> bool:
    """Check if pipeline should proceed to Stage 9.

    Converges when:
    - At least 3 ideas are approved at **strict** quality, OR
    - We've reached max rounds (strict is enforced at max round anyway)
    """
    strict_approved = [
        slug
        for slug, idea in state["ideas"].items()
        if idea.get("status") == "approved"
        and idea.get("quality_approved") == "strict"
    ]
    if len(strict_approved) >= 3:
        return True
    if state["current_round"] >= state.get("max_rounds", MAX_ROUNDS):
        return True
    return False


def get_ideas_needing_strict_rereview(state: dict[str, Any]) -> list[str]:
    """Return slugs of ideas approved below strict quality.

    These ideas passed review at lenient or moderate standards and need
    re-review at the strict level before they count toward convergence.
    """
    return [
        slug
        for slug, idea in state["ideas"].items()
        if idea.get("status") == "approved"
        and idea.get("quality_approved") != "strict"
    ]


def record_round_history(workspace: Path) -> dict[str, Any]:
    """Snapshot the current round's idea statuses into iteration_history."""
    state = load_state(workspace)
    summary = {
        "round": state["current_round"],
        "timestamp": _now(),
        "ideas_submitted": 0,
        "approved": 0,
        "refine": 0,
        "pivoted": 0,
        "dropped": 0,
    }
    for idea in state["ideas"].values():
        status = idea.get("status", "")
        if status in summary:
            summary[status] += 1
        summary["ideas_submitted"] += 1
    state["iteration_history"].append(summary)
    save_state(workspace, state)
    return state


def start_new_round(workspace: Path) -> dict[str, Any]:
    """Increment round counter and reset stage to appropriate start.

    Provisionally-approved ideas (approved below the new quality standard)
    are demoted to ``in_review`` so they go through re-review at the
    stricter level.  They skip student revision — only the reviewers
    re-evaluate them.
    """
    state = load_state(workspace)
    state["current_round"] += 1
    state["quality_standard"] = get_quality_standard(state["current_round"])

    # Demote ideas approved below the new quality standard
    provisional = get_ideas_needing_strict_rereview(state)
    for slug in provisional:
        state["ideas"][slug]["status"] = "in_review"

    # Determine the earliest stage we need to revisit
    refine_ideas = get_ideas_by_status(state, "refine")
    if refine_ideas:
        # Refine ideas need student revision → start at hypothesis stage
        state["current_stage"] = "stage_3_hypothesis"
    elif provisional:
        # Only provisional re-reviews needed → jump to advisor review
        state["current_stage"] = "stage_6_advisor_review"
    else:
        state["current_stage"] = "stage_9_final_output"

    save_state(workspace, state)
    return state


def record_viability_assessment(
    workspace: Path,
    checkpoint: int,
    verdict: str,
    dimensions: dict[str, dict[str, str]],
    summary: str = "",
    caveats: list[str] | None = None,
    alternatives: list[str] | None = None,
    what_would_make_viable: str = "",
) -> dict[str, Any]:
    """Record a topic viability assessment result.

    Args:
        workspace: Workspace root path.
        checkpoint: Which checkpoint triggered this (1 = post-literature, 2 = post-hypothesis).
        verdict: One of "viable", "viable_with_caveats", "infeasible".
        dimensions: Dict mapping dimension name to {"rating": "GREEN|YELLOW|RED", "evidence": "..."}.
        summary: Human-readable summary (required if infeasible).
        caveats: List of caveats (for viable_with_caveats).
        alternatives: Suggested alternative directions (for infeasible).
        what_would_make_viable: Conditions under which topic could work (for infeasible).

    Returns:
        Updated state dict.
    """
    if verdict not in VIABILITY_VERDICTS:
        raise ValueError(
            f"Unknown viability verdict: {verdict}. Valid: {VIABILITY_VERDICTS}"
        )
    if checkpoint not in (1, 2):
        raise ValueError(f"Checkpoint must be 1 or 2, got {checkpoint}")

    state = load_state(workspace)
    assessment: dict[str, Any] = {
        "checkpoint": checkpoint,
        "verdict": verdict,
        "dimensions": dimensions,
        "summary": summary,
        "timestamp": _now(),
    }
    if caveats:
        assessment["caveats"] = caveats
    if alternatives:
        assessment["alternatives"] = alternatives
    if what_would_make_viable:
        assessment["what_would_make_viable"] = what_would_make_viable

    state["viability"] = assessment

    if verdict == "infeasible":
        state["pipeline_status"] = "infeasible"

    save_state(workspace, state)
    return state


def is_infeasible(state: dict[str, Any]) -> bool:
    """Check if the pipeline has been terminated due to topic infeasibility."""
    return state.get("pipeline_status") == "infeasible"


def load_review_tracker(workspace: Path) -> dict[str, Any]:
    """Load the review tracker from disk, or return empty tracker."""
    path = workspace / "proposal_space" / "state" / "review_tracker.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_review_tracker(workspace: Path, tracker: dict[str, Any]) -> None:
    """Write review tracker to disk."""
    path = workspace / "proposal_space" / "state" / "review_tracker.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(tracker, f, indent=2, ensure_ascii=False)


def add_review_issue(
    workspace: Path,
    slug: str,
    issue_id: str,
    source: str,
    round_num: int,
    severity: str,
    category: str,
    description: str,
    suggestion: str = "",
) -> dict[str, Any]:
    """Add a review issue to the tracker for a given idea.

    Args:
        workspace: Workspace root path.
        slug: Idea slug.
        issue_id: Unique issue ID, e.g. "R1-ADV-1".
        source: "advisor" or "vp".
        round_num: Review round number.
        severity: One of "severe", "major", "minor", "slight".
        category: Issue category, e.g. "theory", "experiment", "novelty".
        description: Specific issue description.
        suggestion: Suggested fix.

    Returns:
        Updated tracker dict.
    """
    if severity not in ISSUE_SEVERITIES:
        raise ValueError(
            f"Unknown severity: {severity}. Valid: {ISSUE_SEVERITIES}"
        )
    tracker = load_review_tracker(workspace)
    if slug not in tracker:
        tracker[slug] = {"issues": []}

    now = datetime.now(timezone.utc).isoformat()
    issue = {
        "id": issue_id,
        "source": source,
        "round": round_num,
        "severity": severity,
        "category": category,
        "description": description,
        "suggestion": suggestion,
        "status": "open",
        "resolved_by": None,
        "addressed_in": None,
        "resolution_note": None,
        "history": [
            {
                "event": "opened",
                "timestamp": now,
                "by": source,
                "detail": description,
            }
        ],
    }
    tracker[slug]["issues"].append(issue)
    save_review_tracker(workspace, tracker)
    return tracker


VALID_RESOLVERS = ("advisor", "vp")


def resolve_review_issue(
    workspace: Path,
    slug: str,
    issue_id: str,
    status: str,
    resolved_by: str,
    addressed_in: str = "",
    resolution_note: str = "",
) -> dict[str, Any]:
    """Mark a review issue as addressed or wontfix.

    Only a reviewer (advisor or vp) may resolve an issue. The orchestrator
    and the student have no authority to change issue status — they can only
    relay the reviewer's verdict.

    Args:
        workspace: Workspace root path.
        slug: Idea slug.
        issue_id: The issue ID to resolve.
        status: "addressed" or "wontfix".
        resolved_by: Who confirmed the resolution — must be "advisor" or "vp".
        addressed_in: Where/when it was addressed, e.g. "R2_revision".
        resolution_note: How it was resolved (from the reviewer's text).

    Returns:
        Updated tracker dict.

    Raises:
        ValueError: If status is invalid, resolved_by is not a reviewer,
            or a severe/major issue is marked wontfix.
        KeyError: If slug or issue_id not found.
    """
    if status not in ("addressed", "wontfix"):
        raise ValueError(f"Resolution status must be 'addressed' or 'wontfix', got '{status}'")
    if resolved_by not in VALID_RESOLVERS:
        raise ValueError(
            f"Only a reviewer can resolve issues. "
            f"resolved_by must be one of {VALID_RESOLVERS}, got '{resolved_by}'"
        )
    tracker = load_review_tracker(workspace)
    if slug not in tracker:
        raise KeyError(f"Idea '{slug}' not found in review tracker")
    now = datetime.now(timezone.utc).isoformat()
    found = False
    for issue in tracker[slug]["issues"]:
        if issue["id"] == issue_id:
            if status == "wontfix" and issue["severity"] in ("severe", "major"):
                raise ValueError(
                    f"Cannot mark {issue['severity']} issue '{issue_id}' as wontfix. "
                    f"Severe and major issues must be addressed."
                )
            issue["status"] = status
            issue["resolved_by"] = resolved_by
            issue["addressed_in"] = addressed_in
            issue["resolution_note"] = resolution_note
            if "history" not in issue:
                issue["history"] = []
            issue["history"].append({
                "event": status,  # "addressed" or "wontfix"
                "timestamp": now,
                "by": resolved_by,
                "detail": resolution_note,
            })
            found = True
            break
    if not found:
        raise KeyError(f"Issue '{issue_id}' not found for idea '{slug}'")
    save_review_tracker(workspace, tracker)
    return tracker


def log_review_event(
    workspace: Path,
    slug: str,
    issue_id: str,
    event: str,
    by: str,
    detail: str = "",
) -> dict[str, Any]:
    """Append an event to an issue's history without changing its status.

    Use this to record reviewer re-review outcomes like "still_open" or
    "student_revision_submitted" without altering the issue's resolution state.

    Args:
        workspace: Workspace root path.
        slug: Idea slug.
        issue_id: The issue ID.
        event: Event name, e.g. "still_open", "student_revision_submitted".
        by: Who triggered the event ("advisor", "vp", "student", "orchestrator").
        detail: Free-text explanation.

    Returns:
        Updated tracker dict.
    """
    tracker = load_review_tracker(workspace)
    if slug not in tracker:
        raise KeyError(f"Idea '{slug}' not found in review tracker")
    now = datetime.now(timezone.utc).isoformat()
    found = False
    for issue in tracker[slug]["issues"]:
        if issue["id"] == issue_id:
            if "history" not in issue:
                issue["history"] = []
            issue["history"].append({
                "event": event,
                "timestamp": now,
                "by": by,
                "detail": detail,
            })
            found = True
            break
    if not found:
        raise KeyError(f"Issue '{issue_id}' not found for idea '{slug}'")
    save_review_tracker(workspace, tracker)
    return tracker


def get_open_issues(
    workspace: Path,
    slug: str,
    severity_filter: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return open issues for an idea, optionally filtered by severity.

    Args:
        workspace: Workspace root path.
        slug: Idea slug.
        severity_filter: If provided, only return issues with these severities.

    Returns:
        List of open issue dicts.
    """
    tracker = load_review_tracker(workspace)
    if slug not in tracker:
        return []
    issues = tracker[slug]["issues"]
    result = [i for i in issues if i["status"] == "open"]
    if severity_filter:
        result = [i for i in result if i["severity"] in severity_filter]
    return result


def has_blocking_issues(workspace: Path, slug: str) -> bool:
    """Check if an idea has any open severe or major issues."""
    return len(get_open_issues(workspace, slug, {"severe", "major"})) > 0


def can_approve(workspace: Path, slug: str) -> bool:
    """Check if an idea can be approved (no open severe/major issues)."""
    return not has_blocking_issues(workspace, slug)


def all_ideas_dead(state: dict[str, Any]) -> bool:
    """Check if all ideas are in terminal states (dropped or pivoted).

    Returns True if no active ideas remain, meaning the pipeline has
    exhausted all its current ideas.
    """
    return len(get_active_ideas(state)) == 0


def get_viability_caveats(state: dict[str, Any]) -> list[str]:
    """Return caveats from a VIABLE_WITH_CAVEATS assessment, or empty list."""
    viability = state.get("viability")
    if not viability:
        return []
    if viability.get("verdict") != "viable_with_caveats":
        return []
    return viability.get("caveats", [])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
