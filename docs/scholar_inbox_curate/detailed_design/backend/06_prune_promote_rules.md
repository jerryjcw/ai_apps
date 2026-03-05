# 06 — Prune & Promote Rules Engine

## Overview

The rules engine evaluates each active paper against configurable thresholds to automatically prune low-impact papers and promote high-impact ones. It runs after every citation polling cycle and can also be triggered manually.

---

## Module: `src/rules.py`

### Public Interface

```python
from dataclasses import dataclass

@dataclass
class RulesResult:
    """Summary of a rules evaluation run."""
    papers_evaluated: int
    papers_pruned: int
    papers_promoted: int
    pruned_ids: list[str]
    promoted_ids: list[str]


def run_prune_promote(conn, config: AppConfig, now: str) -> RulesResult:
    """Evaluate all eligible papers against prune/promote rules.

    Only evaluates papers where manual_status = 0 (not manually overridden).
    Returns a summary of actions taken.
    """
```

---

## Prune Rules

A paper is pruned when **ALL** conditions are met:

1. **Status is `active`** — promoted papers are never auto-pruned
2. **`manual_status = 0`** — not manually set by the user
3. **Age since publication > `min_age_months`** (default: 6 months)
4. **Total citations < `min_citations`** (default: 10)
5. **Citation velocity < `min_velocity`** (default: 1.0 citations/month)

```python
def _should_prune(paper: dict, config: AppConfig, now: str) -> bool:
    """Determine if a paper should be pruned."""
    if paper["status"] != "active":
        return False
    if paper["manual_status"]:
        return False

    published = paper.get("published_date") or paper["ingested_at"]
    age_months = months_between(published, now)

    return (
        age_months > config.pruning.min_age_months
        and paper["citation_count"] < config.pruning.min_citations
        and paper["citation_velocity"] < config.pruning.min_velocity
    )
```

### Rationale for AND Logic

All three conditions must hold because:
- A paper might have few total citations but high recent velocity (newly gaining traction) — don't prune
- A paper might have low velocity but high total citations (established work) — don't prune
- A paper might be young (< 6 months) — give it more time before judging

---

## Promote Rules

A paper is promoted when **ANY** condition is met:

1. **Total citations >= `citation_threshold`** (default: 50)
2. **Citation velocity >= `velocity_threshold`** (default: 10.0 citations/month) sustained over at least 2 consecutive snapshots

```python
def _should_promote(paper: dict, conn, config: AppConfig) -> bool:
    """Determine if a paper should be promoted."""
    if paper["status"] != "active":
        return False
    if paper["manual_status"]:
        return False

    # Condition 1: High total citations
    if paper["citation_count"] >= config.promotion.citation_threshold:
        return True

    # Condition 2: Sustained high velocity
    if paper["citation_velocity"] >= config.promotion.velocity_threshold:
        if _has_sustained_velocity(conn, paper["id"], config.promotion.velocity_threshold):
            return True

    return False
```

### Sustained Velocity Check

To avoid promoting papers based on a single anomalous spike, we verify that the velocity threshold was met in at least 2 recent polling cycles:

```python
def _has_sustained_velocity(conn, paper_id: str, threshold: float) -> bool:
    """Check if velocity has been above threshold for 2+ consecutive snapshots.

    Approach:
    1. Get the last 3 snapshots (ordered by date desc).
    2. Compute pair-wise velocity between consecutive snapshots.
    3. Return True if at least 2 of these pair-wise velocities exceed threshold.
    """
    snapshots = conn.execute(
        "SELECT total_citations, checked_at FROM citation_snapshots "
        "WHERE paper_id = ? ORDER BY checked_at DESC LIMIT 3",
        (paper_id,)
    ).fetchall()

    if len(snapshots) < 3:
        # Not enough history to confirm sustained velocity
        # Fall back to: if current velocity >= threshold, treat as sustained
        # (paper will be re-evaluated on next cycle)
        return len(snapshots) >= 2

    # Compute velocities between consecutive pairs
    velocities_above = 0
    for i in range(len(snapshots) - 1):
        newer = snapshots[i]
        older = snapshots[i + 1]
        days = (datetime.fromisoformat(newer["checked_at"]) -
                datetime.fromisoformat(older["checked_at"])).days
        if days < 1:
            continue
        velocity = (newer["total_citations"] - older["total_citations"]) / (days / 30.44)
        if velocity >= threshold:
            velocities_above += 1

    return velocities_above >= 2
```

---

## Execution Flow

```python
def run_prune_promote(conn, config: AppConfig, now: str) -> RulesResult:
    """Evaluate all eligible papers against prune/promote rules."""

    # Fetch all active, non-manual papers
    papers = conn.execute(
        "SELECT * FROM papers WHERE status = 'active' AND manual_status = 0"
    ).fetchall()

    pruned_ids = []
    promoted_ids = []

    for paper in papers:
        paper_dict = dict(paper)

        if _should_promote(paper_dict, conn, config):
            update_paper_status(conn, paper_dict["id"], "promoted", manual=False)
            promoted_ids.append(paper_dict["id"])
            logger.info(
                "Promoted: %s (citations=%d, velocity=%.1f)",
                paper_dict["title"][:60],
                paper_dict["citation_count"],
                paper_dict["citation_velocity"],
            )
        elif _should_prune(paper_dict, config, now):
            update_paper_status(conn, paper_dict["id"], "pruned", manual=False)
            pruned_ids.append(paper_dict["id"])
            logger.info(
                "Pruned: %s (citations=%d, velocity=%.1f, age=%.1f months)",
                paper_dict["title"][:60],
                paper_dict["citation_count"],
                paper_dict["citation_velocity"],
                months_between(
                    paper_dict.get("published_date") or paper_dict["ingested_at"], now
                ),
            )

    return RulesResult(
        papers_evaluated=len(papers),
        papers_pruned=len(pruned_ids),
        papers_promoted=len(promoted_ids),
        pruned_ids=pruned_ids,
        promoted_ids=promoted_ids,
    )
```

**Note:** Promote is evaluated before prune. This ensures that a paper meeting both conditions (unlikely but possible with edge-case thresholds) is promoted rather than pruned.

---

## Manual Status Override

### Setting Manual Status

When a user manually changes a paper's status via CLI or web UI:

```python
def update_paper_status(conn, paper_id: str, status: str, manual: bool = False):
    """Update paper status. If manual=True, sets manual_status=1."""
    conn.execute(
        "UPDATE papers SET status = ?, manual_status = ? WHERE id = ?",
        (status, 1 if manual else 0, paper_id)
    )
```

### Restoring to Auto-Rules

A user can "restore" a paper to auto-managed status:

```python
def restore_auto_status(conn, paper_id: str):
    """Remove manual override, setting status back to 'active' for re-evaluation."""
    conn.execute(
        "UPDATE papers SET status = 'active', manual_status = 0 WHERE id = ?",
        (paper_id,)
    )
```

The paper will then be re-evaluated on the next rules cycle.

---

## Configuration Tunability

All thresholds are loaded from `config.toml` via `AppConfig`:

```toml
[pruning]
min_age_months = 6    # Don't prune papers younger than this
min_citations = 10    # Papers with fewer citations after min_age are pruned
min_velocity = 1.0    # Papers with lower velocity are pruned

[promotion]
citation_threshold = 50    # Papers with this many citations are promoted
velocity_threshold = 10.0  # Papers with this velocity are promoted (if sustained)
```

These can be adjusted over time as the user develops intuition about what thresholds match their reading capacity and interests.

---

## Dry Run Mode

For the CLI, a dry-run mode shows what would happen without making changes:

```python
def dry_run_prune_promote(conn, config: AppConfig, now: str) -> RulesResult:
    """Evaluate rules without modifying the database.

    Returns the same RulesResult showing what would be pruned/promoted.
    Used by: scholar-curate prune --dry-run
    """
```

This is useful for tuning thresholds — see what papers would be affected before committing changes.
