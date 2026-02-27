# 03 — Paper Detail

## Overview

The paper detail page (`GET /papers/{paper_id}`) is the deep-dive view for a single paper. It shows all known metadata, the full citation history as an interactive chart, a stats sidebar, a collapsible raw snapshots table, and action buttons for manually changing the paper's status.

---

## Route Handler: `GET /papers/{paper_id}`

### Signature

```python
import json
from fastapi import HTTPException

@app.get("/papers/{paper_id}")
async def paper_detail(request: Request, paper_id: str):
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        paper = get_paper(conn, paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found")

        paper = dict(paper)

        snapshots = conn.execute(
            "SELECT checked_at, total_citations, source, yearly_breakdown "
            "FROM citation_snapshots WHERE paper_id = ? "
            "ORDER BY checked_at ASC",
            (paper_id,)
        ).fetchall()
        snapshots = [dict(s) for s in snapshots]

    # Parse authors from JSON string
    authors = []
    if paper.get("authors"):
        try:
            authors = json.loads(paper["authors"])
        except (json.JSONDecodeError, TypeError):
            authors = []

    # Serialize snapshots for Chart.js
    snapshots_json = json.dumps([
        {"date": s["checked_at"][:10], "total": s["total_citations"]}
        for s in snapshots
    ])

    return templates.TemplateResponse("papers/detail.html", {
        **_base_context(request),
        "paper": paper,
        "authors": authors,
        "snapshots": snapshots,
        "snapshots_json": snapshots_json,
        "snapshot_count": len(snapshots),
    })
```

### Template Context

| Key | Type | Description |
|-----|------|-------------|
| `request` | `Request` | Starlette request |
| `current_path` | `str` | `"/papers/{paper_id}"` |
| `paper` | `dict` | Full paper row (all columns from `papers` table) |
| `authors` | `list[str]` | Parsed author names |
| `snapshots` | `list[dict]` | Citation snapshots ordered by date ASC (keys: `checked_at`, `total_citations`, `source`, `yearly_breakdown`) |
| `snapshots_json` | `str` | JSON string for Chart.js: `[{"date": "2026-01-15", "total": 120}, ...]` |
| `snapshot_count` | `int` | Number of snapshots |

---

## Template: `src/web/templates/papers/detail.html`

```html
{% extends "base.html" %}

{% block title %}{{ paper.title|truncate(60) }} — Scholar Inbox Curate{% endblock %}

{% block content %}

<!-- Header -->
<hgroup>
    <h1>{{ paper.title }}</h1>
    <p>
        {% if paper.venue %}{{ paper.venue }}{% endif %}
        {% if paper.year %}({{ paper.year }}){% endif %}
    </p>
</hgroup>

<!-- Authors -->
<p>
    {% if authors|length <= 5 %}
        {{ authors|join(", ") }}
    {% else %}
        {{ authors[:5]|join(", ") }}
        <details style="display:inline;">
            <summary>and {{ authors|length - 5 }} more</summary>
            {{ authors[5:]|join(", ") }}
        </details>
    {% endif %}
    {% if not authors %}
        <em>Authors unknown</em>
    {% endif %}
</p>

<!-- Score + Status + Actions -->
<div class="grid">
    <div>
        <p>
            <strong>Scholar Inbox Score:</strong>
            <mark class="score-{{ 'high' if paper.scholar_inbox_score >= 90 else ('medium' if paper.scholar_inbox_score >= 70 else 'low') }}">
                {{ "%.0f"|format(paper.scholar_inbox_score) }}
            </mark>
        </p>
    </div>
    <div>
        {% include "components/_status_section.html" %}
    </div>
</div>

<!-- External Links -->
<p>
    {% if paper.url %}
        <a href="{{ paper.url }}" target="_blank" rel="noopener">Scholar Inbox</a>
    {% endif %}
    {% if paper.id and not paper.id.startswith('title:') %}
        {% if paper.url %}·{% endif %}
        <a href="https://www.semanticscholar.org/paper/{{ paper.id }}" target="_blank" rel="noopener">Semantic Scholar</a>
    {% endif %}
    {% if paper.arxiv_id %}
        · <a href="https://arxiv.org/abs/{{ paper.arxiv_id }}" target="_blank" rel="noopener">arXiv</a>
    {% endif %}
</p>

<hr>

<!-- Two-column layout: chart + stats -->
<div class="detail-layout">

    <!-- Main content: chart + snapshots table -->
    <div>
        <h2>Citation History</h2>
        {% include "components/_citation_chart.html" %}

        <!-- Snapshots Table (collapsible) -->
        <details>
            <summary>Citation Snapshots ({{ snapshot_count }})</summary>
            {% if snapshots %}
            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th scope="col">Date</th>
                            <th scope="col">Total Citations</th>
                            <th scope="col">Source</th>
                            <th scope="col">Yearly Breakdown</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for s in snapshots|reverse %}
                        <tr>
                            <td>{{ s.checked_at[:10] }}</td>
                            <td>{{ s.total_citations }}</td>
                            <td>{{ s.source|replace('_', ' ')|capitalize }}</td>
                            <td>
                                {% if s.yearly_breakdown %}
                                    {% set breakdown = s.yearly_breakdown|from_json if s.yearly_breakdown is string else s.yearly_breakdown %}
                                    {% if breakdown is mapping %}
                                        {% for year, count in breakdown|dictsort %}
                                            {{ year }}: {{ count }}{% if not loop.last %}, {% endif %}
                                        {% endfor %}
                                    {% else %}
                                        —
                                    {% endif %}
                                {% else %}
                                    —
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <p>No citation snapshots recorded yet.</p>
            {% endif %}
        </details>
    </div>

    <!-- Stats Sidebar -->
    <aside>
        <h3>Stats</h3>
        <dl>
            <dt>Current Citations</dt>
            <dd>{{ paper.citation_count }}</dd>

            <dt>Velocity</dt>
            <dd>{{ "%.1f"|format(paper.citation_velocity) }} /month</dd>

            <dt>Published</dt>
            <dd>{{ paper.published_date[:10] if paper.published_date else 'Unknown' }}</dd>

            <dt>First Tracked</dt>
            <dd>{{ paper.ingested_at[:10] }}</dd>

            <dt>Last Checked</dt>
            <dd>{{ paper.last_cited_check[:10] if paper.last_cited_check else 'Never' }}</dd>

            <dt>Snapshots</dt>
            <dd>{{ snapshot_count }}</dd>

            <dt>Status</dt>
            <dd>{% with status=paper.status %}{% include "components/_status_badge.html" %}{% endwith %}</dd>

            {% if paper.abstract %}
            <dt>Abstract</dt>
            <dd><details><summary>Show abstract</summary>{{ paper.abstract }}</details></dd>
            {% endif %}
        </dl>
    </aside>

</div>

{% endblock %}

{% block extra_scripts %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js"></script>
<script>
{{ chart_init_script | safe }}
</script>
{% endblock %}
```

---

## Status Section Component: `src/web/templates/components/_status_section.html`

This component renders the current status badge and action buttons. It's also returned as the HTMX response when a status update is performed.

```html
<div id="status-section">
    <strong>Status:</strong>
    {% with status=paper.status %}{% include "components/_status_badge.html" %}{% endwith %}
    {% if paper.manual_status %}
        <small>(manually set)</small>
    {% endif %}

    {% if paper.status == 'active' %}
        <button hx-post="/papers/{{ paper.id }}/status"
                hx-vals='{"status": "promoted"}'
                hx-target="#status-section"
                hx-swap="outerHTML"
                class="outline"
                style="margin-left: 0.5rem;">
            Promote
        </button>
        <button hx-post="/papers/{{ paper.id }}/status"
                hx-vals='{"status": "pruned"}'
                hx-target="#status-section"
                hx-swap="outerHTML"
                hx-confirm="Prune this paper? It will be hidden from active views."
                class="outline secondary"
                style="margin-left: 0.25rem;">
            Prune
        </button>
    {% elif paper.status == 'pruned' %}
        <button hx-post="/papers/{{ paper.id }}/status"
                hx-vals='{"status": "active"}'
                hx-target="#status-section"
                hx-swap="outerHTML"
                class="outline">
            Restore to Active
        </button>
    {% elif paper.status == 'promoted' %}
        <button hx-post="/papers/{{ paper.id }}/status"
                hx-vals='{"status": "active"}'
                hx-target="#status-section"
                hx-swap="outerHTML"
                class="outline secondary">
            Demote to Active
        </button>
    {% endif %}
</div>
```

---

## Route Handler: `POST /papers/{paper_id}/status`

```python
@app.post("/papers/{paper_id}/status")
async def update_status(request: Request, paper_id: str):
    form = await request.form()
    new_status = form.get("status")

    VALID_STATUSES = {"active", "promoted", "pruned"}
    if new_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        paper = get_paper(conn, paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found")

        update_paper_status(conn, paper_id, new_status, manual=True)
        paper = dict(get_paper(conn, paper_id))

    return templates.TemplateResponse("components/_status_section.html", {
        "request": request,
        "paper": paper,
    })
```

**Key points:**

- `manual=True` — sets `manual_status=1` in the database so the prune/promote rules engine won't override this status.
- Returns just the `_status_section.html` component, which replaces the existing `#status-section` via `hx-swap="outerHTML"`.
- `hx-confirm` on the Prune button shows a browser confirmation dialog before proceeding.

---

## Citation History Chart

The chart is rendered by the `_citation_chart.html` component and initialized in `{% block extra_scripts %}`.

### Component: `src/web/templates/components/_citation_chart.html`

```html
{% if snapshot_count >= 2 %}
    <div style="position: relative; max-height: 400px;">
        <canvas id="citationChart"></canvas>
    </div>
    <!-- Screen reader alternative -->
    <p class="sr-only">
        Citation count over time: started at {{ snapshots[0].total_citations }} on {{ snapshots[0].checked_at[:10] }},
        currently {{ snapshots[-1].total_citations }} on {{ snapshots[-1].checked_at[:10] }}.
    </p>
{% elif snapshot_count == 1 %}
    <p>
        <strong>{{ snapshots[0].total_citations }}</strong> citations as of {{ snapshots[0].checked_at[:10] }}.
        More data points needed for a chart.
    </p>
{% else %}
    <p>No citation data yet. Citation tracking will populate this over time.</p>
{% endif %}
```

### Chart.js Initialization Script

Built in the route handler and passed as `chart_init_script` (or embedded directly):

```javascript
(function() {
    var snapshots = {{ snapshots_json | safe }};
    var canvas = document.getElementById('citationChart');

    if (!canvas || snapshots.length < 2) return;

    // Detect dark mode for chart colors
    var isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    var textColor = isDark ? '#e2e8f0' : '#334155';
    var gridColor = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)';
    var lineColor = '#3b82f6';

    new Chart(canvas, {
        type: 'line',
        data: {
            labels: snapshots.map(function(s) { return s.date; }),
            datasets: [{
                label: 'Total Citations',
                data: snapshots.map(function(s) { return s.total; }),
                borderColor: lineColor,
                backgroundColor: isDark ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.1)',
                fill: true,
                tension: 0.3,
                pointRadius: 4,
                pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: function(items) { return items[0].label; },
                        label: function(item) { return item.raw + ' citations'; }
                    }
                }
            },
            scales: {
                x: {
                    title: { display: true, text: 'Date', color: textColor },
                    ticks: { color: textColor, maxRotation: 45 },
                    grid: { color: gridColor }
                },
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Total Citations', color: textColor },
                    ticks: { color: textColor, precision: 0 },
                    grid: { color: gridColor }
                }
            }
        }
    });
})();
```

---

## `snapshots_json` Data Contract

Serialized in the route handler:

```python
snapshots_json = json.dumps([
    {"date": s["checked_at"][:10], "total": s["total_citations"]}
    for s in snapshots
])
```

- Array of objects, sorted by date ascending.
- `date` format: `"YYYY-MM-DD"` (truncated from ISO timestamp).
- `total`: integer citation count.
- Minimal payload — only what the chart needs.

---

## Snapshots Table

- Wrapped in `<details><summary>` for collapsibility — closed by default.
- Ordered by date **descending** (most recent first) — reversed from the chart order.
- Yearly breakdown: if present, rendered as inline text "2025: 89, 2026: 53". Requires a custom Jinja2 filter or inline parsing via `json.loads`.
- If `yearly_breakdown` is null, display "—".

---

## External Links

| Link | URL Pattern | Condition |
|------|-------------|-----------|
| Scholar Inbox | `{{ paper.url }}` | `paper.url` is not None |
| Semantic Scholar | `https://www.semanticscholar.org/paper/{{ paper.id }}` | `paper.id` does not start with `title:` |
| arXiv | `https://arxiv.org/abs/{{ paper.arxiv_id }}` | `paper.arxiv_id` is not None |

All external links use `target="_blank" rel="noopener"`.

---

## Two-Column Layout

Desktop (>= 768px): chart and snapshots on the left, stats sidebar on the right.

```css
.detail-layout {
    display: grid;
    grid-template-columns: 1fr 280px;
    gap: 2rem;
}
@media (max-width: 768px) {
    .detail-layout {
        grid-template-columns: 1fr;
    }
}
```

Mobile: single column — stats appear below the chart.

---

## Error States

| Scenario | Behavior |
|----------|----------|
| Paper not found | 404 error page (from `paper_detail` raising `HTTPException`) |
| No snapshots | Chart area shows "No citation data yet." Stats show 0/N/A. |
| 1 snapshot | Shows static value instead of chart. |
| Status update fails | HTMX error handler shows inline error (no swap occurs). |

---

## Accessibility

- Chart has a `<p class="sr-only">` text alternative summarizing the citation trajectory.
- Action buttons have descriptive text ("Promote", "Prune", "Restore to Active").
- `hx-confirm` for the Prune action — browser native dialog, accessible by default.
- `<details>/<summary>` for snapshots table and long author lists — natively accessible.
- External links include `rel="noopener"`.
- Stats sidebar uses `<dl>` (definition list) for semantic structure.
