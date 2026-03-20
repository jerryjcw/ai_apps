# 08 — Error Handling & Resilience

## Overview

This document defines the error handling strategy across all components. The system should be resilient to transient failures (network issues, API downtime, Cloudflare challenges) and degrade gracefully — a failure in one subsystem should not prevent others from functioning.

---

## Error Hierarchy

All exceptions are defined in `src/errors.py`:

```
ScholarCurateError (base)
├── ConfigError
│   └── raised when config.toml or .env is invalid/missing
├── DatabaseError
│   └── raised for schema or migration failures (not query-level)
├── ScraperError
│   ├── CloudflareTimeoutError
│   ├── LoginError
│   ├── SessionExpiredError
│   └── APIError
├── ResolverError
│   └── raised when Semantic Scholar API is completely unreachable
├── CitationPollError
│   └── raised when all citation sources fail for an entire poll cycle
└── RulesError
    └── raised for logic errors in prune/promote (shouldn't happen)
```

All custom exceptions inherit from `ScholarCurateError` for easy catch-all handling. Import with:
```python
from src.errors import ScholarCurateError, ConfigError, DatabaseError, ScraperError, ...
```

---

## Per-Component Error Strategy

### Scraper (`src/ingestion/scraper.py`)

| Error | Cause | Action |
|-------|-------|--------|
| `CloudflareTimeoutError` | Challenge not solved within 120s | Abort run, log, record in `ingestion_runs` as failed |
| `LoginError` | Bad credentials or changed login form | Abort run, log prominently, suggest `reset-session` |
| `APIError` | API response format changed or unexpected status | Abort run, log response details for debugging |
| `TimeoutError` (Playwright) | Page load timeout | Retry once, then abort |
| Network error | DNS/connection failure | Abort run, log |

**Key principle:** Scraper errors abort the entire ingestion run. Partial scraping is not useful since we can't know what we missed.

### Resolver (`src/ingestion/resolver.py`)

| Error | Cause | Action |
|-------|-------|--------|
| 404 from S2 API | Paper not yet indexed | Use fallback ID, continue |
| 429 from S2 API | Rate limit hit | Configurable retry via `RetryConfig` (default: exponential backoff, 5 attempts) |
| 5xx from S2 API | Server error | Configurable retry via `RetryConfig` (default: exponential backoff, 5 attempts) |
| Timeout | Slow API response | Use fallback ID, continue |
| No title match | Search returned irrelevant results | Use fallback ID, log warning |

**Key principle:** Individual paper resolution failures are tolerable. Use fallback IDs and continue. The paper will be re-resolved on the next cycle.

### Citation Polling (`src/citations/`)

| Error | Cause | Action |
|-------|-------|--------|
| 429 from S2 batch API | Rate limit | Configurable retry via `RetryConfig` (default: exponential backoff, 5 attempts). Respects `Retry-After` header as minimum wait. |
| 5xx from S2 batch API | Server error | Configurable retry via `RetryConfig` (default: exponential backoff, 5 attempts). Skip batch if all attempts exhausted. |
| Partial null results | Some papers not found in batch | Skip those papers, update the rest |
| OpenAlex 404 | Paper not in OpenAlex | Skip yearly breakdown, log debug |
| OpenAlex timeout | Slow response | Skip, will retry next monthly cycle |
| All sources fail | Both APIs down | Log error, don't update any papers, try next cycle |

**Key principle:** Partial success is acceptable. If 80 of 100 papers get updated, that's fine — the remaining 20 will be retried next cycle.

### Prune/Promote Rules (`src/rules.py`)

Rules operate entirely on local database data, so external failures don't apply. Potential errors:

| Error | Cause | Action |
|-------|-------|--------|
| Missing snapshot data | Paper has no snapshots yet | Skip (velocity = 0, won't be pruned or promoted) |
| Database write error | Disk full, permissions | Rollback transaction, raise `DatabaseError` |

---

## Retry Strategy

### Configurable Retry via `RetryConfig`

All retry logic is centralised in `src/retry.py` through the `RetryConfig` dataclass, which supports two strategies:

```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 5                              # total attempts
    strategy: Literal["fixed", "exponential"] = "exponential"
    base_delay: float = 2.0                            # seconds
    max_delay: float = 60.0                            # cap (exponential only)

    def delay(self, attempt: int) -> float:
        """Compute wait time for the given 0-based attempt.

        Fixed:       base_delay (constant)
        Exponential: min(base_delay * 2^attempt, max_delay) + jitter
        """
```

A default instance is defined in `src/constants.py`:

```python
from src.retry import RetryConfig

DEFAULT_RETRY = RetryConfig()  # exponential, 5 attempts, 2s base, 60s cap
```

Both the single-paper resolver and the batch citation poller accept an optional `retry` parameter, defaulting to `DEFAULT_RETRY`. To switch to a fixed-delay strategy:

```python
fixed = RetryConfig(strategy="fixed", base_delay=5.0, max_attempts=3)
await fetch_citations_batch(client, ids, api_key=key, retry=fixed)
```

---

## Graceful Degradation

### Scenario: Semantic Scholar API Down

If the S2 API is completely unreachable during a poll cycle:
1. All batch requests fail after retries
2. No snapshots are recorded
3. No velocities are updated
4. No prune/promote rules run (they depend on fresh data)
5. `last_cited_check` is NOT updated — so these papers remain "due for poll"
6. Next scheduled poll retries everything

The system does not crash. It simply skips the cycle and tries again later.

### Scenario: Semantic Scholar API Temporarily Down During Ingestion

If the S2 API returns 5xx errors during paper resolution:
1. Individual papers get fallback IDs (`title:{hash}`) and are stored in the DB
2. The ingestion run completes successfully — scraping and storage are unaffected
3. The date is recorded in `scraped_dates`, so backfill won't re-scrape it
4. **Problem:** These "dangling" papers cannot be citation-polled
5. **Self-healing:** The next `run_backfill()` call automatically runs re-resolution, which re-attempts S2 lookup for all dangling papers
6. Once resolved, the paper gets a proper S2 ID and enters normal citation polling

Similarly, backfill-ingested papers that lack a `semantic_scholar_id` get `si-{paper_id}` synthetic IDs. These are also picked up by re-resolution.

### Scenario: Scholar Inbox Down or Blocked

If scraping fails:
1. Ingestion run is recorded as `failed` with error details
2. Citation polling and rules continue independently
3. Existing papers in the database are unaffected

### Scenario: Database Corruption

SQLite with WAL mode is very robust. If corruption occurs:
1. Most operations will raise `sqlite3.DatabaseError`
2. The CLI catches this and logs a fatal error
3. Recovery: restore from backup or delete and rebuild

Future consideration: periodic backup of `scholar_curate.db` (simple file copy when no writes are happening).

---

## Logging for Diagnostics

### Structured Log Fields

All log messages include contextual information:

```python
# Good
logger.info("Ingestion complete: found=%d, new=%d, run_id=%d", found, new, run_id)
logger.warning("S2 batch request failed: status=%d, batch_size=%d", status, len(ids))

# Bad (avoid)
logger.info("Done!")
logger.error(str(e))  # Always include context
```

### Error Logs Include Recovery Hints

```python
except CloudflareTimeoutError:
    logger.error(
        "Cloudflare challenge timed out. "
        "Try: scholar-curate reset-session && scholar-curate ingest"
    )

except LoginError:
    logger.error(
        "Login failed. Verify credentials in .env: "
        "SCHOLAR_INBOX_EMAIL and SCHOLAR_INBOX_PASSWORD"
    )
```

---

## Database Transaction Safety

All database write operations use explicit transactions via the `get_connection()` context manager (defined in doc 01), which auto-commits on success and rolls back on exception.

For operations that modify multiple tables (e.g., inserting a paper + its initial snapshot), they happen within a single `get_connection()` block to ensure atomicity:

```python
with get_connection(db_path) as conn:
    upsert_paper(conn, paper_dict)
    insert_snapshot(conn, paper_id, citation_count, "semantic_scholar")
    # Both succeed or both roll back
```

---

## Health Check

For monitoring, the web UI exposes a simple health endpoint:

```python
@app.get("/health")
async def health():
    """Basic health check — verifies DB connectivity."""
    try:
        with get_connection(config.db_path) as conn:
            conn.execute("SELECT 1")
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
```

This is useful if running behind a reverse proxy or process manager.
