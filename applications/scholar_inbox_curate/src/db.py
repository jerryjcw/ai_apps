"""Database layer for Scholar Inbox Curate.

Manages SQLite connection, schema creation, migrations, and provides
repository-style functions for all data access.
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

from src.constants import CURRENT_SCHEMA_VERSION

logger = logging.getLogger(__name__)

_SCHEMA_V1 = """\
CREATE TABLE IF NOT EXISTS papers (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    authors             TEXT,
    abstract            TEXT,
    url                 TEXT,
    arxiv_id            TEXT,
    doi                 TEXT,
    venue               TEXT,
    year                INTEGER,
    published_date      TEXT,
    scholar_inbox_score REAL,
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK(status IN ('active', 'promoted', 'pruned')),
    manual_status       INTEGER NOT NULL DEFAULT 0,
    ingested_at         TEXT NOT NULL,
    last_cited_check    TEXT,
    citation_count      INTEGER NOT NULL DEFAULT 0,
    citation_velocity   REAL NOT NULL DEFAULT 0.0,
    category            TEXT,
    resolve_failures    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(status);
CREATE INDEX IF NOT EXISTS idx_papers_ingested_at ON papers(ingested_at);
CREATE INDEX IF NOT EXISTS idx_papers_velocity ON papers(citation_velocity DESC);
CREATE INDEX IF NOT EXISTS idx_papers_arxiv_id ON papers(arxiv_id);

CREATE TABLE IF NOT EXISTS citation_snapshots (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id         TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    checked_at       TEXT NOT NULL,
    total_citations  INTEGER NOT NULL,
    yearly_breakdown TEXT,
    source           TEXT NOT NULL CHECK(source IN ('semantic_scholar', 'openalex'))
);

CREATE INDEX IF NOT EXISTS idx_snapshots_paper_date
    ON citation_snapshots(paper_id, checked_at DESC);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    papers_found    INTEGER NOT NULL DEFAULT 0,
    papers_ingested INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK(status IN ('running', 'completed', 'failed')),
    error_message   TEXT,
    digest_date     TEXT
);

CREATE TABLE IF NOT EXISTS scraped_dates (
    digest_date  TEXT PRIMARY KEY,
    scraped_at   TEXT NOT NULL,
    run_id       INTEGER REFERENCES ingestion_runs(id),
    papers_found INTEGER NOT NULL DEFAULT 0
);
"""

def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Add scraped_dates table and digest_date column to ingestion_runs."""
    conn.execute("""\
        CREATE TABLE IF NOT EXISTS scraped_dates (
            digest_date  TEXT PRIMARY KEY,
            scraped_at   TEXT NOT NULL,
            run_id       INTEGER REFERENCES ingestion_runs(id),
            papers_found INTEGER NOT NULL DEFAULT 0
        )
    """)
    # ALTER TABLE is safe to run multiple times if column already exists
    try:
        conn.execute("ALTER TABLE ingestion_runs ADD COLUMN digest_date TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    """Add doi column to papers table."""
    try:
        conn.execute("ALTER TABLE papers ADD COLUMN doi TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists


def _migrate_v3_to_v4(conn: sqlite3.Connection) -> None:
    """Add category column to papers table."""
    try:
        conn.execute("ALTER TABLE papers ADD COLUMN category TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists


def _migrate_v4_to_v5(conn: sqlite3.Connection) -> None:
    """Add resolve_failures column to papers table."""
    try:
        conn.execute(
            "ALTER TABLE papers ADD COLUMN resolve_failures INTEGER NOT NULL DEFAULT 0"
        )
    except sqlite3.OperationalError:
        pass  # Column already exists


# Migration functions: version_from -> callable
_MIGRATIONS: dict[int, callable] = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
    4: _migrate_v4_to_v5,
}


# ---------------------------------------------------------------------------
# Date/Time Helpers
# ---------------------------------------------------------------------------

def now_utc() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def months_between(date1: str, date2: str) -> float:
    """Compute approximate months between two ISO 8601 dates."""
    d1 = datetime.fromisoformat(date1)
    d2 = datetime.fromisoformat(date2)
    delta = abs((d2 - d1).days)
    return delta / 30.44  # Average days per month


# ---------------------------------------------------------------------------
# Connection Management
# ---------------------------------------------------------------------------

@contextmanager
def get_connection(db_path: str):
    """Yield a SQLite connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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


# ---------------------------------------------------------------------------
# Schema Initialization & Migrations
# ---------------------------------------------------------------------------

def init_db(db_path: str) -> None:
    """Create tables if they don't exist and run any pending migrations."""
    with get_connection(db_path) as conn:
        init_db_on_conn(conn)


def init_db_on_conn(conn: sqlite3.Connection) -> None:
    """Create tables and run migrations on an existing connection.

    This variant is used by tests that pass an in-memory connection directly.
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]

    if version == 0:
        conn.executescript(_SCHEMA_V1)
        conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
    else:
        _run_migrations(conn, version)


def _run_migrations(conn: sqlite3.Connection, current_version: int) -> None:
    """Run incremental migrations from current_version to CURRENT_SCHEMA_VERSION."""
    while current_version < CURRENT_SCHEMA_VERSION:
        migrate_fn = _MIGRATIONS[current_version]
        migrate_fn(conn)
        current_version += 1
        conn.execute(f"PRAGMA user_version = {current_version}")


# ---------------------------------------------------------------------------
# Helper to convert sqlite3.Row to dict
# ---------------------------------------------------------------------------

def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Paper Operations
# ---------------------------------------------------------------------------

def upsert_paper(conn: sqlite3.Connection, paper: dict) -> bool:
    """Insert a paper or update if it already exists.

    Returns True if a new paper was inserted, False if updated.
    """
    existed = paper_exists(conn, paper["id"])

    sql = """\
        INSERT INTO papers (
            id, title, authors, abstract, url, arxiv_id, doi, venue, year,
            published_date, scholar_inbox_score, status, manual_status,
            ingested_at, last_cited_check, citation_count, citation_velocity,
            category, resolve_failures
        ) VALUES (
            :id, :title, :authors, :abstract, :url, :arxiv_id, :doi, :venue, :year,
            :published_date, :scholar_inbox_score,
            :status, :manual_status, :ingested_at,
            :last_cited_check, :citation_count, :citation_velocity,
            :category, :resolve_failures
        )
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            authors = excluded.authors,
            abstract = excluded.abstract,
            url = excluded.url,
            arxiv_id = excluded.arxiv_id,
            doi = excluded.doi,
            venue = excluded.venue,
            year = excluded.year,
            published_date = excluded.published_date,
            scholar_inbox_score = excluded.scholar_inbox_score,
            category = excluded.category
    """
    defaults = {
        "status": "active",
        "manual_status": 0,
        "ingested_at": now_utc(),
        "last_cited_check": None,
        "citation_count": 0,
        "citation_velocity": 0.0,
        "published_date": None,
        "abstract": None,
        "url": None,
        "arxiv_id": None,
        "doi": None,
        "venue": None,
        "year": None,
        "scholar_inbox_score": None,
        "category": None,
        "resolve_failures": 0,
    }
    params = {**defaults, **paper}

    if isinstance(params.get("authors"), list):
        params["authors"] = json.dumps(params["authors"])

    conn.execute(sql, params)
    return not existed


def get_paper(conn: sqlite3.Connection, paper_id: str) -> dict | None:
    """Fetch a single paper by ID."""
    row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    return _row_to_dict(row)


def list_papers(
    conn: sqlite3.Connection,
    status: str | None = None,
    sort_by: str = "citation_velocity",
    sort_order: str = "DESC",
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List papers with optional filtering, sorting, and pagination."""
    allowed_sort_columns = {
        "citation_velocity", "citation_count", "ingested_at",
        "scholar_inbox_score", "title", "year", "published_date",
    }
    if sort_by not in allowed_sort_columns:
        sort_by = "citation_velocity"

    sort_order = sort_order.upper()
    if sort_order not in ("ASC", "DESC"):
        sort_order = "DESC"

    conditions = []
    params: list = []

    if status is not None:
        conditions.append("status = ?")
        params.append(status)

    if search is not None:
        words = search.split()
        for word in words:
            conditions.append("(title LIKE ? OR authors LIKE ? OR abstract LIKE ?)")
            pattern = f"%{word}%"
            params.extend([pattern, pattern, pattern])

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"SELECT * FROM papers {where_clause} ORDER BY {sort_by} {sort_order} LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(sql, params).fetchall()
    return _rows_to_dicts(rows)


def update_paper_status(
    conn: sqlite3.Connection, paper_id: str, status: str, manual: bool = False
) -> None:
    """Update paper status. If manual=True, sets manual_status=1."""
    manual_val = 1 if manual else 0
    conn.execute(
        "UPDATE papers SET status = ?, manual_status = ? WHERE id = ?",
        (status, manual_val, paper_id),
    )


def update_paper_citations(
    conn: sqlite3.Connection, paper_id: str, citation_count: int, velocity: float
) -> None:
    """Update citation count and velocity after a poll cycle."""
    conn.execute(
        "UPDATE papers SET citation_count = ?, citation_velocity = ?, last_cited_check = ? WHERE id = ?",
        (citation_count, velocity, now_utc(), paper_id),
    )


def count_non_pruned_papers(conn: sqlite3.Connection) -> int:
    """Return the count of papers whose status is not 'pruned'."""
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM papers WHERE status != 'pruned'"
    ).fetchone()
    return row["cnt"]


def get_papers_due_for_poll(
    conn: sqlite3.Connection, now: str, limit: int | None = None
) -> list[dict]:
    """Return papers that need citation polling based on age-based schedule.

    Papers are ordered by overdue ratio (never-polled first, then most
    overdue relative to their scheduled interval).  An optional *limit*
    caps the number of rows returned for budget-based polling.

    Logic:
    - status='pruned' -> skip
    - last_cited_check is NULL -> include (never polled)
    - age < 3 months AND last check > 7 days ago -> include
    - age 3-12 months AND last check > 14 days ago -> include
    - age > 12 months AND last check > 30 days ago -> include
    - status='promoted' AND last check > 30 days ago -> include
    """
    sql = """\
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
    """
    if limit is not None:
        sql += f"\n        LIMIT {int(limit)}"
    rows = conn.execute(sql, {"now": now}).fetchall()
    return _rows_to_dicts(rows)


def get_papers_never_polled(conn: sqlite3.Connection) -> list[dict]:
    """Return papers that have never had citation data collected.

    Selects papers where ``last_cited_check IS NULL`` and ``status != 'pruned'``.
    """
    rows = conn.execute(
        "SELECT * FROM papers WHERE last_cited_check IS NULL AND status != 'pruned'"
    ).fetchall()
    return _rows_to_dicts(rows)


def get_paper_count_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    """Return {"active": N, "promoted": N, "pruned": N}."""
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM papers GROUP BY status"
    ).fetchall()
    result = {"active": 0, "promoted": 0, "pruned": 0}
    for row in rows:
        result[row["status"]] = row["cnt"]
    return result


def count_papers(
    conn: sqlite3.Connection,
    status: str | None = None,
    search: str | None = None,
) -> int:
    """Count papers matching the given filters.

    Used by the web UI for pagination. Mirrors the filter logic of list_papers().
    """
    conditions = []
    params: list = []

    if status is not None:
        conditions.append("status = ?")
        params.append(status)

    if search is not None:
        words = search.split()
        for word in words:
            conditions.append("(title LIKE ? OR authors LIKE ? OR abstract LIKE ?)")
            pattern = f"%{word}%"
            params.extend([pattern, pattern, pattern])

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    row = conn.execute(
        f"SELECT COUNT(*) as cnt FROM papers {where_clause}", params
    ).fetchone()
    return row["cnt"]


def get_dangling_papers(
    conn: sqlite3.Connection,
    max_failures: int = 3,
) -> list[dict]:
    """Return papers with unresolved synthetic IDs (``title:`` or ``si-`` prefix).

    These papers were stored with fallback IDs because Semantic Scholar
    resolution failed at ingestion time.  They cannot be citation-polled
    until re-resolved.

    Papers whose ``resolve_failures`` counter has reached *max_failures*
    are excluded — they will be retried after the counter is reset
    (e.g. at the start of the next backfill cycle).
    """
    rows = conn.execute(
        "SELECT * FROM papers "
        "WHERE (id LIKE 'title:%' OR id LIKE 'si-%') "
        "AND resolve_failures < ?",
        (max_failures,),
    ).fetchall()
    return _rows_to_dicts(rows)


def increment_resolve_failures(conn: sqlite3.Connection, paper_id: str) -> None:
    """Increment the resolve_failures counter for a paper."""
    conn.execute(
        "UPDATE papers SET resolve_failures = resolve_failures + 1 WHERE id = ?",
        (paper_id,),
    )


def reset_resolve_failures(conn: sqlite3.Connection) -> None:
    """Reset resolve_failures to 0 for all dangling papers.

    Called at the start of a backfill cycle so every paper gets a fresh
    set of resolution attempts.
    """
    conn.execute(
        "UPDATE papers SET resolve_failures = 0 "
        "WHERE (id LIKE 'title:%' OR id LIKE 'si-%') AND resolve_failures > 0"
    )


def replace_paper_id(
    conn: sqlite3.Connection,
    old_id: str,
    new_id: str,
    updated_fields: dict,
) -> bool:
    """Replace a paper's synthetic ID with a resolved one and update metadata.

    Deletes the old row (``ON DELETE CASCADE`` removes any snapshots) and
    inserts a new row with the resolved ID.  This is safe because dangling
    papers have no useful citation snapshots.

    Returns ``True`` if the replacement was performed, ``False`` if *new_id*
    already exists (in which case the dangling duplicate is simply deleted).
    """
    if paper_exists(conn, new_id):
        conn.execute("DELETE FROM papers WHERE id = ?", (old_id,))
        return False

    row = conn.execute("SELECT * FROM papers WHERE id = ?", (old_id,)).fetchone()
    if row is None:
        return False

    old_paper = dict(row)
    merged = {**old_paper, **updated_fields, "id": new_id}
    conn.execute("DELETE FROM papers WHERE id = ?", (old_id,))
    upsert_paper(conn, merged)
    return True


def paper_exists(conn: sqlite3.Connection, paper_id: str) -> bool:
    """Check if a paper ID already exists in the database."""
    row = conn.execute(
        "SELECT 1 FROM papers WHERE id = ? LIMIT 1", (paper_id,)
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Citation Snapshot Operations
# ---------------------------------------------------------------------------

def insert_snapshot(
    conn: sqlite3.Connection,
    paper_id: str,
    total_citations: int,
    source: str,
    yearly_breakdown: dict | None = None,
) -> None:
    """Insert a new citation snapshot."""
    breakdown_json = json.dumps(yearly_breakdown) if yearly_breakdown else None
    conn.execute(
        """\
        INSERT INTO citation_snapshots (paper_id, checked_at, total_citations, yearly_breakdown, source)
        VALUES (?, ?, ?, ?, ?)
        """,
        (paper_id, now_utc(), total_citations, breakdown_json, source),
    )


def get_snapshots(
    conn: sqlite3.Connection, paper_id: str, limit: int = 50
) -> list[dict]:
    """Get citation snapshots for a paper, ordered by checked_at DESC."""
    rows = conn.execute(
        "SELECT * FROM citation_snapshots WHERE paper_id = ? ORDER BY checked_at DESC LIMIT ?",
        (paper_id, limit),
    ).fetchall()
    return _rows_to_dicts(rows)


def get_snapshot_for_velocity(
    conn: sqlite3.Connection, paper_id: str, months_ago: int = 3
) -> dict | None:
    """Get the snapshot closest to N months ago for velocity computation.

    Uses datetime() with a month offset modifier to find the snapshot
    taken closest to (but not after) N months ago.
    """
    reference = now_utc()
    modifier = f"-{months_ago} months"
    row = conn.execute(
        "SELECT * FROM citation_snapshots "
        "WHERE paper_id = ? AND checked_at <= datetime(?, ?) "
        "ORDER BY checked_at DESC LIMIT 1",
        (paper_id, reference, modifier),
    ).fetchone()
    return _row_to_dict(row)


def get_earliest_snapshot(
    conn: sqlite3.Connection, paper_id: str
) -> dict | None:
    """Get the first snapshot ever taken for a paper."""
    row = conn.execute(
        "SELECT * FROM citation_snapshots WHERE paper_id = ? ORDER BY checked_at ASC LIMIT 1",
        (paper_id,),
    ).fetchone()
    return _row_to_dict(row)


# ---------------------------------------------------------------------------
# Ingestion Run Operations
# ---------------------------------------------------------------------------

def create_ingestion_run(conn: sqlite3.Connection) -> int:
    """Create a new ingestion run record, return its ID."""
    cursor = conn.execute(
        "INSERT INTO ingestion_runs (started_at) VALUES (?)",
        (now_utc(),),
    )
    return cursor.lastrowid


def update_ingestion_run(
    conn: sqlite3.Connection,
    run_id: int,
    papers_found: int,
    papers_ingested: int,
    status: str,
    error_message: str | None = None,
) -> None:
    """Update an ingestion run with results."""
    conn.execute(
        """\
        UPDATE ingestion_runs
        SET finished_at = ?, papers_found = ?, papers_ingested = ?, status = ?, error_message = ?
        WHERE id = ?
        """,
        (now_utc(), papers_found, papers_ingested, status, error_message, run_id),
    )


def get_recent_ingestion_runs(
    conn: sqlite3.Connection, limit: int = 10
) -> list[dict]:
    """Get recent ingestion runs for display."""
    rows = conn.execute(
        "SELECT * FROM ingestion_runs ORDER BY started_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Scraped Dates Operations
# ---------------------------------------------------------------------------

def record_scraped_date(
    conn: sqlite3.Connection,
    digest_date: str,
    run_id: int | None = None,
    papers_found: int = 0,
) -> None:
    """Record that a digest date has been scraped.

    Uses INSERT OR REPLACE to allow updates if re-scraping the same date.
    ``digest_date`` should be in ``YYYY-MM-DD`` format.

    Parameters
    ----------
    conn : sqlite3.Connection
    digest_date : str
        Calendar date in YYYY-MM-DD format
    run_id : int, optional
        ID of the ingestion_run that scraped this date
    papers_found : int
        Number of papers above threshold for this date
    """
    conn.execute(
        "INSERT OR REPLACE INTO scraped_dates (digest_date, scraped_at, run_id, papers_found) VALUES (?, ?, ?, ?)",
        (digest_date, now_utc(), run_id, papers_found),
    )


def get_scraped_dates(conn: sqlite3.Connection) -> set[str]:
    """Return the set of all digest dates that have been scraped (YYYY-MM-DD)."""
    rows = conn.execute("SELECT digest_date FROM scraped_dates").fetchall()
    return {row["digest_date"] for row in rows}


def find_missing_dates(
    conn: sqlite3.Connection,
    lookback_days: int,
    today: date | None = None,
) -> list[str]:
    """Return weekday dates within the lookback window that haven't been scraped.

    Scholar Inbox only publishes digests on weekdays (Mon-Fri), so weekends
    are excluded from the result.

    Parameters
    ----------
    conn : sqlite3.Connection
    lookback_days : int
        How many days back to check.
    today : date, optional
        Override for testability; defaults to ``date.today()``.

    Returns
    -------
    list[str]
        Missing weekday dates as YYYY-MM-DD strings, sorted oldest-first.
    """
    if today is None:
        today = date.today()

    scraped = get_scraped_dates(conn)

    missing: list[str] = []
    for offset in range(1, lookback_days + 1):
        d = today - timedelta(days=offset)
        # Skip weekends (5=Saturday, 6=Sunday)
        if d.weekday() >= 5:
            continue
        date_str = d.isoformat()
        if date_str not in scraped:
            missing.append(date_str)

    missing.sort()
    return missing


# ---------------------------------------------------------------------------
# Analytics & Dashboard Queries
# ---------------------------------------------------------------------------

def get_trending_papers(
    conn: sqlite3.Connection,
    limit: int = 10,
) -> list[dict]:
    """Get papers with highest citation velocity.

    Used for dashboard "Top Papers by Velocity" section.

    Parameters
    ----------
    conn : sqlite3.Connection
    limit : int
        Maximum number of papers to return (default: 10)

    Returns
    -------
    list[dict]
        Papers ordered by citation_velocity DESC
    """
    rows = conn.execute(
        """\
        SELECT id, title, authors, citation_count, citation_velocity, status
        FROM papers
        WHERE status IN ('active', 'promoted')
        AND citation_velocity > 0
        ORDER BY citation_velocity DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return _rows_to_dicts(rows)


def get_dashboard_statistics(conn: sqlite3.Connection) -> dict:
    """Get summary statistics for the dashboard.

    Returns
    -------
    dict
        Contains:
        - total_papers: int
        - active: int
        - promoted: int
        - pruned: int
        - trending_count: int (velocity > 5/month)
        - recently_ingested: int (last 7 days)
        - papers_due_for_poll: int
    """
    # Paper counts by status
    status_counts = get_paper_count_by_status(conn)

    # Trending papers (high velocity)
    trending = conn.execute(
        """\
        SELECT COUNT(*) as cnt FROM papers
        WHERE status IN ('active', 'promoted')
        AND citation_velocity > 5.0
        """
    ).fetchone()["cnt"]

    # Recently ingested
    recent = conn.execute(
        """\
        SELECT COUNT(*) as cnt FROM papers
        WHERE julianday('now') - julianday(ingested_at) <= 7
        """
    ).fetchone()["cnt"]

    # Papers due for polling
    now = now_utc()
    due = conn.execute(
        """\
        SELECT COUNT(*) as cnt FROM papers
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
        """,
        {"now": now},
    ).fetchone()["cnt"]

    return {
        "total_papers": sum(status_counts.values()),
        "active": status_counts.get("active", 0),
        "promoted": status_counts.get("promoted", 0),
        "pruned": status_counts.get("pruned", 0),
        "trending_count": trending,
        "recently_ingested": recent,
        "papers_due_for_poll": due,
    }


# ---------------------------------------------------------------------------
# Stats page queries
# ---------------------------------------------------------------------------

# Exclusive last-poll staleness buckets, in days. Each tuple is
# (label, lower_days_inclusive, upper_days_exclusive); None means open-ended.
POLL_STALENESS_BUCKETS: list[tuple[str, float | None, float | None]] = [
    ("< 1 week",     0,   7),
    ("1–2 weeks",    7,   14),
    ("2–4 weeks",    14,  28),
    ("4–8 weeks",    28,  56),
    ("8+ weeks",     56,  None),
]


def get_paper_date_range(conn: sqlite3.Connection) -> dict:
    """Summary of paper date coverage.

    Returns oldest/newest rows by ``published_date`` (ignoring NULLs) and the
    oldest/newest ``ingested_at`` timestamps as the tracking window. Used by
    the Stats page.
    """
    def _fetch(sql: str) -> dict | None:
        row = conn.execute(sql).fetchone()
        return _row_to_dict(row)

    oldest_pub = _fetch(
        "SELECT id, title, published_date FROM papers "
        "WHERE published_date IS NOT NULL AND published_date != '' "
        "ORDER BY published_date ASC LIMIT 1"
    )
    newest_pub = _fetch(
        "SELECT id, title, published_date FROM papers "
        "WHERE published_date IS NOT NULL AND published_date != '' "
        "ORDER BY published_date DESC LIMIT 1"
    )
    oldest_ing = _fetch(
        "SELECT id, title, ingested_at FROM papers ORDER BY ingested_at ASC LIMIT 1"
    )
    newest_ing = _fetch(
        "SELECT id, title, ingested_at FROM papers ORDER BY ingested_at DESC LIMIT 1"
    )

    total = conn.execute("SELECT COUNT(*) AS c FROM papers").fetchone()["c"]
    missing_pub = conn.execute(
        "SELECT COUNT(*) AS c FROM papers "
        "WHERE published_date IS NULL OR published_date = ''"
    ).fetchone()["c"]

    return {
        "oldest_published": oldest_pub,
        "newest_published": newest_pub,
        "oldest_ingested": oldest_ing,
        "newest_ingested": newest_ing,
        "total_papers": total,
        "missing_published_date": missing_pub,
    }


def get_poll_staleness_buckets(
    conn: sqlite3.Connection,
    now: str | None = None,
) -> dict:
    """Count non-pruned papers by how long since their last citation poll.

    The returned ``buckets`` list preserves the order defined in
    ``POLL_STALENESS_BUCKETS`` plus a leading "Never polled" entry.
    ``stale_over_week`` is the count of papers whose last poll is strictly
    older than 7 days (never-polled papers are included).
    """
    if now is None:
        now = now_utc()

    never_polled = conn.execute(
        "SELECT COUNT(*) AS c FROM papers "
        "WHERE status != 'pruned' AND last_cited_check IS NULL"
    ).fetchone()["c"]

    buckets = [{"label": "Never polled", "count": never_polled}]
    for label, lo, hi in POLL_STALENESS_BUCKETS:
        clauses = [
            "status != 'pruned'",
            "last_cited_check IS NOT NULL",
            f"(julianday(:now) - julianday(last_cited_check)) >= {lo}",
        ]
        if hi is not None:
            clauses.append(
                f"(julianday(:now) - julianday(last_cited_check)) < {hi}"
            )
        sql = "SELECT COUNT(*) AS c FROM papers WHERE " + " AND ".join(clauses)
        count = conn.execute(sql, {"now": now}).fetchone()["c"]
        buckets.append({"label": label, "count": count})

    stale_over_week = conn.execute(
        "SELECT COUNT(*) AS c FROM papers "
        "WHERE status != 'pruned' AND ("
        "last_cited_check IS NULL "
        "OR (julianday(:now) - julianday(last_cited_check)) >= 7)",
        {"now": now},
    ).fetchone()["c"]

    total = conn.execute(
        "SELECT COUNT(*) AS c FROM papers WHERE status != 'pruned'"
    ).fetchone()["c"]

    return {
        "buckets": buckets,
        "stale_over_week": stale_over_week,
        "total_non_pruned": total,
    }


def get_monthly_ingest_counts(
    conn: sqlite3.Connection, months: int = 12, today: date | None = None
) -> list[dict]:
    """Papers ingested per calendar month for the last *months* months.

    Always returns exactly *months* entries, zero-filled, ordered oldest-first
    as ``[{"month": "YYYY-MM", "count": N}, ...]``.
    """
    if today is None:
        today = date.today()

    raw = {
        row["m"]: row["c"]
        for row in conn.execute(
            "SELECT strftime('%Y-%m', ingested_at) AS m, COUNT(*) AS c "
            "FROM papers WHERE ingested_at IS NOT NULL "
            "GROUP BY m"
        ).fetchall()
    }

    out: list[dict] = []
    # Walk back month-by-month, normalizing to the first of the month.
    cursor = date(today.year, today.month, 1)
    for _ in range(months):
        key = cursor.strftime("%Y-%m")
        out.append({"month": key, "count": raw.get(key, 0)})
        # previous month
        if cursor.month == 1:
            cursor = date(cursor.year - 1, 12, 1)
        else:
            cursor = date(cursor.year, cursor.month - 1, 1)
    out.reverse()
    return out


def get_weekly_citation_updates(
    conn: sqlite3.Connection, weeks: int = 26, today: date | None = None
) -> list[dict]:
    """Citation snapshot rows per ISO week for the last *weeks* weeks.

    Always returns exactly *weeks* entries, zero-filled, ordered oldest-first
    as ``[{"week_start": "YYYY-MM-DD", "count": N}, ...]``. Weeks start on
    Monday (ISO-8601) and the key is the Monday date.
    """
    if today is None:
        today = date.today()

    raw = {
        row["w"]: row["c"]
        for row in conn.execute(
            # SQLite's strftime('%W', d) returns the Monday-based week number,
            # but to get Monday's calendar date we shift by weekday offset.
            "SELECT date(checked_at, 'weekday 0', '-6 days') AS w, "
            "COUNT(*) AS c FROM citation_snapshots GROUP BY w"
        ).fetchall()
    }

    # Monday of the current week
    this_monday = today - timedelta(days=today.weekday())
    out: list[dict] = []
    for i in range(weeks):
        wk = this_monday - timedelta(weeks=i)
        key = wk.isoformat()
        out.append({"week_start": key, "count": raw.get(key, 0)})
    out.reverse()
    return out


# ---------------------------------------------------------------------------
# Existing analytics helpers
# ---------------------------------------------------------------------------

def get_papers_by_velocity_trend(
    conn: sqlite3.Connection,
    min_velocity: float = 1.0,
) -> list[dict]:
    """Get papers with velocity above a threshold, useful for monitoring trending papers.

    Parameters
    ----------
    conn : sqlite3.Connection
    min_velocity : float
        Minimum velocity threshold (citations/month)

    Returns
    -------
    list[dict]
        Papers ordered by citation_velocity DESC
    """
    rows = conn.execute(
        """\
        SELECT id, title, authors, citation_count, citation_velocity, status, ingested_at
        FROM papers
        WHERE status IN ('active', 'promoted')
        AND citation_velocity >= ?
        ORDER BY citation_velocity DESC
        """,
        (min_velocity,),
    ).fetchall()
    return _rows_to_dicts(rows)
