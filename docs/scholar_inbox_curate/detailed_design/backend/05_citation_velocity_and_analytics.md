# 05 — Citation Velocity & Analytics

## Overview

Citation velocity is the core metric for identifying papers gaining traction. This document details the velocity computation algorithm, edge cases, and the analytics queries that power the dashboard.

---

## Module: `src/citations/velocity.py`

### Public Interface

```python
def compute_velocity(conn, paper_id: str, now: str) -> float:
    """Compute citation velocity for a paper (citations per month).

    Uses the rolling 3-month window by default. Falls back to
    available data if less than 3 months of snapshots exist.

    Returns 0.0 if insufficient data (only one snapshot or less).
    """
```

---

## Velocity Computation Algorithm

### Standard Case (>= 3 Months of Data)

```
velocity = (current_citations - citations_3_months_ago) / 3.0
```

Where:
- `current_citations` = the latest `citation_snapshots.total_citations` for this paper
- `citations_3_months_ago` = the `total_citations` from the snapshot closest to (but not after) the date 3 months ago

### Short History Case (< 3 Months but >= 2 Snapshots)

```
velocity = (current_citations - earliest_citations) / months_elapsed
```

Where `months_elapsed` = days between earliest and latest snapshot / 30.44.

**Minimum elapsed time:** If the earliest and latest snapshots are less than 7 days apart, return 0.0 — too little data for a meaningful rate.

### Insufficient Data (0 or 1 Snapshots)

Return 0.0. The paper hasn't been tracked long enough.

---

## Implementation

```python
from datetime import datetime, timezone, timedelta

def compute_velocity(conn, paper_id: str, now: str) -> float:
    """Compute citation velocity in citations per month."""

    # Get latest snapshot
    latest = conn.execute(
        "SELECT total_citations, checked_at FROM citation_snapshots "
        "WHERE paper_id = ? ORDER BY checked_at DESC LIMIT 1",
        (paper_id,)
    ).fetchone()

    if latest is None:
        return 0.0

    current_citations = latest["total_citations"]
    current_date = datetime.fromisoformat(latest["checked_at"])

    # Try to find snapshot from ~3 months ago
    three_months_ago = current_date - timedelta(days=91)

    reference = conn.execute(
        "SELECT total_citations, checked_at FROM citation_snapshots "
        "WHERE paper_id = ? AND checked_at <= ? "
        "ORDER BY checked_at DESC LIMIT 1",
        (paper_id, three_months_ago.isoformat())
    ).fetchone()

    if reference is None:
        # Fall back to earliest available snapshot
        reference = conn.execute(
            "SELECT total_citations, checked_at FROM citation_snapshots "
            "WHERE paper_id = ? ORDER BY checked_at ASC LIMIT 1",
            (paper_id,)
        ).fetchone()

    if reference is None or reference["checked_at"] == latest["checked_at"]:
        return 0.0

    ref_date = datetime.fromisoformat(reference["checked_at"])
    ref_citations = reference["total_citations"]

    days_elapsed = (current_date - ref_date).days
    if days_elapsed < 7:
        return 0.0

    months_elapsed = days_elapsed / 30.44
    citation_diff = current_citations - ref_citations

    # Velocity cannot be negative (citation counts shouldn't decrease,
    # but API data corrections can cause this)
    if citation_diff <= 0:
        return 0.0

    return citation_diff / months_elapsed
```

---

## Edge Cases

### Citation Count Decreasing

Semantic Scholar occasionally corrects citation data, which can cause counts to drop between snapshots. When `citation_diff < 0`:
- Return velocity as 0.0 (not negative)
- Log a warning: "Citation count decreased for paper {id}: {old} -> {new}"
- Do **not** delete or modify previous snapshots — they represent what the API reported at that time

### Paper With No Semantic Scholar Data

Papers with `title:{hash}` IDs may have no snapshots at all or only OpenAlex snapshots. The velocity computation works the same regardless of source — it uses `total_citations` from whatever snapshot is available.

### Very New Papers (< 1 Week Tracked)

Return 0.0. This prevents misleading spikes like "5 citations in 2 days = 75/month velocity" from a single early snapshot.

### Very Old Papers With Stable Counts

Papers with high total citations but near-zero velocity (e.g., 500 citations total, 0.5/month) are expected. The velocity metric specifically captures **recent momentum**, not historical impact.

---

## Bulk Velocity Update

After a citation poll cycle, velocities need recomputation for all polled papers:

```python
def update_velocities_bulk(conn, paper_ids: list[str], now: str):
    """Recompute and update velocity for a list of papers."""
    for paper_id in paper_ids:
        velocity = compute_velocity(conn, paper_id, now)
        conn.execute(
            "UPDATE papers SET citation_velocity = ? WHERE id = ?",
            (velocity, paper_id)
        )
```

---

## Analytics Queries

These queries power the dashboard and paper list views. They are implemented as functions in `src/db.py`.

### Trending Papers

Papers with the highest velocity, used for the dashboard "Top Papers by Velocity" section:

```sql
SELECT id, title, authors, citation_count, citation_velocity, status
FROM papers
WHERE status IN ('active', 'promoted')
AND citation_velocity > 0
ORDER BY citation_velocity DESC
LIMIT 10;
```

### Summary Statistics

```sql
-- Paper counts by status
SELECT status, COUNT(*) as count FROM papers GROUP BY status;

-- Trending count (velocity > 5/month)
SELECT COUNT(*) FROM papers
WHERE status IN ('active', 'promoted')
AND citation_velocity > 5.0;

-- Recently ingested (last 7 days)
SELECT COUNT(*) FROM papers
WHERE julianday('now') - julianday(ingested_at) <= 7;
```

### Citation History for a Paper

Used by the detail view Chart.js visualization:

```sql
SELECT checked_at, total_citations, source, yearly_breakdown
FROM citation_snapshots
WHERE paper_id = ?
ORDER BY checked_at ASC;
```

### Papers Due for Polling

Count of papers that need polling (for the dashboard "Next Poll" card):

```sql
SELECT COUNT(*) FROM papers
WHERE status != 'pruned'
AND (
    last_cited_check IS NULL
    OR julianday('now') - julianday(last_cited_check) >= 7
);
```

---

## Velocity Trend Indicator

For the paper list UI, a simple trend indicator shows whether velocity is increasing or decreasing compared to the previous computation:

This requires comparing the current velocity with the velocity that would have been computed at the previous snapshot. Rather than storing historical velocity values, we compute it on-the-fly for the papers being displayed:

```python
def get_velocity_trend(conn, paper_id: str) -> str:
    """Return 'up', 'down', or 'stable' based on recent velocity change.

    Compares velocity computed from the last 2 snapshots vs
    the 2 snapshots before that. If the delta is < 0.5/month,
    consider it 'stable'.
    """
```

This is a nice-to-have for the UI — not critical for MVP.
