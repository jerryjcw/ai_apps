# 07 — JavaScript & Interactivity

## Overview

The project avoids custom JavaScript wherever possible. HTMX handles all dynamic interactions (filtering, sorting, status updates, trigger buttons). The only JavaScript in the project is:

1. **Chart.js initialization** on the paper detail page.
2. **Global HTMX error handlers** in the base template.

All JS is inline `<script>` blocks in templates — no build step, no bundling, no modules, no npm. Total custom JavaScript: approximately 50 lines.

---

## Explicit Non-Goals

- No npm, no webpack/vite/esbuild, no bundler of any kind.
- No TypeScript.
- No JavaScript module system (`import`/`export`).
- No client-side routing.
- No client-side state management.
- No JavaScript for form submission, filtering, or table sorting (HTMX handles all of this).

---

## Chart.js Integration

### Loading Strategy

Chart.js is loaded from CDN **only on the paper detail page** via `{% block extra_scripts %}`. It is not included on other pages where it's not needed.

```html
{# In papers/detail.html #}
{% block extra_scripts %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js"></script>
<script>
    {# Chart initialization script here #}
</script>
{% endblock %}
```

**Why UMD build?** The `chart.umd.min.js` file works with plain `<script>` tags without a module system. It exposes `Chart` as a global.

### Full Chart Initialization Script

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
    var fillColor = isDark ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.1)';

    new Chart(canvas, {
        type: 'line',
        data: {
            labels: snapshots.map(function(s) { return s.date; }),
            datasets: [{
                label: 'Total Citations',
                data: snapshots.map(function(s) { return s.total; }),
                borderColor: lineColor,
                backgroundColor: fillColor,
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

### Chart Configuration Details

| Option | Value | Rationale |
|--------|-------|-----------|
| `type` | `'line'` | Citation count is a continuous time series |
| `fill` | `true` | Area fill makes the trend more visually apparent |
| `tension` | `0.3` | Slight curve smoothing for a cleaner look |
| `pointRadius` | `4` | Visible data points (important when snapshots are sparse) |
| `pointHoverRadius` | `6` | Slightly larger on hover for tooltip targeting |
| `responsive` | `true` | Resizes with container |
| `maintainAspectRatio` | `false` | Allows the chart to fill the container height (controlled by `max-height: 400px` on the wrapper) |
| `legend.display` | `false` | Only one dataset — legend is redundant |
| `y.beginAtZero` | `true` | Anchors the y-axis to show absolute scale |
| `y.ticks.precision` | `0` | Integer-only tick labels (citations are whole numbers) |
| `x.ticks.maxRotation` | `45` | Angled date labels to prevent overlap |

### Dark Mode Colors

| Element | Light Mode | Dark Mode |
|---------|-----------|-----------|
| Axis text | `#334155` (slate-700) | `#e2e8f0` (slate-200) |
| Grid lines | `rgba(0,0,0,0.1)` | `rgba(255,255,255,0.1)` |
| Line | `#3b82f6` (blue-500) | `#3b82f6` (same — high contrast in both themes) |
| Fill | `rgba(59,130,246,0.1)` | `rgba(59,130,246,0.2)` (slightly more opaque for dark bg) |

---

## `snapshots_json` Data Contract

### Server-Side Serialization

```python
# In the paper_detail route handler
snapshots_json = json.dumps([
    {"date": s["checked_at"][:10], "total": s["total_citations"]}
    for s in snapshots
])
```

### Shape

```json
[
    {"date": "2025-09-15", "total": 5},
    {"date": "2025-10-01", "total": 12},
    {"date": "2025-11-15", "total": 34},
    {"date": "2026-01-10", "total": 89},
    {"date": "2026-02-24", "total": 142}
]
```

| Field | Type | Format | Description |
|-------|------|--------|-------------|
| `date` | `string` | `YYYY-MM-DD` | Truncated from ISO 8601 timestamp |
| `total` | `integer` | — | Total citation count at this snapshot |

- Array sorted by date **ascending** (oldest first → newest last).
- Minimal payload: only date and total needed for the chart. Source, yearly breakdown, etc. are not included.

### Edge Cases

| Condition | `snapshots_json` value | Chart behavior |
|-----------|----------------------|----------------|
| 0 snapshots | `[]` | Script exits early (`snapshots.length < 2`), "No citation data" message shown |
| 1 snapshot | `[{"date": "...", "total": N}]` | Script exits early, static count shown |
| 2+ snapshots | Normal array | Chart renders |
| Decreasing total | Normal array with lower later value | Chart shows the dip — this is correct behavior (API corrections happen) |

---

## Global HTMX Event Handlers

Defined in `base.html`, active on all pages.

```html
<script>
    // Handle server errors (4xx, 5xx status codes)
    document.addEventListener('htmx:responseError', function(evt) {
        var target = evt.detail.target;
        if (target) {
            target.innerHTML = '<p role="alert" style="color:var(--color-error)">Request failed. Please try again.</p>';
        }
    });

    // Handle network errors (no response received)
    document.addEventListener('htmx:sendError', function(evt) {
        var target = evt.detail.target;
        if (target) {
            target.innerHTML = '<p role="alert" style="color:var(--color-error)">Network error. Check your connection.</p>';
        }
    });
</script>
```

**Design decisions:**

- `role="alert"` ensures screen readers announce the error.
- Uses `var(--color-error)` CSS custom property for theme-aware error color.
- Replaces the target content with the error message — this is appropriate because:
  - For filter/sort operations: the table body shows the error instead of stale data.
  - For triggers: the result area shows the error.
  - For status updates: the status section shows the error (the original buttons are lost, but a page refresh restores them).

---

## URL State Management

### How It Works

The paper list page uses `hx-push-url="true"` on HTMX requests to update the browser URL:

```
/papers?status=active&q=transformer&sort=citation_velocity&order=desc&page=2
```

### Server-Side Initial State

On full page load, query parameters are parsed by the route handler and used to populate filter controls:

```html
<input type="search" name="q" value="{{ search_query }}">
<select name="status">
    <option value="active" {% if status_filter == 'active' %}selected{% endif %}>Active</option>
    ...
</select>
```

**No JavaScript is needed for initial state.** The server renders the correct values into the HTML attributes.

### Browser History

- `hx-push-url="true"` pushes each filter/sort/page change onto the browser history stack.
- Browser back button navigates to the previous state.
- HTMX handles the back-navigation by re-fetching the URL and swapping content.

### Partial Redirect on Refresh

Since `hx-push-url="true"` pushes the partial URL (`/partials/paper-rows?...`) into the browser address bar, a page refresh would load the bare partial without the base layout. The `/partials/paper-rows` endpoint checks for the `HX-Request` header: if absent (direct browser load), it redirects to `/papers` with the same query parameters, serving the full page.

---

## Progressive Enhancement

The application is designed to work (with reduced interactivity) if JavaScript fails to load:

| Feature | With JS/HTMX | Without JS |
|---------|--------------|------------|
| Paper list filtering | Live HTMX updates | Standard form submission (add a `<noscript>` submit button) |
| Sorting | HTMX swap | Standard link navigation (sort headers are `<a>` elements) |
| Status updates | HTMX POST + partial swap | Would need a full form POST (not implemented in v1) |
| Trigger buttons | HTMX POST with inline result | Would not work (requires JS) |
| Citation chart | Chart.js renders | Snapshots table is always present as fallback |

**v1 approach:** Progressive enhancement for the chart (snapshots table is the fallback). The paper list degrades partially (sort links work, HTMX filtering does not). Trigger buttons require JS. This is acceptable for a personal tool.

---

## Future Enhancements (v2)

### Yearly Breakdown Stacked Bar Chart

If `yearly_breakdown` data is available in snapshots, overlay a stacked bar chart showing per-year citation contributions. This requires:

- A second dataset in Chart.js with `type: 'bar'` and `stack: true`.
- Processing the `yearly_breakdown` JSON into per-year arrays.
- Mixed chart type (`line` + `bar`).

Deferred to v2 due to complexity.

### Live Theme Switching

Detect OS theme changes while the page is open and re-render the chart:

```javascript
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function() {
    // Destroy and recreate chart with new colors
});
```

Deferred to v2 — page refresh works fine for now.
