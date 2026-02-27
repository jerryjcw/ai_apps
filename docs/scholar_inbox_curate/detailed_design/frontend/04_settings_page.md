# 04 — Settings Page

## Overview

The settings page (`GET /settings`) is the admin/operations interface. It displays the current configuration (read-only in v1), provides manual trigger buttons for ingestion, citation polling, and prune/promote rules, and shows the ingestion run history. All triggers use HTMX for inline feedback without full page reloads.

---

## Route Handler: `GET /settings`

### Signature

```python
@app.get("/settings")
async def settings(request: Request):
    config = request.app.state.config
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        ingestion_runs = get_recent_ingestion_runs(conn, limit=20)

    return templates.TemplateResponse("settings.html", {
        **_base_context(request),
        "config": config,
        "ingestion_runs": [dict(row) for row in ingestion_runs],
    })
```

### Template Context

| Key | Type | Description |
|-----|------|-------------|
| `request` | `Request` | Starlette request |
| `current_path` | `str` | `"/settings"` |
| `config` | `AppConfig` | Full application configuration dataclass |
| `ingestion_runs` | `list[dict]` | Last 20 ingestion runs (keys: `id`, `started_at`, `finished_at`, `papers_found`, `papers_ingested`, `status`, `error_message`) |

---

## Template: `src/web/templates/settings.html`

```html
{% extends "base.html" %}

{% block title %}Settings — Scholar Inbox Curate{% endblock %}

{% block content %}
<h1>Settings</h1>

<!-- Section 1: Configuration -->
<section>
    <h2>Configuration</h2>
    <p><small>Values loaded from <code>config.toml</code>. Edit the file and restart the server to change.</small></p>

    <h3>Ingestion</h3>
    <table>
        <tbody>
            <tr>
                <th scope="row">Score Threshold</th>
                <td>{{ config.ingestion.score_threshold }}</td>
            </tr>
            <tr>
                <th scope="row">Schedule</th>
                <td>
                    <code>{{ config.ingestion.schedule_cron }}</code>
                    <small>({{ config.ingestion.schedule_cron|cron_human }})</small>
                </td>
            </tr>
        </tbody>
    </table>

    <h3>Citation Polling</h3>
    <table>
        <tbody>
            <tr>
                <th scope="row">Batch Size</th>
                <td>{{ config.citations.semantic_scholar_batch_size }}</td>
            </tr>
            <tr>
                <th scope="row">Schedule</th>
                <td>
                    <code>{{ config.citations.poll_schedule_cron }}</code>
                    <small>({{ config.citations.poll_schedule_cron|cron_human }})</small>
                </td>
            </tr>
        </tbody>
    </table>

    <h3>Pruning Thresholds</h3>
    <table>
        <tbody>
            <tr>
                <th scope="row">Min Age</th>
                <td>{{ config.pruning.min_age_months }} months</td>
            </tr>
            <tr>
                <th scope="row">Min Citations</th>
                <td>{{ config.pruning.min_citations }}</td>
            </tr>
            <tr>
                <th scope="row">Min Velocity</th>
                <td>{{ config.pruning.min_velocity }} /month</td>
            </tr>
        </tbody>
    </table>

    <h3>Promotion Thresholds</h3>
    <table>
        <tbody>
            <tr>
                <th scope="row">Citation Threshold</th>
                <td>{{ config.promotion.citation_threshold }}</td>
            </tr>
            <tr>
                <th scope="row">Velocity Threshold</th>
                <td>{{ config.promotion.velocity_threshold }} /month (sustained)</td>
            </tr>
        </tbody>
    </table>

    <h3>Browser</h3>
    <table>
        <tbody>
            <tr>
                <th scope="row">Profile Directory</th>
                <td><code>{{ config.browser.profile_dir }}</code></td>
            </tr>
            <tr>
                <th scope="row">Headed Fallback</th>
                <td>{{ 'Yes' if config.browser.headed_fallback else 'No' }}</td>
            </tr>
        </tbody>
    </table>
</section>

<hr>

<!-- Section 2: Manual Triggers -->
<section>
    <h2>Manual Triggers</h2>

    <div class="grid">
        <!-- Ingest -->
        <article>
            <header><strong>Paper Ingestion</strong></header>
            <p>Scrape Scholar Inbox for new paper recommendations.</p>
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
        </article>

        <!-- Poll Citations -->
        <article>
            <header><strong>Citation Polling</strong></header>
            <p>Check citation counts for papers due for a poll.</p>
            <button hx-post="/partials/trigger-poll"
                    hx-target="#poll-result"
                    hx-indicator="#poll-spinner"
                    hx-disabled-elt="this">
                Poll Citations
            </button>
            <span id="poll-spinner" class="htmx-indicator" aria-hidden="true">
                <span aria-busy="true">Running...</span>
            </span>
            <div id="poll-result"></div>
        </article>

        <!-- Prune/Promote -->
        <article>
            <header><strong>Prune / Promote Rules</strong></header>
            <p>Evaluate papers against prune/promote thresholds.</p>
            <button hx-post="/partials/trigger-rules"
                    hx-target="#rules-result"
                    hx-indicator="#rules-spinner"
                    hx-disabled-elt="this">
                Run Rules
            </button>
            <span id="rules-spinner" class="htmx-indicator" aria-hidden="true">
                <span aria-busy="true">Running...</span>
            </span>
            <div id="rules-result"></div>
        </article>
    </div>
</section>

<hr>

<!-- Section 3: Ingestion Run History -->
<section>
    <h2>Ingestion History</h2>

    {% if ingestion_runs %}
    <div class="table-responsive">
        <table>
            <caption class="sr-only">Ingestion run history</caption>
            <thead>
                <tr>
                    <th scope="col">Started</th>
                    <th scope="col">Duration</th>
                    <th scope="col">Papers Found</th>
                    <th scope="col">Ingested</th>
                    <th scope="col">Status</th>
                </tr>
            </thead>
            <tbody id="run-history-body">
                {% for run in ingestion_runs %}
                <tr>
                    <td>{{ run.started_at|relative_date }}</td>
                    <td>{{ run.started_at|format_duration(run.finished_at) }}</td>
                    <td>{{ run.papers_found }}</td>
                    <td>{{ run.papers_ingested }}</td>
                    <td>
                        <span class="run-status-{{ run.status }}">{{ run.status|capitalize }}</span>
                        {% if run.error_message %}
                        <details>
                            <summary><small>Error details</small></summary>
                            <small><code>{{ run.error_message }}</code></small>
                        </details>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% else %}
    <p>No ingestion runs recorded yet.</p>
    {% endif %}
</section>

{% endblock %}
```

---

## Trigger Endpoint Handlers

### `POST /partials/trigger-ingest`

```python
@app.post("/partials/trigger-ingest")
async def trigger_ingest(request: Request):
    config = request.app.state.config

    try:
        from src.ingestion.orchestrate import run_ingest
        await run_ingest(config)

        # Fetch latest run for feedback
        with get_connection(config.db_path) as conn:
            runs = get_recent_ingestion_runs(conn, limit=1)
            latest = dict(runs[0]) if runs else {}
            all_runs = get_recent_ingestion_runs(conn, limit=20)

        found = latest.get("papers_found", 0)
        ingested = latest.get("papers_ingested", 0)

        # Main result + OOB swap for history table
        return HTMLResponse(
            f'<p class="trigger-success">Done. Found {found} papers, ingested {ingested} new.</p>'
            + _render_run_history_oob(request, templates, all_runs)
        )

    except Exception as e:
        return HTMLResponse(
            f'<p class="trigger-error">Failed: {str(e)}</p>'
        )
```

### `POST /partials/trigger-poll`

```python
@app.post("/partials/trigger-poll")
async def trigger_poll(request: Request):
    config = request.app.state.config

    try:
        from src.citations.poller import run_citation_poll
        result = await run_citation_poll(config, config.db_path)

        return HTMLResponse(
            f'<p class="trigger-success">Done. Updated {result} papers.</p>'
        )

    except Exception as e:
        return HTMLResponse(
            f'<p class="trigger-error">Failed: {str(e)}</p>'
        )
```

### `POST /partials/trigger-rules`

```python
@app.post("/partials/trigger-rules")
async def trigger_rules(request: Request):
    config = request.app.state.config

    try:
        from src.rules import run_prune_promote
        from src.db import now_utc

        with get_connection(config.db_path) as conn:
            result = run_prune_promote(conn, config, now_utc())

        return HTMLResponse(
            f'<p class="trigger-success">'
            f'Done. Pruned {result.papers_pruned}, promoted {result.papers_promoted} '
            f'(of {result.papers_evaluated} evaluated).'
            f'</p>'
        )

    except Exception as e:
        return HTMLResponse(
            f'<p class="trigger-error">Failed: {str(e)}</p>'
        )
```

---

## Out-of-Band History Table Refresh

After a successful ingestion trigger, the run history table should update to show the new run. This uses HTMX's out-of-band swap feature.

```python
def _render_run_history_oob(request, templates, runs):
    """Render the run history tbody with hx-swap-oob for out-of-band update."""
    rows = ""
    for run in runs:
        r = dict(run)
        status_class = f"run-status-{r['status']}"
        error_html = ""
        if r.get("error_message"):
            error_html = (
                f'<details><summary><small>Error details</small></summary>'
                f'<small><code>{r["error_message"]}</code></small></details>'
            )
        rows += (
            f'<tr>'
            f'<td>{relative_date(r["started_at"])}</td>'
            f'<td>{format_duration(r["started_at"], r.get("finished_at"))}</td>'
            f'<td>{r["papers_found"]}</td>'
            f'<td>{r["papers_ingested"]}</td>'
            f'<td><span class="{status_class}">{r["status"].capitalize()}</span>{error_html}</td>'
            f'</tr>'
        )
    return f'<tbody id="run-history-body" hx-swap-oob="innerHTML">{rows}</tbody>'
```

**How OOB swap works:**

1. The trigger response contains the primary result HTML (for `#ingest-result`) plus an additional `<tbody>` with `hx-swap-oob="innerHTML"`.
2. HTMX processes the primary swap into `#ingest-result`.
3. HTMX detects the `hx-swap-oob` attribute and separately swaps the `<tbody>` content into the matching `#run-history-body` element.
4. Result: both the trigger result message and the history table are updated from a single response.

---

## Long-Running Operation Behavior

| Operation | Estimated Duration | Notes |
|-----------|-------------------|-------|
| Ingestion | 30–60 seconds | Browser automation (Playwright) |
| Citation Poll | 5–15 seconds | API calls (batched) |
| Prune/Promote | < 1 second | Local DB queries only |

**HTMX waits for the response** — no timeout by default. During the wait:

- `hx-indicator` shows the "Running..." spinner.
- `hx-disabled-elt="this"` disables the button to prevent double-clicks.
- The user can still navigate to other pages (the HTMX request continues in the background).

**Future enhancement (v2):** For ingestion, consider running as a background task with polling for status. For v1, synchronous is acceptable — it's a personal tool with a single user.

---

## Configuration Display

The configuration section shows all values from `config.toml` grouped by category. All values are read-only in v1.

| Group | Fields | Display Format |
|-------|--------|----------------|
| Ingestion | `score_threshold`, `schedule_cron` | Threshold as number, cron as `code` + human-readable |
| Citation Polling | `semantic_scholar_batch_size`, `poll_schedule_cron` | Same pattern |
| Pruning | `min_age_months`, `min_citations`, `min_velocity` | Number + unit suffix |
| Promotion | `citation_threshold`, `velocity_threshold` | Number + unit suffix |
| Browser | `profile_dir`, `headed_fallback` | Path as `code`, boolean as Yes/No |

Cron expressions are displayed with both the raw value and a human-readable translation via the `cron_human` filter.

---

## Run History Table

| Column | Source | Format |
|--------|--------|--------|
| Started | `started_at` | Relative date via `relative_date` filter |
| Duration | `started_at`, `finished_at` | Via `format_duration` filter: "45s", "1m 23s", or "In progress" |
| Papers Found | `papers_found` | Integer |
| Ingested | `papers_ingested` | Integer |
| Status | `status` | Color-coded text + optional error details |

**Status colors (CSS classes):**

- `.run-status-completed` — green
- `.run-status-failed` — red
- `.run-status-running` — amber

**Error details** for failed runs are shown in a `<details>/<summary>` element below the status text (better than tooltip for longer error messages).

Maximum 20 rows displayed (no pagination needed — ingestion runs are infrequent).

---

## Empty States

| Section | Condition | Display |
|---------|-----------|---------|
| Trigger results | Before any trigger is clicked | Empty `<div>` — no placeholder text needed |
| Run history | No runs recorded | "No ingestion runs recorded yet." |

---

## Accessibility

- Trigger buttons have descriptive text ("Run Ingestion", "Poll Citations", "Run Rules").
- Spinner uses `aria-busy="true"` and `aria-hidden="true"` (hidden when not active, shown when active via HTMX indicator CSS).
- Config tables use `<th scope="row">` for the config key column.
- Run history table has `<caption class="sr-only">`.
- Status colors are accompanied by text labels.
- Error details in `<details>/<summary>` are natively accessible.
