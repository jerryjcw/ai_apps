# Scholar Inbox Curate — Backend Architecture

## System Overview

Scholar Inbox Curate is a personal tool that monitors academic paper recommendations from [Scholar Inbox](https://www.scholar-inbox.com/) and tracks their citation traction over time. The goal is to surface papers that are gaining real-world impact — not just high recommendation scores — so that interesting work doesn't slip through the cracks.

**Core workflow:**

1. Ingest recommended papers from Scholar Inbox (score >= 0.60).
2. Periodically poll citation counts from external APIs.
3. Compute citation velocity and flag papers gaining traction.
4. Prune stale low-citation papers; promote high-impact ones.

---

## Tech Stack

| Component        | Choice       | Rationale                                       |
|------------------|-------------|--------------------------------------------------|
| Language         | Python 3.12+ | Ecosystem for scraping, scheduling, data work   |
| Database         | SQLite       | Zero-ops, single-file, sufficient for personal use |
| Browser automation | Playwright | One-time headed login (Cloudflare Turnstile)    |
| HTTP client      | httpx        | Scholar Inbox API + citation lookups (async)    |
| Scheduler        | APScheduler  | In-process cron-like scheduling                 |
| CLI framework    | Click        | Clean CLI for manual triggers and admin tasks   |
| Config           | tomllib + python-dotenv | config.toml for settings, .env for secrets |

---

## Data Model

### `papers`

Stores each ingested paper and its current status.

```
papers
├── id              TEXT PRIMARY KEY  (Semantic Scholar paperId or DOI)
├── title           TEXT NOT NULL
├── authors         TEXT              (JSON array of author names)
├── abstract        TEXT
├── url             TEXT              (Scholar Inbox link or DOI link)
├── arxiv_id        TEXT              (nullable, for preprints)
├── venue           TEXT
├── year            INTEGER
├── scholar_inbox_score  REAL         (recommendation score 0.0-1.0)
├── doi                 TEXT              (nullable, DOI identifier)
├── category            TEXT              (Scholar Inbox topic category, e.g. "Computer Vision and Graphics")
├── published_date      TEXT              (ISO 8601, actual publication date)
├── manual_status       INTEGER DEFAULT 0 (1 if status was manually set)
├── digest_date         TEXT              (YYYY-MM-DD, date of Scholar Inbox digest)
├── status          TEXT DEFAULT 'active'  (active | promoted | pruned)
├── ingested_at     TEXT              (ISO 8601 timestamp)
├── last_cited_check TEXT             (ISO 8601 timestamp)
├── citation_count  INTEGER DEFAULT 0 (latest known total)
├── citation_velocity REAL DEFAULT 0  (citations/month, rolling 3-month)
```

### `citation_snapshots`

Time-series of citation counts for each paper, enabling velocity computation.

```
citation_snapshots
├── id              INTEGER PRIMARY KEY AUTOINCREMENT
├── paper_id        TEXT NOT NULL  → papers(id)
├── checked_at      TEXT NOT NULL  (ISO 8601 timestamp)
├── total_citations INTEGER NOT NULL
├── yearly_breakdown TEXT           (JSON object, e.g. {"2024": 12, "2025": 34})
├── source          TEXT NOT NULL   (semantic_scholar | openalex)
```

### `ingestion_runs`

Audit log for each scraping session.

```
ingestion_runs
├── id              INTEGER PRIMARY KEY AUTOINCREMENT
├── started_at      TEXT NOT NULL
├── finished_at     TEXT
├── papers_found    INTEGER DEFAULT 0
├── papers_ingested INTEGER DEFAULT 0  (new papers added)
├── status          TEXT DEFAULT 'running'  (running | completed | failed)
├── error_message   TEXT
├── digest_date     TEXT              (YYYY-MM-DD, added in V2)
```

### `scraped_dates`

Tracks which Scholar Inbox digest dates have been successfully scraped, enabling gap detection for backfill. Added in schema V2.

```
scraped_dates
├── digest_date  TEXT PRIMARY KEY     (YYYY-MM-DD)
├── scraped_at   TEXT NOT NULL        (ISO 8601 timestamp)
├── run_id       INTEGER              → ingestion_runs(id)
├── papers_found INTEGER DEFAULT 0
```

---

## Paper Ingestion Pipeline

### Scholar Inbox API (Verified Feb 2026)

Scholar Inbox exposes a **JSON REST API** at `https://api.scholar-inbox.com/api/` that the React SPA consumes. After obtaining a session cookie (see Authentication below), paper data can be fetched directly via `httpx` — **no Playwright DOM scraping needed** for the data extraction step.

Key API endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/` | GET | Today's recommended papers (digest) |
| `/api/?date=MM-DD-YYYY` | GET | Papers for a specific date |
| `/api/?from=MM-DD-YYYY&to=MM-DD-YYYY` | GET | Papers across a date range |
| `/api/session_info` | GET | Check login status, user info |
| `/api/trending` | GET | Trending papers |
| `/api/settings` | GET | User preferences |

> **Important:** Dates must use **`MM-DD-YYYY`** format. `YYYY-MM-DD` is silently ignored and returns today's data.

### Authentication Strategy

Scholar Inbox is protected by Cloudflare. The **login page embeds a Cloudflare Turnstile CAPTCHA** (`cf-turnstile-response` hidden input) that **cannot be bypassed programmatically** — headless Playwright, stealth plugins (`patchright`, `undetected-playwright`), and even real Chrome (`channel="chrome"`) with a fresh profile all fail because the Turnstile widget requires an explicit user click.

**Primary approach: Chrome cookie extraction.** Since the user is already logged into Scholar Inbox in their Chrome browser, we extract the session cookie directly from Chrome's cookie store using `browser_cookie3`. This avoids any manual browser interaction.

The `ensure_session()` fallback order:

1. **Saved cookies** — load from `data/cookies.json`. If valid, use immediately (no browser interaction).
2. **Chrome extraction** — read Chrome's cookie store via `browser_cookie3`, verify the session cookie, and save to `cookies.json` for future use. Run manually with `scholar-curate grab-session`.
3. **Playwright manual login (last resort)** — launch a headed browser for the user to solve Turnstile. Used only when Chrome has no valid cookie (e.g. after clearing browser data).

**Cookie lifecycle:** The `session` cookie on `api.scholar-inbox.com` expires ~7 days after login. When it expires, `ensure_session()` automatically tries Chrome extraction before falling back to Playwright. Multiple accesses with the same session cookie are fully supported with no rate limiting observed.

### Ingestion Flow

```
1. Load saved cookies from data/cookies.json
2. Verify session: GET /api/session_info → check is_logged_in == true
   - If expired → try Chrome cookie extraction via browser_cookie3
   - If Chrome extraction fails → trigger headed Playwright login
   - Save new cookies to data/cookies.json
3. Fetch today's papers: GET /api/
   - Or fetch a specific date: GET /api/?date=MM-DD-YYYY
   - Or fetch a date range: GET /api/?from=MM-DD-YYYY&to=MM-DD-YYYY
4. Parse JSON response:
   - Papers are in the `digest_df` array, sorted by score descending
   - Score field: `ranking_score` (float 0.0–1.0; UI shows round(score * 100))
   - Each paper includes: title, authors, abstract, arxiv_id, display_venue,
     publication_date, paper_id, semantic_scholar_id, url, and more
   - Trending papers are in a separate `trending` array (no relevance score)
5. Filter: only papers with ranking_score >= configured score_threshold (default 0.60)
6. For each new paper (not already in DB):
   a. Use semantic_scholar_id from the API response (already resolved!)
   b. Insert into `papers` table
   c. Take initial citation snapshot
7. Log results to `ingestion_runs`
```

### API Response Details

The `/api/` response includes useful metadata:

| Field | Description |
|-------|-------------|
| `digest_df` | Array of recommended papers (sorted by `ranking_score` desc) |
| `trending` | Array of trending papers (separate from recommendations) |
| `total_papers` | Total papers available for that date (e.g., 1173) |
| `has_more_papers_in_digest` | Whether more papers exist beyond the returned batch |
| `current_digest_date` | The date of this digest |
| `prev_date` / `next_date` | Adjacent dates for navigation (YYYY-MM-DD format) |
| `from_date` / `to_date` | Date range boundaries |
| `custom_digest_range` | `true` when using `from`/`to` params |
| `first_paper_id_below_decision_boundary` | Paper ID where the model's confidence drops |

Each paper in `digest_df` contains rich pre-resolved data:

| Field | Example | Notes |
|-------|---------|-------|
| `ranking_score` | `0.936` | Float 0-1, UI displays `round(score * 100)` |
| `title` | `"StoryTailor:..."` | |
| `authors` | `"Jinghao Hu, Yuhe Zhang, ..."` | Comma-separated string |
| `abstract` | Full text | |
| `arxiv_id` | `"2602.21273"` | |
| `semantic_scholar_id` | `"..."` | **Already resolved** — no separate lookup needed |
| `display_venue` | `"ArXiv 2026 (February 24)"` | |
| `paper_id` | `4596964` | Scholar Inbox internal ID |
| `url` | `"https://arxiv.org/pdf/..."` | |
| `category` | `"Computer Vision and Graphics"` | |
| `publication_date` | epoch ms | |

### Pagination / Batch Size

The API returns a capped batch per request (observed: 34-50 papers). The `has_more_papers_in_digest` flag indicates more exist, but no server-side pagination parameter was found. However, since results are sorted by `ranking_score` descending, all papers above the configured score threshold are always included in the first batch. For date ranges spanning multiple days where the 50-paper cap may truncate results, iterate day by day with `?date=`.

### Score Threshold

The default threshold of **0.60** (displayed as 60 in the Scholar Inbox UI) is configurable via `config.toml`. Papers below this score are not ingested — they represent low-relevance recommendations that would add noise.

---

## Citation Monitoring Strategy

### Age-Based Lazy Polling

Not all papers need the same polling frequency. Newer papers change faster:

| Paper age       | Poll interval |
|-----------------|---------------|
| < 3 months      | Weekly        |
| 3–12 months     | Biweekly      |
| > 12 months     | Monthly       |
| Status: pruned  | Never         |
| Status: promoted| Monthly       |

This keeps API usage low while still catching early citation spikes.

### Citation Data Sources

**Primary: Semantic Scholar Academic Graph API**

- Batch endpoint: `POST /graph/v1/paper/batch` (up to 500 papers per request)
- Fields: `citationCount`, `externalIds`
- Rate limit: 100 requests/second with API key (1 req/sec without)
- Used for: total citation count on every poll
- Budget-based polling: each cycle polls at most `poll_budget_fraction` (default 10%) of non-pruned papers, prioritized by overdue ratio to prevent starvation

**Secondary: OpenAlex API**

- Endpoint: `GET /works/{doi}` or search by title
- Used for: yearly citation breakdown (OpenAlex provides `counts_by_year`)
- Polled less frequently (monthly) since yearly granularity doesn't change fast

### Snapshot-Based Velocity Computation

After each poll, a new row is inserted into `citation_snapshots`. Velocity is computed as:

```
velocity = (citations_now - citations_3months_ago) / 3.0  # citations per month
```

If fewer than 3 months of data exist, use the available window:

```
velocity = (citations_now - citations_first) / months_elapsed
```

The computed velocity is written back to `papers.citation_velocity` for fast querying.

---

## Prune / Promote Logic

Runs after each citation poll cycle.

### Prune Rules

A paper is pruned (status → `pruned`) when **all** of these hold:

- Age since ingestion > 6 months
- Total citations < 10
- Citation velocity < 1.0 citations/month

Pruned papers are hidden from the default dashboard view and stop being polled.

### Promote Rules

A paper is promoted (status → `promoted`) when **any** of these hold:

- Total citations >= 50
- Citation velocity >= 10 citations/month (sustained over 2+ snapshots)

Promoted papers are highlighted in the UI and continue to be polled (monthly).

### Manual Override

Both prune and promote can be manually applied or reversed via CLI or the web UI settings page. Manual status changes are respected — auto-rules won't override a manually set status.

---

## Configuration

### `config.toml`

```toml
[ingestion]
score_threshold = 0.60
schedule_cron = "0 8 * * 1"       # every Monday at 8 AM

[citations]
semantic_scholar_batch_size = 100
poll_schedule_cron = "0 6 * * 3"  # every Wednesday at 6 AM

[pruning]
min_age_months = 6
min_citations = 10
min_velocity = 1.0

[promotion]
citation_threshold = 50
velocity_threshold = 10.0

[browser]
profile_dir = "data/browser_profile"
headed_fallback = true
```

### `.env`

```
SCHOLAR_INBOX_EMAIL=...
SCHOLAR_INBOX_PASSWORD=...
SEMANTIC_SCHOLAR_API_KEY=...
```

---

## Project Structure

```
scholar_inbox_curate/
├── src/
│   ├── __init__.py
│   ├── cli.py               # Click CLI entry point
│   ├── config.py             # Load config.toml + .env
│   ├── db.py                 # SQLite connection, migrations, queries
│   ├── errors.py             # Custom exception hierarchy
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── scraper.py        # Scholar Inbox API client (httpx + Playwright auth)
│   │   ├── resolver.py       # Resolve paper IDs via Semantic Scholar
│   │   ├── reresolver.py     # Re-resolve dangling papers with fallback IDs
│   │   ├── orchestrate.py    # Ingestion orchestration (shared by CLI and web)
│   │   └── backfill.py       # Gap detection, backfill, and dangling paper re-resolution
│   ├── citations/
│   │   ├── __init__.py
│   │   ├── semantic_scholar.py
│   │   ├── openalex.py
│   │   ├── velocity.py       # Velocity computation logic
│   │   └── poller.py         # Citation poll orchestration
│   ├── rules.py              # Prune/promote logic
│   ├── scheduler.py          # APScheduler setup
│   └── web/                  # FastAPI app (see frontend.md)
├── data/
│   ├── scholar_curate.db     # SQLite database
│   ├── cookies.json          # Session cookies for API access
│   └── browser_profile/      # Playwright persistent context (headed login only)
├── config.toml
├── .env
├── pyproject.toml
└── README.md
```

---

## CLI Commands

```
scholar-curate ingest            # Run paper ingestion now
scholar-curate backfill          # Scrape missed digest dates + re-resolve dangling papers
scholar-curate re-resolve        # Re-attempt S2 resolution for papers with fallback IDs
scholar-curate poll-citations    # Run citation polling now
scholar-curate collect-citations # Collect citation data for never-polled papers
scholar-curate prune             # Run prune/promote rules now
scholar-curate serve             # Start the web UI (FastAPI)
scholar-curate run               # Start scheduler (ingest + poll on cron)
scholar-curate stats             # Print DB summary (paper counts by status)
scholar-curate grab-session      # Extract session cookie from Chrome browser
scholar-curate login             # Launch headed browser for manual Turnstile auth
scholar-curate reset-session     # Delete cookies + browser profile, then re-auth
```
