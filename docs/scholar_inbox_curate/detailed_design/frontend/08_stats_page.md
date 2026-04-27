# 08 — Stats Page

## Overview

The Stats page (`/stats`) is a read-only diagnostic view of the database: what papers are in it, how long since each was last polled, and how ingestion and citation-update activity has trended over time. It is the primary place to answer "is the pipeline healthy?" without needing to query SQLite directly.

**Relationship to the other pages:** the Dashboard shows a handful of forward-looking summary tiles (trending papers, next poll). The Stats page instead looks backward — at history and staleness — and is useful when debugging poll coverage, ingestion gaps, or historical data-loads. It lives in the main nav between Papers and Settings.

---

## Route

```python
@app.get("/stats")
async def stats(request: Request):
    from src.web.routes.stats import render_stats
    db_path = request.app.state.db_path
    return await render_stats(request, db_path, templates)
```

The handler in `src/web/routes/stats.py` opens a single connection and calls four analytics helpers (described below), then renders `templates/stats.html`. No query parameters — the page is a snapshot of "now".

---

## Data model

All queries are added to `src/db.py` alongside the existing dashboard analytics. They are pure read-only and never mutate state.

### 1. `get_paper_date_range(conn) -> dict`

Returns the paper with the oldest/newest `published_date` (NULLs excluded), plus the oldest/newest `ingested_at`. Each nested row carries `id`, `title`, and the relevant date so the template can link to the paper detail page. Also returns `total_papers` and `missing_published_date` to contextualize the range.

Why two kinds of range: `published_date` is the intuitive "paper age," but some Scholar Inbox entries arrive without one. `ingested_at` always exists and describes when the DB itself started tracking the paper — useful for verifying the merge of the old DB or a long gap in ingestion.

### 2. `get_poll_staleness_buckets(conn, now=None) -> dict`

Buckets non-pruned papers by `(now - last_cited_check)` into exclusive ranges defined in `POLL_STALENESS_BUCKETS`:

| Label        | Range (days)     |
|--------------|------------------|
| Never polled | `last_cited_check IS NULL` |
| < 1 week     | 0 ≤ age < 7      |
| 1–2 weeks    | 7 ≤ age < 14     |
| 2–4 weeks    | 14 ≤ age < 28    |
| 4–8 weeks    | 28 ≤ age < 56    |
| 8+ weeks     | 56 ≤ age         |

Returns `{buckets, stale_over_week, total_non_pruned}`. `stale_over_week` is the single headline number — how many papers need attention — and includes both "never polled" and any bucket ≥ 7 days. A seven-day boundary is deliberate: papers polled exactly seven days ago count as stale (≥ 7), matching the weekly poll cadence.

The `now` argument is optional — callers use it in tests to pin the current time; production passes `None` and the query uses `now_utc()` internally.

### 3. `get_monthly_ingest_counts(conn, months=12, today=None) -> list[dict]`

Groups `papers.ingested_at` by `strftime('%Y-%m', ...)` and zero-fills any month in the window that had no ingestions. Always returns exactly `months` rows, oldest-first as `[{"month": "YYYY-MM", "count": N}, ...]`. The zero-fill is done in Python rather than SQL so the series is guaranteed dense regardless of gaps in the data.

### 4. `get_weekly_citation_updates(conn, weeks=26, today=None) -> list[dict]`

Counts rows in `citation_snapshots` per ISO week (Monday-starting). The SQL expression `date(checked_at, 'weekday 0', '-6 days')` normalizes each snapshot's timestamp to the Monday of its week. Same zero-fill behavior as the monthly series: always exactly `weeks` entries, oldest-first, with `"week_start"` as the Monday date in ISO format.

26 weeks is a reasonable default window — wide enough to see a half-year of trend, narrow enough to fit legibly in a ~580px chart.

---

## Template layout

`templates/stats.html` has three sections, in order of decreasing emphasis:

1. **Paper date coverage.** Two hero cards (`.stat-card`) side-by-side with the oldest/newest `published_date` as the large value and the paper title linking to its detail page. Below them, a four-up mini-stat row shows tracking window and paper totals.

2. **Last poll freshness.** One lede sentence (`X of Y non-pruned papers haven't been polled in the past week.`) — the primary signal — followed by a Chart.js bar chart keyed off the bucket array, and a distribution table with gradient progress bars (`.bar-cell`/`.bar-fill`) showing each bucket's share.

3. **Ingestion & citation activity.** A two-column grid (`.stats-twocol`): monthly ingestion counts as a bar chart on the left, weekly citation updates as a filled line chart on the right. The grid collapses to one column below 900px.

All chart data is serialized with `| tojson` into JS constants inside `{% block extra_scripts %}`, then consumed by a single IIFE that instantiates the three Chart.js charts. A shared `baseOpts` object and `palette` keep all three charts visually consistent and respect the light/dark color scheme.

### Styling

Stats-specific styles live in `src/web/static/style.css` under `/* --- Stats Page --- */`. Highlights:

- `.stat-card` — elevated surface with a subtle `translateY(-2px)` hover lift. Uses tabular numerals (`font-variant-numeric: tabular-nums`) for the date value so row heights don't shift.
- `.stat-mini` — smaller sibling for the secondary stat row.
- `.stats-chart` — fixed 260px height wrapper so Chart.js `responsive: true, maintainAspectRatio: false` behaves.
- `.bar-cell` / `.bar-fill` — inline progress bars in the distribution table. The fill uses a linear gradient and is rendered as a flex child with an explicit width percentage.
- `.stats-twocol` — grid with responsive collapse to single column at ≤900px.

All colors come from CSS variables that Pico defines; the only hard-coded colors are the accent gradients (`#3b82f6 → #8b5cf6`) and chart palette (blue for pipeline data, violet for citation data, amber for "needs attention" states on the poll chart).

---

## Testing

Tests live in `tests/scholar_inbox_curate/web/test_stats.py` and cover three layers:

- **DB helpers** — bucket boundaries (including the 7-day edge case), zero-fill length, pruned-paper exclusion, empty-database behavior.
- **Route/template** — HTTP 200, title and section headers present, all three canvas IDs present once data exists, chart data serialized as JSON into the JS block.
- **Empty state** — dash fallback in hero cards, "No non-pruned papers to poll" message.

The fixtures mirror the existing `test_dashboard.py` setup (tmp SQLite DB + `TestClient`) so the tests run independent of any real data.
