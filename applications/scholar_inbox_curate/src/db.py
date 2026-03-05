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
    category            TEXT
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


# Migration functions: version_from -> callable
_MIGRATIONS: dict[int, callable] = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
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
            category
        ) VALUES (
            :id, :title, :authors, :abstract, :url, :arxiv_id, :doi, :venue, :year,
            :published_date, :scholar_inbox_score,
            :status, :manual_status, :ingested_at,
            :last_cited_check, :citation_count, :citation_velocity,
            :category
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
        conditions.append("(title LIKE ? OR authors LIKE ? OR abstract LIKE ?)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern, search_pattern])

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


def get_papers_due_for_poll(conn: sqlite3.Connection, now: str) -> list[dict]:
    """Return papers that need citation polling based on age-based schedule.

    Logic:
    - status='pruned' -> skip
    - last_cited_check is NULL -> include (never polled)
    - age < 3 months AND last check > 7 days ago -> include
    - age 3-12 months AND last check > 14 days ago -> include
    - age > 12 months AND last check > 30 days ago -> include
    - status='promoted' AND last check > 30 days ago -> include
    """
    sql = """\
        SELECT * FROM papers
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
    """
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
        conditions.append("(title LIKE ? OR authors LIKE ? OR abstract LIKE ?)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern, search_pattern])

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    row = conn.execute(
        f"SELECT COUNT(*) as cnt FROM papers {where_clause}", params
    ).fetchone()
    return row["cnt"]


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
