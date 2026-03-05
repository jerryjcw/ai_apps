# Scholar Inbox Curate — Frontend Architecture

## Overview

The frontend is a lightweight server-rendered web UI for browsing tracked papers, viewing citation trends, and managing system settings. It prioritizes simplicity — no build step, no SPA framework, no JavaScript bundling.

---

## Tech Stack

| Component   | Choice          | Rationale                                        |
|-------------|----------------|--------------------------------------------------|
| Web framework | FastAPI       | Already used for the backend; async, fast        |
| Templating  | Jinja2          | Built-in FastAPI support, mature, simple         |
| Interactivity | HTMX         | Dynamic updates without writing JavaScript       |
| Charts      | Chart.js        | Lightweight, works with vanilla `<canvas>` tags  |
| CSS         | Pico CSS (classless) | Minimal styling with zero configuration    |

**No build tools.** All frontend assets are served statically or via CDN links. The entire UI is a set of Jinja2 templates with HTMX attributes for interactivity.

---

## Routes

```
GET  /                        → Dashboard (redirect to /dashboard)
GET  /dashboard               → Summary cards + top papers
GET  /papers                  → Paper list (filterable table)
GET  /papers/{paper_id}       → Paper detail view
GET  /settings                → Configuration and manual triggers

# HTMX partial endpoints (return HTML fragments)
GET  /partials/paper-rows     → Filtered/sorted table rows
POST /partials/trigger-ingest → Trigger ingestion, return status
POST /partials/trigger-poll   → Trigger citation poll, return status
POST /partials/trigger-rules  → Trigger prune/promote rules, return status
POST /partials/trigger-backfill → Trigger backfill of missed dates, return status
POST /partials/trigger-collect  → Trigger citation collection for unpolled papers, return status
POST /papers/{id}/status      → Update paper status (promote/prune/restore)
```

---

## Views

### 1. Dashboard (`/dashboard`)

The landing page. Provides a quick overview of the paper collection and surfaces the most interesting items.

**Summary Cards (top row):**

| Card              | Content                        |
|-------------------|--------------------------------|
| Total Papers      | Count of active + promoted     |
| Trending          | Papers with velocity > 5/month |
| Recently Ingested | Papers added in last 7 days    |
| Next Poll         | Scheduled time of next citation check |

**Top Papers by Velocity (main section):**

A table showing the top 10 papers ranked by `citation_velocity`, displaying:

- Title (links to detail view)
- Authors (truncated)
- Citation count
- Velocity (citations/month)
- Sparkline or small trend indicator

**Recent Activity (sidebar or below):**

- Last 5 ingestion runs with status and paper counts
- Last citation poll timestamp

---

### 2. Paper List (`/papers`)

A full table of all tracked papers with filtering and sorting.

**Columns:**

| Column          | Sortable | Notes                          |
|-----------------|----------|--------------------------------|
| Title           | Yes      | Links to detail view           |
| Authors         | No       | First author + "et al."        |
| Year            | Yes      |                                |
| Score           | Yes      | Scholar Inbox recommendation   |
| Citations       | Yes      | Latest total                   |
| Velocity        | Yes      | Citations/month                |
| Status          | No       | Badge: active / promoted / pruned |
| Ingested        | Yes      | Relative date ("3 days ago")   |

**Filters (above table):**

- **Status**: dropdown — All / Active / Promoted / Pruned
- **Score range**: min/max inputs
- **Search**: text input matching title/author

**HTMX behavior:**

- Filter/sort changes trigger `hx-get="/partials/paper-rows"` to swap the table body without full page reload.
- Default sort: velocity descending.

---

### 3. Paper Detail (`/papers/{paper_id}`)

Full information about a single paper plus its citation history.

**Header section:**

- Title
- Authors (full list)
- Venue, year
- Scholar Inbox score (with color indicator)
- Status badge with action buttons:
  - Active paper → [Promote] [Prune]
  - Pruned paper → [Restore]
  - Promoted paper → [Demote to Active]
- External links: Scholar Inbox page, Semantic Scholar, DOI

**Citation History Chart:**

A Chart.js line chart showing citation count over time, built from `citation_snapshots`.

- X-axis: date
- Y-axis: total citations
- Tooltip: exact count and date
- If yearly breakdown data is available, show a stacked bar chart overlay for per-year contributions.

**Stats sidebar:**

| Stat               | Value                           |
|--------------------|---------------------------------|
| Current citations  | 142                             |
| Velocity           | 8.3 / month                     |
| First tracked      | 2025-09-15                      |
| Last checked       | 2026-02-24                      |
| Snapshots          | 12                              |

**Citation Snapshots Table (collapsible):**

Raw snapshot data for debugging/verification:

| Date       | Total | Source           | Yearly Breakdown     |
|------------|-------|------------------|----------------------|
| 2026-02-24 | 142   | semantic_scholar | {"2025": 89, "2026": 53} |
| 2026-02-10 | 134   | semantic_scholar | —                    |
| ...        | ...   | ...              | ...                  |

---

### 4. Settings (`/settings`)

System configuration and manual controls.

**Configuration Display:**

Shows current values from `config.toml` (read-only in v1):

- Ingestion score threshold
- Poll intervals and cron schedules
- Prune/promote thresholds
- Browser profile path

**Manual Triggers:**

Buttons that fire HTMX POST requests and show inline status:

| Action           | Endpoint                   | Feedback                    |
|------------------|----------------------------|-----------------------------|
| Run Ingestion    | POST /partials/trigger-ingest | "Running..." → "Done. 5 new papers." |
| Poll Citations   | POST /partials/trigger-poll   | "Running..." → "Done. 42 papers updated." |
| Run Prune/Promote | POST /partials/trigger-rules | "Running..." → "Pruned 3, promoted 1." |
| Run Backfill    | POST /partials/trigger-backfill | "Running..." → "Backfilled 5 dates, 12 new papers." |
| Collect Citations | POST /partials/trigger-collect | "Running..." → "Collected citations for 8 papers." |

**Ingestion Run History:**

Table of recent `ingestion_runs`:

| Started          | Duration | Papers Found | Ingested | Status    |
|------------------|----------|-------------|----------|-----------|
| 2026-02-24 08:00 | 45s      | 28          | 5        | completed |
| 2026-02-17 08:00 | 38s      | 22          | 3        | completed |
| 2026-02-10 08:01 | 12s      | 0           | 0        | failed    |

---

## Template Structure

```
src/web/
├── app.py                  # FastAPI app, route definitions
├── templates/
│   ├── base.html           # Layout: head, nav, footer, HTMX/Chart.js CDN links
│   ├── dashboard.html
│   ├── papers/
│   │   ├── list.html
│   │   ├── detail.html
│   │   └── _rows.html      # HTMX partial: table rows only
│   ├── settings.html
│   └── components/
│       ├── _summary_card.html
│       ├── _paper_table.html
│       ├── _citation_chart.html
│       └── _status_badge.html
└── static/
    └── style.css           # Minimal overrides on top of Pico CSS
```

---

## HTMX Patterns

### Table Filtering

```html
<input type="search" name="q"
       hx-get="/partials/paper-rows"
       hx-trigger="keyup changed delay:300ms"
       hx-target="#paper-table-body"
       hx-include="[name='status'],[name='sort']" />
```

### Manual Trigger with Status Feedback

```html
<button hx-post="/partials/trigger-ingest"
        hx-target="#ingest-status"
        hx-indicator="#ingest-spinner">
  Run Ingestion
</button>
<span id="ingest-spinner" class="htmx-indicator">Running...</span>
<span id="ingest-status"></span>
```

### Status Update on Paper Detail

```html
<button hx-post="/papers/abc123/status"
        hx-vals='{"status": "promoted"}'
        hx-target="#status-section"
        hx-swap="outerHTML">
  Promote
</button>
```

---

## Chart.js Integration

Citation history charts are rendered on the paper detail page. Data is embedded in the template as a JSON script block to avoid an extra API call:

```html
<script>
  const snapshots = {{ snapshots_json | safe }};
  new Chart(document.getElementById('citationChart'), {
    type: 'line',
    data: {
      labels: snapshots.map(s => s.date),
      datasets: [{
        label: 'Total Citations',
        data: snapshots.map(s => s.total),
        borderColor: '#3b82f6',
        tension: 0.3
      }]
    },
    options: {
      responsive: true,
      scales: { y: { beginAtZero: true } }
    }
  });
</script>
```
