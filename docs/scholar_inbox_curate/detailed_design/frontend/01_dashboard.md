# 01 — Dashboard

## Overview

The dashboard is the landing page (`GET /dashboard`). It answers three questions at a glance: "How many papers am I tracking?", "What's trending?", and "When was the last ingestion?" It displays summary metric cards, a top-10 papers-by-velocity table, and a recent activity section.

---

## Route Handler: `GET /dashboard`

### Signature

```python
@app.get("/dashboard")
async def dashboard(request: Request):
    config = request.app.state.config
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        stats = get_dashboard_statistics(conn)
        top_papers = get_trending_papers(conn, limit=10)
        recent_runs = get_recent_ingestion_runs(conn, limit=5)

    # Compute next poll time from cron expression
    next_poll = _next_cron_run(config.citations.poll_schedule_cron)

    return templates.TemplateResponse("dashboard.html", {
        **_base_context(request),
        "total_papers": stats["total_papers"],
        "trending_count": stats["trending_count"],
        "recent_count": stats["recently_ingested"],
        "next_poll": next_poll,
        "top_papers": top_papers,
        "recent_runs": [dict(row) for row in recent_runs],
    })
```

### Template Context

| Key | Type | Description |
|-----|------|-------------|
| `request` | `Request` | Starlette request object |
| `current_path` | `str` | `"/dashboard"` |
| `total_papers` | `int` | Count of active + promoted papers |
| `trending_count` | `int` | Papers with velocity > 5.0/month |
| `recent_count` | `int` | Papers ingested in last 7 days |
| `next_poll` | `str` | Next scheduled poll time, e.g., "Wed, Mar 4 at 06:00" or the cron schedule description if scheduler is not running |
| `top_papers` | `list[dict]` | Top 10 papers by velocity (keys: `id`, `title`, `authors`, `citation_count`, `citation_velocity`, `status`) |
| `recent_runs` | `list[dict]` | Last 5 ingestion runs (keys: `id`, `started_at`, `finished_at`, `papers_found`, `papers_ingested`, `status`, `error_message`) |

### Backend Functions Used

- `get_dashboard_statistics(conn)` from `src/db.py` — returns a dict with `total_papers`, `active`, `promoted`, `pruned`, `trending_count`, `recently_ingested`, `papers_due_for_poll`.
- `get_trending_papers(conn, limit=10)` from `src/db.py` — returns a `list[dict]` of papers ordered by `citation_velocity` DESC (keys: `id`, `title`, `authors`, `citation_count`, `citation_velocity`, `status`).
- `get_recent_ingestion_runs(conn, limit=5)` from `src/db.py` — returns recent ingestion runs.

---

## Template: `src/web/templates/dashboard.html`

```html
{% extends "base.html" %}

{% block title %}Dashboard — Scholar Inbox Curate{% endblock %}

{% block content %}

<!-- Summary Cards -->
<div class="grid">
    {% with card_label="Papers Tracked", card_value=total_papers %}
        {% include "components/_summary_card.html" %}
    {% endwith %}

    {% with card_label="Trending (>5/mo)", card_value=trending_count %}
        {% include "components/_summary_card.html" %}
    {% endwith %}

    {% with card_label="Added This Week", card_value=recent_count %}
        {% include "components/_summary_card.html" %}
    {% endwith %}

    {% with card_label="Next Poll", card_value=next_poll %}
        {% include "components/_summary_card.html" %}
    {% endwith %}
</div>

<!-- Top Papers by Velocity -->
<section>
    <h2>Top Papers by Velocity</h2>

    {% if top_papers %}
    <div class="table-responsive">
        <table>
            <caption class="sr-only">Top 10 papers ranked by citation velocity</caption>
            <thead>
                <tr>
                    <th scope="col">#</th>
                    <th scope="col">Title</th>
                    <th scope="col">Authors</th>
                    <th scope="col">Citations</th>
                    <th scope="col">Velocity</th>
                    <th scope="col">Status</th>
                </tr>
            </thead>
            <tbody>
                {% for paper in top_papers %}
                <tr>
                    <td>{{ loop.index }}</td>
                    <td class="title-cell">
                        <a href="/papers/{{ paper.id }}">{{ paper.title|truncate(80) }}</a>
                    </td>
                    <td>{{ paper.authors|first_author }}</td>
                    <td>{{ paper.citation_count }}</td>
                    <td>{{ "%.1f"|format(paper.citation_velocity) }} /mo</td>
                    <td>{% with status=paper.status %}{% include "components/_status_badge.html" %}{% endwith %}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% else %}
    <p>No papers tracked yet. <a href="/settings">Run an ingestion</a> to get started.</p>
    {% endif %}
</section>

<!-- Recent Activity -->
<section>
    <h2>Recent Activity</h2>

    {% if recent_runs %}
    <div class="table-responsive">
        <table>
            <caption class="sr-only">Recent ingestion runs</caption>
            <thead>
                <tr>
                    <th scope="col">Date</th>
                    <th scope="col">Papers Found</th>
                    <th scope="col">New Papers</th>
                    <th scope="col">Duration</th>
                    <th scope="col">Status</th>
                </tr>
            </thead>
            <tbody>
                {% for run in recent_runs %}
                <tr>
                    <td>{{ run.started_at|relative_date }}</td>
                    <td>{{ run.papers_found }}</td>
                    <td>{{ run.papers_ingested }}</td>
                    <td>{{ run.started_at|format_duration(run.finished_at) }}</td>
                    <td>
                        <span class="run-status-{{ run.status }}">{{ run.status|capitalize }}</span>
                        {% if run.error_message %}
                        <small title="{{ run.error_message }}">(hover for details)</small>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% else %}
    <p>No ingestion runs yet.</p>
    {% endif %}
</section>

{% endblock %}
```

---

## Summary Cards

The dashboard uses Pico CSS's `<div class="grid">` which creates a responsive auto-column grid. Each card is an `<article>` element rendered by the `_summary_card.html` component:

```html
{# src/web/templates/components/_summary_card.html #}
<article aria-label="{{ card_label }}">
    <header>{{ card_label }}</header>
    <p class="card-value">{{ card_value }}</p>
</article>
```

**Responsive behavior (handled by Pico CSS grid):**

| Viewport | Card layout |
|----------|-------------|
| Desktop (>= 992px) | 4 columns in one row |
| Tablet (>= 576px) | 2 columns, 2 rows |
| Mobile (< 576px) | 1 column, 4 rows |

---

## Top Papers Table

- **Title** links to the paper detail page (`/papers/{id}`).
- **Title** is truncated to 80 characters via Jinja2's built-in `truncate` filter. CSS `text-overflow: ellipsis` provides visual truncation for narrower viewports.
- **Authors** uses the custom `first_author` filter: parses the JSON author array, returns "First Author et al." if multiple authors, or just the name if single.
- **Velocity** formatted to one decimal place with "/mo" suffix.
- **Status** rendered via the `_status_badge.html` component (see doc 05).
- **Rank** uses `loop.index` (1-based).

---

## Recent Activity Section

- Shows the last 5 ingestion runs from the `ingestion_runs` table.
- **Date** uses the `relative_date` filter ("3 days ago", "2 weeks ago").
- **Duration** uses the `format_duration` filter: computes difference between `started_at` and `finished_at`, returns "45s" or "1m 23s", or "In progress" if `finished_at` is None.
- **Status** text is color-coded via CSS classes:
  - `.run-status-completed` — green text
  - `.run-status-failed` — red text
  - `.run-status-running` — amber text
- **Error details** for failed runs shown as a `title` attribute tooltip on hover.

---

## Next Poll Computation

The "Next Poll" card shows when the next citation poll will run. This is computed from the cron expression in config using APScheduler's `CronTrigger`:

```python
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timezone

def _next_cron_run(cron_expr: str) -> str:
    """Compute the next fire time from a cron expression and format it."""
    try:
        parts = cron_expr.split()
        if len(parts) != 5:
            return cron_human(cron_expr)

        trigger = CronTrigger(
            minute=parts[0], hour=parts[1], day=parts[2],
            month=parts[3], day_of_week=parts[4],
        )
        now = datetime.now(timezone.utc)
        next_fire = trigger.get_next_fire_time(None, now)

        if next_fire:
            return next_fire.strftime("%a, %b %-d at %H:%M")
        return cron_human(cron_expr)

    except Exception:
        return cron_human(cron_expr)
```

**Fallback:** If the cron expression can't be parsed (shouldn't happen with valid config), falls back to the human-readable cron description from the `cron_human` filter.

**Note:** This computes the next fire time from the cron expression statically. It does not require the scheduler to be running in the same process — the web server and scheduler may run separately (via `scholar-curate serve` vs `scholar-curate run`).

---

## Empty States

| Section | Condition | Display |
|---------|-----------|---------|
| Summary cards | No papers | All values show "0" |
| Top papers table | `top_papers` is empty | "No papers tracked yet. Run an ingestion to get started." with link to settings |
| Recent activity | `recent_runs` is empty | "No ingestion runs yet." |

---

## Accessibility

- Summary cards use `<article aria-label="...">` to provide screen reader context.
- Tables include `<caption class="sr-only">` (visually hidden) for screen reader identification.
- Table headers use `<th scope="col">`.
- Paper title links use the paper title as link text (descriptive, not "click here").
- Status badges include text labels — color is not the only indicator.
- Error tooltips (`title` attribute) are supplementary; the "(hover for details)" text signals their presence.
