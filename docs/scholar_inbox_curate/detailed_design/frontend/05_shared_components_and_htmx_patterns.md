# 05 — Shared Components & HTMX Patterns

## Overview

This document defines all reusable Jinja2 component templates (partials), custom Jinja2 filters, HTMX interaction patterns used across multiple pages, and global JavaScript utilities. These shared building blocks ensure consistency and avoid template duplication.

---

## Component Templates

All components live in `src/web/templates/components/` and are prefixed with `_` to indicate they are includes/partials, not standalone pages.

### `_summary_card.html`

**Path:** `src/web/templates/components/_summary_card.html`

**Usage:** Dashboard summary cards.

**Expected variables** (set via `{% with %}`):

| Variable | Type | Description |
|----------|------|-------------|
| `card_label` | `str` | The metric label (e.g., "Papers Tracked") |
| `card_value` | `str \| int` | The metric value (e.g., 42 or "Every Monday at 08:00") |

**Markup:**

```html
<article aria-label="{{ card_label }}">
    <header>{{ card_label }}</header>
    <p class="card-value">{{ card_value }}</p>
</article>
```

**Usage in templates:**

```html
{% with card_label="Papers Tracked", card_value=total_papers %}
    {% include "components/_summary_card.html" %}
{% endwith %}
```

**Styling:** See doc 06 for `.card-value` CSS.

---

### `_status_badge.html`

**Path:** `src/web/templates/components/_status_badge.html`

**Usage:** Everywhere a paper status is displayed (paper list table, detail page, dashboard table).

**Expected variable:**

| Variable | Type | Description |
|----------|------|-------------|
| `status` | `str` | One of: `"active"`, `"promoted"`, `"pruned"` |

**Markup:**

```html
<mark class="status-{{ status }}">{{ status|capitalize }}</mark>
```

Pico CSS provides base `<mark>` styling. Custom CSS adds status-specific background colors (see doc 06).

---

### `_status_section.html`

**Path:** `src/web/templates/components/_status_section.html`

**Usage:** Paper detail page. Also returned as the HTMX response for `POST /papers/{id}/status`.

**Expected variable:**

| Variable | Type | Description |
|----------|------|-------------|
| `paper` | `dict` | Full paper row (needs `id`, `status`, `manual_status`) |

**Full markup:** See doc 03 for the complete template including action buttons and HTMX attributes.

**Key attribute:** `id="status-section"` — serves as the HTMX swap target.

---

### `_citation_chart.html`

**Path:** `src/web/templates/components/_citation_chart.html`

**Usage:** Paper detail page.

**Expected variables:**

| Variable | Type | Description |
|----------|------|-------------|
| `snapshots_json` | `str` | JSON-serialized array for Chart.js |
| `snapshot_count` | `int` | Number of snapshots |
| `snapshots` | `list[dict]` | Raw snapshot data (for screen reader text) |

**Behavior:**

- >= 2 snapshots: renders `<canvas>` for Chart.js.
- 1 snapshot: shows static citation count text.
- 0 snapshots: shows "No citation data yet" message.

**Full markup:** See doc 03 for the complete template.

---

### `_paper_table.html` (Optional)

**Path:** `src/web/templates/components/_paper_table.html`

**Usage:** Could be used by both the dashboard (simplified) and paper list (full). However, since the two tables differ significantly (dashboard has fewer columns, no sorting, no pagination), it may be simpler to keep them as separate inline markup in each page template.

**Recommendation for v1:** Skip this component. Inline the table markup in `dashboard.html` and `papers/list.html` respectively. Extract into a shared component only if duplication becomes a maintenance burden.

---

## Custom Jinja2 Filters

All filters are defined in `src/web/filters.py` and registered on the Jinja2 environment in `app.py`.

### Registration

```python
# In src/web/app.py
from src.web.filters import relative_date, first_author, format_duration, cron_human, from_json

def _register_filters(templates: Jinja2Templates):
    templates.env.filters["relative_date"] = relative_date
    templates.env.filters["first_author"] = first_author
    templates.env.filters["format_duration"] = format_duration
    templates.env.filters["cron_human"] = cron_human
    templates.env.filters["from_json"] = from_json
```

### `relative_date(iso_str: str) -> str`

Converts an ISO 8601 timestamp to a human-readable relative time string.

```python
from datetime import datetime, timezone

def relative_date(iso_str: str) -> str:
    """Convert ISO timestamp to relative string like '3 days ago'."""
    if not iso_str:
        return "—"

    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)

        # Make both offset-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        delta = now - dt
        seconds = int(delta.total_seconds())

        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif seconds < 604800:  # 7 days
            days = seconds // 86400
            return f"{days} day{'s' if days != 1 else ''} ago"
        elif seconds < 2592000:  # 30 days
            weeks = seconds // 604800
            return f"{weeks} week{'s' if weeks != 1 else ''} ago"
        else:
            # Show absolute date for older items
            return dt.strftime("%b %d, %Y")

    except (ValueError, TypeError):
        return iso_str
```

**Usage:** `{{ run.started_at|relative_date }}` → "3 days ago"

---

### `first_author(authors_json: str) -> str`

Parses a JSON author array and returns a compact representation.

```python
import json

def first_author(authors_json: str) -> str:
    """Parse JSON author array, return 'First Author et al.' or single name."""
    if not authors_json:
        return "Unknown"

    try:
        if isinstance(authors_json, list):
            authors = authors_json
        else:
            authors = json.loads(authors_json)

        if not authors:
            return "Unknown"
        elif len(authors) == 1:
            return authors[0]
        else:
            return f"{authors[0]} et al."

    except (json.JSONDecodeError, TypeError):
        return "Unknown"
```

**Usage:** `{{ paper.authors|first_author }}` → "Alice Smith et al."

---

### `format_duration(started_at: str, finished_at: str | None) -> str`

Computes duration between two ISO timestamps.

```python
def format_duration(started_at: str, finished_at: str | None = None) -> str:
    """Compute duration between two ISO timestamps."""
    if not started_at:
        return "—"
    if not finished_at:
        return "In progress"

    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(finished_at)
        delta = end - start
        total_seconds = int(delta.total_seconds())

        if total_seconds < 0:
            return "—"
        elif total_seconds < 60:
            return f"{total_seconds}s"
        else:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            return f"{minutes}m {seconds}s"

    except (ValueError, TypeError):
        return "—"
```

**Usage:** `{{ run.started_at|format_duration(run.finished_at) }}` → "45s" or "1m 23s"

**Note on Jinja2 filter calling convention:** When used as `value|filter(arg)`, Jinja2 passes `value` as the first argument and `arg` as the second. So `started_at|format_duration(finished_at)` calls `format_duration(started_at, finished_at)`.

---

### `cron_human(cron_expr: str) -> str`

Converts a 5-field cron expression to a human-readable description.

```python
def cron_human(cron_expr: str) -> str:
    """Convert cron expression to human-readable text.

    Handles common patterns used in this project. Not a full cron parser.
    """
    if not cron_expr:
        return "—"

    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return cron_expr

    minute, hour, dom, month, dow = parts

    day_names = {
        "0": "Sunday", "1": "Monday", "2": "Tuesday",
        "3": "Wednesday", "4": "Thursday", "5": "Friday",
        "6": "Saturday", "7": "Sunday",
    }

    # Common pattern: specific weekday
    if dom == "*" and month == "*" and dow != "*":
        day = day_names.get(dow, f"day {dow}")
        return f"Every {day} at {hour.zfill(2)}:{minute.zfill(2)}"

    # Daily
    if dom == "*" and month == "*" and dow == "*":
        return f"Daily at {hour.zfill(2)}:{minute.zfill(2)}"

    # Monthly on specific day
    if month == "*" and dow == "*" and dom != "*":
        return f"Monthly on day {dom} at {hour.zfill(2)}:{minute.zfill(2)}"

    # Fallback: return the raw expression
    return cron_expr
```

**Usage:** `{{ config.ingestion.schedule_cron|cron_human }}` → "Every Monday at 08:00"

---

### `from_json(value: str) -> dict | list`

Parses a JSON string into a Python object. Used in the paper detail snapshots table to parse `yearly_breakdown` stored as a JSON text column in SQLite.

```python
import json

def from_json(value: str):
    """Parse a JSON string. Returns the parsed object, or the original value on error."""
    if not value:
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
```

**Usage:** `{{ s.yearly_breakdown|from_json }}` → `{"2025": 89, "2026": 53}`

**Note:** Jinja2 does not include a built-in `from_json` filter (unlike `tojson`), so this must be registered as a custom filter.

---

## HTMX Patterns Reference

These patterns are used consistently across the application. Each pattern is documented once here and referenced from the page-specific docs.

### Pattern 1: Debounced Search Input

```html
<input type="search"
       name="q"
       placeholder="Search..."
       value="{{ search_query }}"
       hx-get="/partials/paper-rows"
       hx-trigger="keyup changed delay:300ms"
       hx-target="#paper-table-body"
       hx-include="#paper-filters"
       hx-push-url="true">
```

**Behavior:**

- Fires after 300ms pause in typing (`delay:300ms`).
- Only fires if the value actually changed (`changed`).
- Sends all form fields via `hx-include`.
- Updates browser URL for bookmarkability.

**Used by:** Paper list page (doc 02).

---

### Pattern 2: Dropdown Filter

```html
<select name="status"
        hx-get="/partials/paper-rows"
        hx-trigger="change"
        hx-target="#paper-table-body"
        hx-include="#paper-filters"
        hx-push-url="true">
    <option value="">All</option>
    <option value="active">Active</option>
    ...
</select>
```

**Behavior:**

- Fires immediately on selection change.
- Same include/target/push-url pattern as search.

**Used by:** Paper list page (doc 02).

---

### Pattern 3: Action Button with Spinner

```html
<button hx-post="/partials/trigger-ingest"
        hx-target="#ingest-result"
        hx-indicator="#ingest-spinner"
        hx-disabled-elt="this">
    Run Ingestion
</button>
<span id="ingest-spinner" class="htmx-indicator" aria-hidden="true">
    <span aria-busy="true">Running...</span>
</span>
<div id="ingest-result"></div>
```

**Behavior:**

1. Button click sends POST request.
2. Button is disabled during request (`hx-disabled-elt="this"`).
3. Spinner becomes visible (HTMX toggles the indicator class).
4. Response HTML replaces `#ingest-result` content.
5. Spinner hides, button re-enables.

**Used by:** Settings page triggers (doc 04).

---

### Pattern 4: Inline Status Update

```html
<button hx-post="/papers/{{ paper.id }}/status"
        hx-vals='{"status": "promoted"}'
        hx-target="#status-section"
        hx-swap="outerHTML"
        hx-confirm="Are you sure?">
    Promote
</button>
```

**Behavior:**

1. Click shows browser confirmation dialog.
2. If confirmed, POST sends the new status as form values.
3. Response contains the re-rendered status section.
4. `hx-swap="outerHTML"` replaces the entire `#status-section` div (including itself).

**Used by:** Paper detail page (doc 03).

---

### Pattern 5: Out-of-Band (OOB) Swap

```html
<!-- Primary response: goes to hx-target -->
<p class="trigger-success">Done. Found 28, ingested 5.</p>

<!-- OOB element: swaps into matching ID elsewhere on page -->
<tbody id="run-history-body" hx-swap-oob="innerHTML">
    <tr>...</tr>
    ...
</tbody>
```

**Behavior:**

1. HTMX processes the primary response into the original target.
2. HTMX detects `hx-swap-oob` on additional elements.
3. Those elements are swapped into matching IDs on the current page.
4. Result: multiple page sections updated from a single response.

**Used by:** Settings page ingestion trigger (doc 04) — updates both the result message and the run history table.

---

## Global HTMX Error Handling

Defined in `base.html` and active on all pages.

```html
<script>
    // Server returned an error status code (4xx, 5xx)
    document.addEventListener('htmx:responseError', function(evt) {
        var target = evt.detail.target;
        if (target) {
            target.innerHTML = '<p role="alert" style="color:var(--color-error)">Request failed. Please try again.</p>';
        }
    });

    // Network error (no response received)
    document.addEventListener('htmx:sendError', function(evt) {
        var target = evt.detail.target;
        if (target) {
            target.innerHTML = '<p role="alert" style="color:var(--color-error)">Network error. Check your connection.</p>';
        }
    });
</script>
```

**Behavior:**

- On server error: replaces the swap target content with an error message.
- On network error: same, but with a network-specific message.
- Uses `role="alert"` for screen reader announcement.
- Error styling uses the `--color-error` CSS custom property (adapts to dark mode).

---

## HTMX Configuration

Global HTMX settings are left at defaults. No `<meta name="htmx-config">` is needed.

| Setting | Value | Notes |
|---------|-------|-------|
| Default swap | `innerHTML` | HTMX default, works for all our use cases |
| Default settle delay | 20ms | HTMX default |
| History | Enabled via `hx-push-url` | Only on paper list filters |
| Timeout | None (infinite) | Acceptable for personal tool; triggers can take 30-60s |
