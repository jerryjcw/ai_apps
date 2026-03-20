# 02 — Scholar Inbox Scraper

## Overview

The scraper fetches recommended paper data from Scholar Inbox's JSON REST API. Authentication requires a one-time manual login via Playwright (due to Cloudflare Turnstile CAPTCHA), after which the session cookie enables direct API access with `httpx` — no browser automation needed for data extraction.

> **Verified as of Feb 2026.** Scholar Inbox is a **React / Material UI (MUI) single-page application** backed by a JSON API at `api.scholar-inbox.com`. All API details, field names, and date formats below have been confirmed against the live site.

---

## Module: `src/ingestion/scraper.py`

### Public Interface

```python
async def scrape_recommendations(
    config: AppConfig,
    date: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[RawPaper]:
    """Fetch recommended papers from Scholar Inbox API.

    Args:
        config: App configuration with credentials and thresholds.
        date: Optional specific date in MM-DD-YYYY format.
        from_date: Optional range start in MM-DD-YYYY format.
        to_date: Optional range end in MM-DD-YYYY format.

    If no date args are given, fetches today's digest.
    Returns papers above the configured score threshold.

    The score_threshold in config is already on the 0.0-1.0 decimal scale,
    matching the API's ranking_score directly. No conversion needed.
    """
```

### `RawPaper` Data Class

```python
from dataclasses import dataclass

@dataclass
class RawPaper:
    """A paper as returned by the Scholar Inbox API, lightly parsed."""
    title: str
    authors: list[str]
    abstract: str
    score: float                           # ranking_score from API (0.0-1.0)
    arxiv_id: str | None = None            # From API response
    semantic_scholar_id: str | None = None  # Already resolved by Scholar Inbox
    paper_id: int | None = None            # Scholar Inbox internal ID
    venue: str | None = None
    year: int | None = None
    category: str | None = None
    scholar_inbox_url: str | None = None   # URL to paper PDF
    publication_date: str | None = None    # ISO 8601 (converted from epoch ms)
```

---

## Scholar Inbox API (Verified)

### Base URL

```
https://api.scholar-inbox.com
```

### Authentication

All API calls require a `session` cookie. Send it as:
```
Cookie: session=<value>
```

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/` | GET | Today's recommended papers (digest) |
| `/api/?date=MM-DD-YYYY` | GET | Papers for a specific date |
| `/api/?from=MM-DD-YYYY&to=MM-DD-YYYY` | GET | Papers across a date range |
| `/api/session_info` | GET | Check login status, user info |
| `/api/trending` | GET | Trending papers (popular across all users) |
| `/api/settings` | GET | User preferences |
| `/api/catchup_info` | GET | Catch-up date range info |
| `/api/maintenance_info` | GET | Maintenance status |

### Date Format

> **Critical:** Dates must use **`MM-DD-YYYY`** format (e.g., `02-25-2026`).
> `YYYY-MM-DD` format is **silently ignored** and the API returns today's data instead.

### Single Date Query

```
GET /api/?date=02-25-2026
```

Returns the digest for a specific date. The response includes `prev_date` and `next_date` fields (in `YYYY-MM-DD` format, confusingly) for sequential navigation.

### Date Range Query

```
GET /api/?from=01-14-2026&to=01-15-2026
```

Returns papers across the specified date range. The response sets `custom_digest_range: true` and `from_date`/`to_date` reflect the requested range.

### Digest Response Structure

```json
{
  "success": true,
  "current_digest_date": "2026-02-26",
  "custom_digest_range": false,
  "from_date": "Thu, 26 Feb 2026 00:00:00 GMT",
  "to_date": "Thu, 26 Feb 2026 00:00:00 GMT",
  "prev_date": "2026-02-25",
  "next_date": "2026-02-27",
  "display_next_date": false,
  "total_papers": 1173,
  "has_more_papers_in_digest": false,
  "first_paper_id_below_decision_boundary": 4594523,
  "digest_df": [ ... ],
  "trending": [ ... ],
  "read_paper_ids": [],
  "username": "Jerry Wu"
}
```

### Paper Object Structure

Each paper in the `digest_df` array:

```json
{
  "paper_id": 4596964,
  "title": "StoryTailor: A Zero-Shot Pipeline for ...",
  "authors": "Jinghao Hu, Yuhe Zhang, GuoHua Geng, Kang Li, Han Zhang",
  "abstract": "Generating multi-frame, action-rich ...",
  "ranking_score": 0.936284534,
  "arxiv_id": "2602.21273",
  "semantic_scholar_id": "...",
  "url": "https://arxiv.org/pdf/2602.21273",
  "display_venue": "ArXiv 2026 (February 24)",
  "category": "Computer Vision and Graphics",
  "publication_date": 1772064000000,
  "affiliations": ["School of Computing, Northwest University"],
  "citations": null,
  "bookmarked": 0,
  "rating": null,
  "read": false,
  "recommended": true,
  "has_ranking": true,
  "n_positive_ratings": 0,
  "n_negative_ratings": 0,
  "total_likes": 0,
  "total_read": 11,
  "cache_file_name": "Hu2026ARXIV_StoryTailor_A_Zero_Shot.pdf",
  "first_page_image": {"imageUrl": "/first_pages/4596964.jpeg"},
  "html_link": "https://arxiv.org/html/2602.21273",
  "keywords_metadata": ["..."],
  "summaries": null
}
```

Key fields for ingestion:

| Field | Type | Notes |
|-------|------|-------|
| `ranking_score` | float | 0.0–1.0. The UI displays `round(score * 100)` as an integer. |
| `title` | string | Paper title |
| `authors` | string | Comma-separated author names |
| `abstract` | string | Full abstract text |
| `arxiv_id` | string\|null | arXiv identifier (e.g., `"2602.21273"`) |
| `semantic_scholar_id` | string\|null | **Already resolved** — no separate Semantic Scholar lookup needed |
| `paper_id` | int | Scholar Inbox internal ID |
| `display_venue` | string | e.g., `"ArXiv 2026 (February 24)"` |
| `category` | string | e.g., `"Computer Vision and Graphics"` |
| `url` | string | Direct link to paper PDF |
| `publication_date` | int | Epoch milliseconds |

### Trending Response Structure

```
GET /api/trending
```

Returns `{"success": true, "digest_df": [...], "categories": [...], "has_next": bool}`.
Trending papers are popular across all users (not personalized) and have no `ranking_score`.

### Pagination / Batch Size

The API returns a **capped batch** per request (observed: 34–50 papers depending on the date). The `has_more_papers_in_digest` field indicates more exist beyond the returned batch.

**No server-side pagination parameter was found** — standard params like `page`, `offset`, `limit`, `n_papers` were all tested and had no effect.

However, this is not a problem for ingestion because:
- Results are sorted by `ranking_score` **descending**
- All papers above the configured score threshold are included in the first batch
- For wide date ranges where the 50-paper cap truncates results, iterate day by day using `?date=` instead

### Session Info

```
GET /api/session_info
```

```json
{
  "is_logged_in": true,
  "name": "Jerry Wu",
  "user_id": 31500,
  "sha_key": "...",
  "onboarding_status": "finished"
}
```

Use this to verify session validity before fetching papers.

---

## Authentication & Cloudflare Strategy

### Turnstile Cannot Be Bypassed Programmatically

Scholar Inbox's login page embeds a Cloudflare Turnstile CAPTCHA that **requires explicit user interaction** (clicking the widget). The following automated bypass approaches were tested and **all failed**:

| Approach | Result |
|----------|--------|
| Playwright headless | Turnstile `cf-turnstile-response` field stays empty |
| Playwright headed (bundled Chromium) | Turnstile field stays empty |
| `patchright` headless (stealth Playwright fork) | Turnstile field stays empty |
| `patchright` headed | Turnstile field stays empty |
| Real Chrome via `channel="chrome"` (headed, fresh profile) | Turnstile field stays empty |
| `browser_cookie3` (read Chrome cookie store) | Works but requires macOS Keychain access — grants broad access to all browser cookies, unacceptable security risk |

The Turnstile widget specifically requires a user click to solve, regardless of browser fingerprint or stealth measures. This is by design — Turnstile's "managed challenge" mode uses interaction signals (mouse movement, click) as proof of humanity.

### Chosen Approach: One-Time Headed Login + Cookie Reuse

The most practical approach is a **two-phase workflow**:

**Phase 1 — Manual Login (headed, ~weekly)**
1. Launch Playwright in headed mode (`headless=False`).
2. Navigate to `/login`.
3. Pre-fill credentials (email into `input[type="text"]`, password into `input[type="password"]`).
4. Prompt the user to click the Turnstile checkbox and submit (~10 seconds).
5. Wait for URL to change away from `/login` (indicates successful login).
6. Save all cookies to `data/cookies.json`.
7. Close the browser.

**Phase 2 — API Access (automated, repeatable)**
1. Load the `session` cookie value from `data/cookies.json`.
2. Verify session: `GET /api/session_info` with `Cookie: session=<value>`.
3. If `is_logged_in` is `true` → proceed with `httpx` API calls (no browser needed).
4. If not → trigger Phase 1 again.

### Session Cookie Details (Verified)

| Cookie | Domain | Expires | Required for API? |
|--------|--------|---------|-------------------|
| `session` | `api.scholar-inbox.com` | **~7 days** after login | **Yes** — the only cookie needed |
| `_cfuvid` | `.challenges.cloudflare.com` | Session (browser close) | No — only for browser-based access |

### Multiple Access / Rate Limiting

- **Multiple sequential requests** with the same session cookie work without issues.
- **No rate limiting** was observed during testing (5 rapid requests in sequence all succeeded).
- The session cookie supports **concurrent access** — no single-use or nonce-based restrictions.

### Login Page Structure (Verified)

The login page at `https://www.scholar-inbox.com/login` contains:

| Element | Selector | Notes |
|---------|----------|-------|
| Email/username field | `input[type="text"]` | **Not** `type="email"` — it's a plain text input |
| Password field | `input[type="password"]` | Standard password input |
| Turnstile hidden field | `input[type="hidden"][name="cf-turnstile-response"]` | Auto-populated when user clicks the Turnstile widget |
| Submit button | `button[type="submit"]` | Also matches `button:has-text("Log")` |

### Headed Login Flow

```python
async def _manual_login(config: AppConfig) -> list[dict]:
    """Open a headed browser for manual login. Return cookies on success.

    Pre-fills credentials so the user only needs to:
    1. Click the Turnstile checkbox
    2. Click the submit button
    Takes ~10 seconds of manual interaction.
    """
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir=config.browser.profile_dir,
        headless=False,
        viewport={"width": 1280, "height": 720},
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto("https://www.scholar-inbox.com/login",
                    wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(3)

    # Pre-fill credentials
    await page.fill('input[type="text"]', config.secrets.scholar_inbox_email)
    await page.fill('input[type="password"]', config.secrets.scholar_inbox_password)

    # Wait for user to complete Turnstile and submit
    logger.info("Please click the Turnstile checkbox and submit the login form.")
    for _ in range(90):  # 3-minute timeout
        await asyncio.sleep(2)
        if "/login" not in page.url:
            break
    else:
        raise CloudflareTimeoutError("Login not completed within timeout")

    cookies = await ctx.cookies()
    await ctx.close()
    await pw.stop()
    return cookies
```

---

## Data Extraction (API-Based)

### Fetching Papers

Since the API returns structured JSON, extraction is straightforward:

```python
import httpx

async def _fetch_papers(
    session_cookie: str,
    date: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    """Fetch paper digest from Scholar Inbox API.

    Args:
        session_cookie: Value of the 'session' cookie.
        date: Single date in MM-DD-YYYY format.
        from_date: Range start in MM-DD-YYYY format.
        to_date: Range end in MM-DD-YYYY format.

    Returns the full API response as a dict.
    """
    headers = {"Cookie": f"session={session_cookie}"}
    params = {}
    if date:
        params["date"] = date       # MM-DD-YYYY
    elif from_date and to_date:
        params["from"] = from_date  # MM-DD-YYYY
        params["to"] = to_date      # MM-DD-YYYY

    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        resp = await client.get(
            "https://api.scholar-inbox.com/api/",
            params=params,
        )
        resp.raise_for_status()
        return resp.json()
```

### Parsing Papers

```python
def _parse_papers(data: dict, score_threshold: float = 0.60) -> list[RawPaper]:
    """Parse API response into RawPaper objects, filtering by score.

    Args:
        data: Full API response from /api/.
        score_threshold: Minimum ranking_score (0.0-1.0 decimal scale).
                         Default 0.60 (matches config.ingestion.score_threshold).
    """
    papers = []
    for p in data.get("digest_df", []):
        score = p.get("ranking_score") or 0.0
        if score < score_threshold:
            continue  # sorted desc, so we could break, but continue for safety

        papers.append(RawPaper(
            title=p["title"],
            authors=[a.strip() for a in p.get("authors", "").split(",")],
            abstract=p.get("abstract", ""),
            score=score,
            scholar_inbox_url=p.get("url", ""),
            arxiv_id=p.get("arxiv_id"),
            semantic_scholar_id=p.get("semantic_scholar_id"),
            paper_id=p["paper_id"],
            venue=p.get("display_venue"),
            year=_extract_year(p.get("display_venue", "")),
            category=p.get("category"),
        ))
    return papers
```

### Iterating Over a Date Range

For multi-day ingestion (e.g., catching up on missed days), iterate day by day to avoid the 50-paper batch cap on date range queries:

```python
from datetime import date, timedelta

async def _fetch_date_range(
    session_cookie: str,
    start: date,
    end: date,
    score_threshold: float = 0.60,
) -> list[RawPaper]:
    """Fetch papers for each day in a date range.

    Iterates day by day to ensure all high-scoring papers are captured,
    since the API caps each response at ~50 papers.
    """
    all_papers = []
    current = start
    while current <= end:
        date_str = current.strftime("%m-%d-%Y")  # MM-DD-YYYY
        data = await _fetch_papers(session_cookie, date=date_str)
        papers = _parse_papers(data, score_threshold)
        all_papers.extend(papers)
        current += timedelta(days=1)
    return all_papers
```

Alternatively, for quick overviews where the 50-paper cap is acceptable:

```python
# Fetch a date range in a single call
data = await _fetch_papers(cookie, from_date="01-14-2026", to_date="01-15-2026")
```

---

## Backfill & Gap Detection

### Problem

The scraper runs on a schedule (default: Monday 8 AM) or on-demand. If the scheduler misses a run — system was off, network down, cookie expired — papers from those dates are lost silently. There is no mechanism to detect or recover missed days.

### Solution: `scraped_dates` Table + On-Demand Backfill

A dedicated `scraped_dates` table (see [01 — Database Layer](01_database_layer.md)) tracks which calendar digest dates have been successfully scraped. A backfill function compares this table against a lookback window to identify gaps and re-scrape them.

### Module: `src/ingestion/backfill.py`

```python
@dataclass
class BackfillResult:
    dates_checked: int       # total missing dates identified
    dates_scraped: int       # dates successfully scraped
    papers_found: int        # total papers above threshold
    papers_new: int          # papers not already in DB
    errors: list[str]        # per-date errors (non-fatal)


async def run_backfill(
    config: AppConfig,
    lookback_days: int | None = None,
    score_threshold: float | None = None,
) -> BackfillResult:
    """Identify missed digest dates and scrape them.

    Args:
        config: App configuration.
        lookback_days: Override for config.ingestion.backfill_lookback_days.
        score_threshold: Override for config.ingestion.backfill_score_threshold.

    Steps:
        1. Query scraped_dates table to find gaps within the lookback window.
        2. For each missing date, call scrape_date() with the backfill threshold.
        3. Record each successfully scraped date in scraped_dates.
        4. Track one ingestion_run for the overall backfill invocation.
        5. Continue on per-date errors (log + collect), don't abort.
    """
```

### `scrape_date()` — Single-Date Scraping

A thin wrapper in `src/ingestion/scraper.py` used by both regular ingestion and backfill:

```python
async def scrape_date(
    config,
    date: str,
    score_threshold: float | None = None,
) -> list[RawPaper]:
    """Scrape a single digest date.

    Args:
        config: App configuration.
        date: Digest date in YYYY-MM-DD format (converted to MM-DD-YYYY for API).
        score_threshold: Override (0.0-1.0); defaults to config.ingestion.score_threshold.
    """
```

### Why Day-by-Day Iteration?

The Scholar Inbox API caps each response at ~50 papers (see [Pagination / Batch Size](#pagination--batch-size)). Results are sorted by `ranking_score` descending, so the top papers are always returned, but for a date range query spanning multiple days the cap can truncate results. Iterating day-by-day ensures all papers above threshold are captured for each date.

A 1-second delay between requests avoids overwhelming the API.

### Relationship with Regular Ingestion

When `scrape_recommendations()` completes successfully (via the `ingest` CLI command or scheduler), it should also call `record_scraped_date()` to mark that date as covered. This way, backfill won't re-scrape dates that were already handled by normal ingestion.

### Configuration

Two new fields in `IngestionConfig` (see [00 — Project Setup](00_project_setup_and_configuration.md)):

| Field | Default | Description |
|-------|---------|-------------|
| `backfill_score_threshold` | 0.60 | Score threshold (0.0-1.0) used during backfill |
| `backfill_lookback_days` | 30 | How far back to search for missed dates |

The primary `score_threshold` also defaults to **0.60** to cast a wider net.

### CLI

```
$ scholar-curate backfill --help
Usage: scholar-curate backfill [OPTIONS]

  Scrape missed digest dates within the lookback window.

Options:
  --lookback INTEGER   Days to look back (default: from config)
  --threshold FLOAT    Score threshold override (0.0-1.0)
  --help               Show this message and exit.
```

---

## DOM Scraping (Fallback)

The DOM scraping approach documented below is kept as a **fallback** in case the API changes or becomes inaccessible. The API-based approach above is strongly preferred.

### SPA Navigation Constraints

- `wait_until="networkidle"` does **not** work (SPA keeps connections open; always times out).
- Use `wait_until="domcontentloaded"` + 3-5s delay for React to render.
- After login, the app redirects to `/home`.

### DOM Structure (Verified)

Each paper card is wrapped in `<div data-lazy-paper-digest-index="N">`. Within each card:

| Data | Selector | Notes |
|------|----------|-------|
| Score | `div[aria-label="Relevance"]` | Integer text (e.g., "87"). Absent for trending papers. |
| Title | `h3 a` | Title text + href to paper detail |
| Authors | `h3`'s next sibling | Comma-separated, may be truncated |
| Abstract | First text block > 200 chars | |
| arXiv link | `a[href*="arxiv.org"]` | |

The page also contains a `react-daterange-picker` widget for date range selection and `keyboard_arrow_left` / `keyboard_arrow_right` buttons for day-by-day navigation.

---

## Error Handling

All scraper exceptions are defined in `src/errors.py` (see [08 — Error Handling](08_error_handling_and_resilience.md)):

```python
from src.errors import ScraperError, CloudflareTimeoutError, LoginError, SessionExpiredError, APIError
```

The top-level `scrape_recommendations()` catches these and logs them, then records the failure in `ingestion_runs`.

---

## Session Reset

When cookies become stale, the `scholar-curate reset-session` CLI command deletes saved cookies and the browser profile directory, forcing a fresh headed login on the next run.

```python
def reset_browser_session(config: AppConfig):
    """Delete cookies and browser profile to force re-authentication."""
    import shutil

    cookie_file = Path(config.db_path).parent / "cookies.json"
    if cookie_file.exists():
        cookie_file.unlink()
        logger.info("Cookies deleted: %s", cookie_file)

    profile_dir = Path(config.browser.profile_dir)
    if profile_dir.exists():
        shutil.rmtree(profile_dir)
        logger.info("Browser profile deleted: %s", profile_dir)
```
