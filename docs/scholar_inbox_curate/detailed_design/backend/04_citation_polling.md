# 04 — Citation Polling

## Overview

Citation polling is the periodic process of fetching updated citation counts for tracked papers from external APIs. This document covers the two data sources (Semantic Scholar and OpenAlex), the age-based polling schedule, batch fetching, and snapshot recording.

---

## Module Structure

```
src/citations/
├── __init__.py
├── semantic_scholar.py   # Semantic Scholar API client
├── openalex.py           # OpenAlex API client
├── velocity.py           # Velocity computation (see doc 05)
└── poller.py             # Orchestration: which papers to poll, when
```

---

## Module: `src/citations/poller.py`

### Public Interface

```python
async def run_citation_poll(config: AppConfig, db_path: str) -> int:
    """Execute a full citation polling cycle.

    Steps:
    1. Query DB for papers due for polling (age-based schedule).
    2. Batch-fetch citation counts from Semantic Scholar.
    3. For papers due for monthly OpenAlex check, fetch yearly breakdowns.
    4. Insert new citation_snapshots rows.
    5. Recompute citation velocity for each polled paper.
    6. Update papers.citation_count and papers.citation_velocity.
    7. Update papers.last_cited_check timestamps.
    8. Run prune/promote rules on updated papers.

    Returns:
        Number of papers whose citations were updated.
    """
```

---

## Age-Based Polling Schedule

The `get_papers_due_for_poll()` database function (defined in doc 01) determines which papers need polling. The logic:

```python
from datetime import datetime, timezone, timedelta

def _is_paper_due_for_poll(paper: dict, now: datetime) -> bool:
    """Determine if a paper needs citation polling based on its age and last check."""

    if paper["status"] == "pruned":
        return False

    last_check = paper.get("last_cited_check")
    if last_check is None:
        return True  # Never polled

    last_check_dt = datetime.fromisoformat(last_check)
    days_since_check = (now - last_check_dt).days

    # Paper age = time since it was published (or ingested if unknown)
    published = paper.get("published_date") or paper["ingested_at"]
    published_dt = datetime.fromisoformat(published)
    age_months = (now - published_dt).days / 30.44

    if paper["status"] == "promoted":
        return days_since_check >= 30

    if age_months < 3:
        return days_since_check >= 7   # Weekly
    elif age_months < 12:
        return days_since_check >= 14  # Biweekly
    else:
        return days_since_check >= 30  # Monthly
```

This logic is implemented as a SQL query for efficiency, not Python-side filtering. The SQL version:

```sql
SELECT *,
    CASE
        WHEN last_cited_check IS NULL THEN 1e9
        ELSE (julianday(:now) - julianday(last_cited_check))
             / CASE
                 WHEN status = 'promoted' THEN 30.0
                 WHEN julianday(:now) - julianday(ingested_at) < 91 THEN 7.0
                 WHEN julianday(:now) - julianday(ingested_at) < 365 THEN 14.0
                 ELSE 30.0
               END
    END AS overdue_ratio
FROM papers
WHERE status != 'pruned'
AND (
    last_cited_check IS NULL
    OR (
        status = 'promoted'
        AND last_cited_check <= datetime(:now, '-30 days')
    )
    OR (
        julianday(:now) - julianday(ingested_at) < 91
        AND last_cited_check <= datetime(:now, '-7 days')
    )
    OR (
        julianday(:now) - julianday(ingested_at) >= 91
        AND julianday(:now) - julianday(ingested_at) < 365
        AND last_cited_check <= datetime(:now, '-14 days')
    )
    OR (
        julianday(:now) - julianday(ingested_at) >= 365
        AND last_cited_check <= datetime(:now, '-30 days')
    )
)
ORDER BY overdue_ratio DESC
LIMIT :limit;  -- NULL means no limit
```

> **Note:** The query uses `ingested_at` (not `published_date`) for age determination, and accepts `:now` as a parameter for deterministic testing rather than using `'now'`. The `overdue_ratio` column orders papers so the most overdue are polled first, and the optional `LIMIT` enables budget-based polling.

---

## Module: `src/citations/semantic_scholar.py`

### Semantic Scholar Batch API

The primary source for citation counts. Uses the batch endpoint for efficiency.

```python
BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
FIELDS = "citationCount,externalIds"

async def fetch_citations_batch(
    client: httpx.AsyncClient,
    paper_ids: list[str],
    api_key: str | None = None,
    batch_size: int = 100,
) -> dict[str, int]:
    """Fetch citation counts for multiple papers in batches.

    Args:
        paper_ids: List of Semantic Scholar paper IDs.
        batch_size: Papers per API request (max 500, default 100).

    Returns:
        Dict mapping paper_id -> citation_count.
        Papers not found are excluded from the result.
    """
```

### Batch Request Format

```python
async def _fetch_batch(
    client: httpx.AsyncClient,
    ids: list[str],
    headers: dict,
) -> list[dict]:
    """Execute a single batch request."""
    response = await client.post(
        BATCH_URL,
        params={"fields": FIELDS},
        json={"ids": ids},
        headers=headers,
        timeout=60.0,
    )
    response.raise_for_status()

    results = response.json()
    # Results are in the same order as input IDs.
    # Missing papers return null entries.
    return results
```

### Handling Paper IDs with Different Prefixes

Papers in our database may have different ID formats:
- Semantic Scholar paperId (40-char hex) — use directly
- `arxiv:{id}` — prefix with `ARXIV:` for the API
- `doi:{doi}` — prefix with `DOI:` for the API
- `title:{hash}` — cannot be used with batch API; skip or use search endpoint

```python
def _to_s2_id(paper_id: str) -> str | None:
    """Convert our internal paper ID to a Semantic Scholar API-compatible ID."""
    if paper_id.startswith("arxiv:"):
        return f"ARXIV:{paper_id[6:]}"
    elif paper_id.startswith("doi:"):
        return f"DOI:{paper_id[4:]}"
    elif paper_id.startswith("title:") or paper_id.startswith("si-"):
        return None  # Cannot batch-lookup by title hash or Scholar Inbox internal ID
    else:
        return paper_id  # Assume it's a native S2 paperId
```

> **Note:** Papers with `title:` or `si-` prefix IDs are skipped during citation polling. These "dangling" papers are automatically re-resolved to proper S2 IDs by the backfill process (see doc 03 — Re-Resolution of Dangling Papers).

### Rate Limiting

```python
# With API key: up to 1 request per second for batch endpoint
# Without key: 1 request per 10 seconds for batch
BATCH_DELAY_WITH_KEY = 1.0
BATCH_DELAY_NO_KEY = 10.0
```

Between each batch request, wait the appropriate delay.

### Error Recovery

Error recovery uses the configurable `RetryConfig` from `src/retry.py` (see doc 08). The default `DEFAULT_RETRY` configuration provides exponential backoff with jitter, 5 attempts, 2s base delay capped at 60s. A fixed-delay strategy is also available.

- **429 Rate Limit:** Retry using the configured strategy. The `Retry-After` header is used as a minimum wait time.
- **5xx Server Error:** Retry using the configured strategy. Skip the batch if all attempts are exhausted.
- **Partial results:** If some IDs in a batch return null, those papers are skipped for this cycle. They'll be retried on the next poll.

---

## Module: `src/citations/openalex.py`

### OpenAlex API

Secondary source used for yearly citation breakdowns. OpenAlex provides `counts_by_year` which shows how many citations a paper received in each calendar year.

```python
OPENALEX_BASE = "https://api.openalex.org"

async def fetch_yearly_citations(
    client: httpx.AsyncClient,
    doi: str | None = None,
    title: str | None = None,
) -> dict | None:
    """Fetch yearly citation breakdown from OpenAlex.

    Args:
        doi: Paper DOI (preferred lookup method).
        title: Paper title (fallback search).

    Returns:
        Dict with keys:
        - "total": int (total citation count)
        - "by_year": dict[str, int] (e.g., {"2024": 12, "2025": 34})

        Returns None if the paper is not found.
    """
```

### Lookup by DOI

```
GET https://api.openalex.org/works/doi:{doi}
```

### Lookup by Title (Fallback)

```
GET https://api.openalex.org/works?search={title}&per_page=5
```

Select the best title match using the same fuzzy matching logic from doc 03.

### Response Parsing

```python
def _parse_openalex_work(work: dict) -> dict:
    """Parse an OpenAlex work object into our format."""
    counts_by_year = work.get("counts_by_year", [])
    by_year = {}
    for entry in counts_by_year:
        year = str(entry["year"])
        by_year[year] = entry["cited_by_count"]

    return {
        "total": work.get("cited_by_count", 0),
        "by_year": by_year,
    }
```

### Rate Limiting

OpenAlex is free and generous, but requests should include a polite `mailto` parameter:

```python
def _openalex_params(config: AppConfig) -> dict:
    """Build OpenAlex query params with polite mailto from config."""
    return {"mailto": config.secrets.scholar_inbox_email}
```

Rate: max 10 requests per second (polite pool). We'll limit to 2 req/sec to be safe.

### When to Use OpenAlex

OpenAlex is only queried:
- During the **monthly** poll cycle (not weekly/biweekly)
- For papers that have a DOI (most reliable lookup)
- The yearly breakdown data is stored in `citation_snapshots.yearly_breakdown`

This reduces API calls while still providing trend data for the detail view charts.

---

## Polling Orchestration Flow

```python
async def run_citation_poll(config: AppConfig, db_path: str) -> int:
    now = now_utc()

    with get_connection(db_path) as conn:
        # Budget-based polling: cap each cycle to a fraction of non-pruned papers
        total = count_non_pruned_papers(conn)
        budget = max(1, int(total * config.citations.poll_budget_fraction))
        papers = get_papers_due_for_poll(conn, now, limit=budget)

    if not papers:
        logger.info("No papers due for citation polling")
        return 0

    logger.info("Polling citations for %d papers (budget %d of %d)", len(papers), budget, total)

    async with httpx.AsyncClient() as client:
        # 1. Batch fetch from Semantic Scholar
        s2_ids = []
        s2_id_map = {}  # s2_api_id -> our_paper_id
        fallback_papers = []

        for paper in papers:
            s2_id = _to_s2_id(paper["id"])
            if s2_id:
                s2_ids.append(s2_id)
                s2_id_map[s2_id] = paper["id"]
            else:
                fallback_papers.append(paper)

        citation_results = await fetch_citations_batch(
            client, s2_ids,
            api_key=config.secrets.semantic_scholar_api_key,
            batch_size=config.citations.semantic_scholar_batch_size,
        )

        # 2. Record snapshots and update papers
        with get_connection(db_path) as conn:
            for s2_id, count in citation_results.items():
                paper_id = s2_id_map.get(s2_id)
                if paper_id is None:
                    continue

                insert_snapshot(conn, paper_id, count, "semantic_scholar")

                # Compute velocity
                velocity = compute_velocity(conn, paper_id, now)

                update_paper_citations(conn, paper_id, count, velocity)

            # 3. Monthly: fetch OpenAlex for yearly breakdowns
            for paper in papers:
                if _should_fetch_openalex(paper, now):
                    result = await fetch_yearly_citations(
                        client, doi=paper.get("doi"), title=paper["title"]
                    )
                    if result:
                        insert_snapshot(
                            conn, paper["id"], result["total"],
                            "openalex", result["by_year"]
                        )

            # 4. Update last_cited_check for all polled papers
            for paper in papers:
                conn.execute(
                    "UPDATE papers SET last_cited_check = ? WHERE id = ?",
                    (now, paper["id"])
                )

    updated_count = len(citation_results)
    logger.info("Citation poll complete: %d papers updated", updated_count)
    return updated_count
```

---

## Budget-Based Polling

With a growing database, polling all eligible papers in every cycle can cause excessive Semantic Scholar API usage. Budget-based polling caps each cycle to a configurable fraction of the total non-pruned papers.

### Configuration

```toml
[citations]
poll_budget_fraction = 0.10  # Poll at most 10% of non-pruned papers per cycle
```

### Budget Computation

```python
total = count_non_pruned_papers(conn)
budget = max(1, int(total * config.citations.poll_budget_fraction))
papers = get_papers_due_for_poll(conn, now, limit=budget)
```

The minimum budget is 1 (even with very few papers).

### Overdue Ratio Prioritization

Papers are ordered by their *overdue ratio* = `days_since_last_check / scheduled_interval`:

- **Never-polled papers** sort first (assigned ratio `1e9`)
- Among polled papers, **higher ratio = more overdue** relative to schedule
- **Starvation prevention**: a monthly paper 60 days overdue (ratio 2.0) outranks a weekly paper 8 days overdue (ratio 1.14). Every paper's ratio climbs over time, guaranteeing eventual selection.

### Scope

- `run_citation_poll()` is budget-limited (periodic polling)
- `collect_citations_for_unpolled()` is **not** budget-limited (initial one-time collection for backfilled papers)

---

## Handling Papers with Fallback IDs

Papers with `title:{hash}` or `si-{paper_id}` IDs cannot use the Semantic Scholar batch API and are skipped during citation polling.

These "dangling" papers are handled by the **re-resolution mechanism** (see doc 03), which runs automatically at the end of each backfill execution:

1. Query the DB for papers with `title:` or `si-` prefix IDs
2. Re-attempt Semantic Scholar resolution (arXiv ID, DOI, or title search)
3. If resolved, replace the synthetic ID with the real S2 `paperId` in the database
4. If the resolved ID already exists, delete the dangling duplicate
5. If still unresolved, the paper remains and will be retried on the next backfill

This self-healing mechanism means that papers initially missed by S2 (due to temporary API outages or indexing delays) get resolved automatically once they appear in the S2 index.
