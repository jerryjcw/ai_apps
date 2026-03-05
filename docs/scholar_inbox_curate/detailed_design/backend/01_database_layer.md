# 01 — Database Layer

## Overview

The database layer manages an SQLite database for storing papers, citation snapshots, and ingestion audit logs. It handles schema creation, migrations, and provides a repository-style API for all data access.

---

## Database Connection (`src/db.py`)

### Connection Management

SQLite connections are managed via a context manager that ensures proper cleanup:

```python
import sqlite3
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def get_connection(db_path: str):
    """Yield a SQLite connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Access columns by name
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

**Why WAL mode?** Write-Ahead Logging allows concurrent reads while writing, which matters when the scheduler writes citation data while the web UI reads it.

---

## Schema Definition

### `papers` Table

```sql
CREATE TABLE IF NOT EXISTS papers (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    authors             TEXT,                -- JSON array: ["Alice Smith", "Bob Jones"]
    abstract            TEXT,
    url                 TEXT,                -- Scholar Inbox URL or DOI link
    arxiv_id            TEXT,
    doi                 TEXT,                -- DOI identifier (from Semantic Scholar)
    category            TEXT,                -- Scholar Inbox topic category
    venue               TEXT,
    year                INTEGER,
    published_date      TEXT,                -- ISO 8601, actual publication/preprint date
    scholar_inbox_score REAL,
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK(status IN ('active', 'promoted', 'pruned')),
    manual_status       INTEGER NOT NULL DEFAULT 0,  -- 1 if status was manually set
    ingested_at         TEXT NOT NULL,       -- ISO 8601
    last_cited_check    TEXT,                -- ISO 8601
    citation_count      INTEGER NOT NULL DEFAULT 0,
    citation_velocity   REAL NOT NULL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(status);
CREATE INDEX IF NOT EXISTS idx_papers_ingested_at ON papers(ingested_at);
CREATE INDEX IF NOT EXISTS idx_papers_velocity ON papers(citation_velocity DESC);
CREATE INDEX IF NOT EXISTS idx_papers_arxiv_id ON papers(arxiv_id);
```

**Key design decisions:**

- `id` is the Semantic Scholar `paperId` (a 40-char hex hash). If Semantic Scholar lookup fails, fall back to `doi:<DOI>` or `arxiv:<arxiv_id>` as synthetic IDs.
- `authors` is a JSON array rather than a separate table — we never query by individual author, so normalization adds complexity without benefit.
- `manual_status` flag prevents the prune/promote rules engine from overriding a user's deliberate status change.
- `published_date` is distinct from `ingested_at` — it captures when the paper was actually published/posted to arXiv, which is needed for age-based pruning. If not available from Semantic Scholar, defaults to `ingested_at`.

### `citation_snapshots` Table

```sql
CREATE TABLE IF NOT EXISTS citation_snapshots (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id         TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    checked_at       TEXT NOT NULL,          -- ISO 8601
    total_citations  INTEGER NOT NULL,
    yearly_breakdown TEXT,                   -- JSON: {"2024": 12, "2025": 34}
    source           TEXT NOT NULL CHECK(source IN ('semantic_scholar', 'openalex'))
);

CREATE INDEX IF NOT EXISTS idx_snapshots_paper_date
    ON citation_snapshots(paper_id, checked_at DESC);
```

**Why `ON DELETE CASCADE`?** If a paper is fully removed (rare, admin-only), its snapshots should go with it. Pruned papers are not deleted — they stay in the DB with `status='pruned'`.

### `ingestion_runs` Table

```sql
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    papers_found    INTEGER NOT NULL DEFAULT 0,
    papers_ingested INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK(status IN ('running', 'completed', 'failed')),
    error_message   TEXT,
    digest_date     TEXT                        -- YYYY-MM-DD, added in V2
);
```

### `scraped_dates` Table

Tracks which Scholar Inbox digest dates have been successfully scraped, enabling gap detection for backfill. Added in schema V2.

```sql
CREATE TABLE IF NOT EXISTS scraped_dates (
    digest_date  TEXT PRIMARY KEY,              -- YYYY-MM-DD
    scraped_at   TEXT NOT NULL,                 -- ISO 8601 timestamp
    run_id       INTEGER REFERENCES ingestion_runs(id),
    papers_found INTEGER NOT NULL DEFAULT 0
);
```

**Key design decisions:**

- `digest_date` is the primary key — each calendar date can only appear once. Re-scraping the same date updates the existing row.
- `run_id` links back to the `ingestion_runs` record for audit trail.
- `papers_found` records how many papers were above threshold for that date, useful for diagnostics (a zero-paper day vs a missed day are different).
- This table is separate from `ingestion_runs` because one backfill run may cover many dates, and we need efficient lookup by date.

---

## Schema Initialization & Migrations

### Approach: Version-based Inline Migrations

Rather than using a migration framework (overkill for a personal tool), the database uses a `schema_version` pragma and a series of migration functions:

```python
CURRENT_SCHEMA_VERSION = 2

def init_db(db_path: str):
    """Create tables if they don't exist and run any pending migrations."""
    with get_connection(db_path) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]

        if version == 0:
            # Fresh database — create all tables with V2 schema
            conn.executescript(_SCHEMA_V1)
            conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
        else:
            # Run incremental migrations for older databases
            _run_migrations(conn, version)
```

Migration functions are registered in order:

```python
_MIGRATIONS = {
    # version_from: migration_function
    1: _migrate_v1_to_v2,  # adds scraped_dates table + digest_date column + run_id/papers_found
}

def _run_migrations(conn, current_version: int):
    while current_version < CURRENT_SCHEMA_VERSION:
        migrate_fn = _MIGRATIONS[current_version]
        migrate_fn(conn)
        current_version += 1
        conn.execute(f"PRAGMA user_version = {current_version}")
```

This allows adding columns or tables in the future without requiring users to recreate their database.

**Current Schema Version: 4**
- V1: Initial schema with papers, citation_snapshots, ingestion_runs
- V2: Adds scraped_dates table with run_id/papers_found columns for backfill audit trail
- V3: Adds `doi` column to papers table
- V4: Adds `category` column to papers table (Scholar Inbox topic category)

### V1 → V2 Migration

The V2 migration adds backfill support:

```python
def _migrate_v1_to_v2(conn):
    """Add scraped_dates table and digest_date column to ingestion_runs."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scraped_dates (
            digest_date  TEXT PRIMARY KEY,
            scraped_at   TEXT NOT NULL,
            run_id       INTEGER REFERENCES ingestion_runs(id),
            papers_found INTEGER NOT NULL DEFAULT 0
        );

        ALTER TABLE ingestion_runs ADD COLUMN digest_date TEXT;
    """)
```

---

## Repository Functions

All database access goes through functions in `src/db.py`. These functions accept a connection and return plain dicts or dataclass instances.

### Paper Operations

```python
def upsert_paper(conn, paper: dict) -> bool:
    """Insert a paper or update if it already exists.

    Returns True if a new paper was inserted, False if updated.
    Uses INSERT ... ON CONFLICT to handle duplicates by paper ID.
    """

def get_paper(conn, paper_id: str) -> dict | None:
    """Fetch a single paper by ID."""

def list_papers(
    conn,
    status: str | None = None,
    sort_by: str = "citation_velocity",
    sort_order: str = "DESC",
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List papers with optional filtering, sorting, and pagination."""

def update_paper_status(conn, paper_id: str, status: str, manual: bool = False):
    """Update paper status. If manual=True, sets manual_status=1."""

def update_paper_citations(conn, paper_id: str, citation_count: int, velocity: float):
    """Update citation count and velocity after a poll cycle."""

def get_papers_due_for_poll(conn, now: str) -> list[dict]:
    """Return papers that need citation polling based on age-based schedule.

    Logic:
    - status='pruned' → skip
    - last_cited_check is NULL → include (never polled)
    - age < 3 months AND last check > 7 days ago → include
    - age 3-12 months AND last check > 14 days ago → include
    - age > 12 months AND last check > 30 days ago → include
    - status='promoted' AND last check > 30 days ago → include
    """

def get_papers_never_polled(conn) -> list[dict]:
    """Return papers that have never had citation data collected.

    Selects papers where last_cited_check IS NULL and status != 'pruned'.
    Used by the collect-citations command to target backfilled papers.
    """

def get_paper_count_by_status(conn) -> dict[str, int]:
    """Return {"active": N, "promoted": N, "pruned": N}."""

def count_papers(
    conn,
    status: str | None = None,
    search: str | None = None,
) -> int:
    """Count papers matching the given filters.

    Used by the web UI for pagination. Mirrors the filter logic of list_papers().
    """

def paper_exists(conn, paper_id: str) -> bool:
    """Check if a paper ID already exists in the database."""
```

### Citation Snapshot Operations

```python
def insert_snapshot(conn, paper_id: str, total_citations: int,
                    source: str, yearly_breakdown: dict | None = None):
    """Insert a new citation snapshot."""

def get_snapshots(conn, paper_id: str, limit: int = 50) -> list[dict]:
    """Get citation snapshots for a paper, ordered by checked_at DESC."""

def get_snapshot_for_velocity(conn, paper_id: str, months_ago: int = 3) -> dict | None:
    """Get the snapshot closest to N months ago for velocity computation.

    Uses: SELECT ... WHERE paper_id = ? AND checked_at <= date(?, '-N months')
          ORDER BY checked_at DESC LIMIT 1
    """

def get_earliest_snapshot(conn, paper_id: str) -> dict | None:
    """Get the first snapshot ever taken for a paper."""
```

### Ingestion Run Operations

```python
def create_ingestion_run(conn) -> int:
    """Create a new ingestion run record, return its ID."""

def update_ingestion_run(conn, run_id: int, papers_found: int,
                         papers_ingested: int, status: str,
                         error_message: str | None = None):
    """Update an ingestion run with results."""

def get_recent_ingestion_runs(conn, limit: int = 10) -> list[dict]:
    """Get recent ingestion runs for display."""
```

### Scraped Date Operations

```python
def record_scraped_date(conn, digest_date: str, run_id: int,
                        papers_found: int) -> None:
    """Record that a digest date has been successfully scraped.

    Uses INSERT OR REPLACE so re-scraping a date updates the record.

    Args:
        digest_date: Calendar date in YYYY-MM-DD format.
        run_id: ID of the ingestion_run that scraped this date.
        papers_found: Number of papers above threshold for this date.
    """

def get_scraped_dates(conn, since_date: str) -> set[str]:
    """Return all digest dates (YYYY-MM-DD) that have been scraped since a given date.

    Args:
        since_date: Only return dates on or after this date (YYYY-MM-DD).
    """

def find_missing_dates(conn, lookback_days: int) -> list[str]:
    """Identify digest dates within the lookback window that have not been scraped.

    Computes the date range [today - lookback_days, yesterday], subtracts
    dates present in scraped_dates, and returns the missing dates sorted
    ascending as YYYY-MM-DD strings.

    Today is excluded because it may not have a digest yet.
    """
```

---

## Date/Time Handling

All timestamps are stored as ISO 8601 strings in UTC: `2026-02-26T08:00:00Z`.

Utility functions:

```python
from datetime import datetime, timezone

def now_utc() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()

def months_between(date1: str, date2: str) -> float:
    """Compute approximate months between two ISO 8601 dates."""
    d1 = datetime.fromisoformat(date1)
    d2 = datetime.fromisoformat(date2)
    delta = abs((d2 - d1).days)
    return delta / 30.44  # Average days per month
```

---

## Testing Strategy

- Tests use an **in-memory SQLite database** (`:memory:`) created via a pytest fixture
- `conftest.py` provides a `db_conn` fixture that calls `init_db` on a fresh in-memory DB
- Each test function gets a clean database — no state leaks between tests
- Test data fixtures provide sample papers and snapshots for query testing

```python
# tests/conftest.py
import pytest
from src.db import get_connection, init_db

@pytest.fixture
def db_conn():
    """Provide a fresh in-memory database connection for each test."""
    with get_connection(":memory:") as conn:
        init_db_on_conn(conn)  # variant that takes a connection directly
        yield conn
```
