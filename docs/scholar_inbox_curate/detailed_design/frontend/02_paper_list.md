# 02 — Paper List

## Overview

The paper list page (`GET /papers`) is the primary browsing interface. It displays all tracked papers in a table with filtering by status, searching by title/author, sorting by any sortable column, and pagination. All interactions use HTMX for partial page updates without full reloads.

---

## Route Handler: `GET /papers`

### Signature

```python
PAGE_SIZE = 25

@app.get("/papers")
async def paper_list(
    request: Request,
    status: str | None = None,
    q: str | None = None,
    sort: str = "citation_velocity",
    order: str = "desc",
    page: int = 1,
):
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        papers = list_papers(
            conn,
            status=status,
            search=q,
            sort_by=sort,
            sort_order=order,
            limit=PAGE_SIZE,
            offset=(page - 1) * PAGE_SIZE,
        )
        total_count = count_papers(conn, status=status, search=q)

    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)

    return templates.TemplateResponse("papers/list.html", {
        **_base_context(request),
        "papers": [dict(row) for row in papers],
        "total_count": total_count,
        "current_page": page,
        "total_pages": total_pages,
        "status_filter": status,
        "search_query": q or "",
        "sort_by": sort,
        "sort_order": order,
    })
```

### Template Context

| Key | Type | Description |
|-----|------|-------------|
| `request` | `Request` | Starlette request object |
| `current_path` | `str` | `"/papers"` |
| `papers` | `list[dict]` | Paper rows for current page |
| `total_count` | `int` | Total papers matching current filters |
| `current_page` | `int` | Current page number (1-based) |
| `total_pages` | `int` | Total number of pages |
| `status_filter` | `str \| None` | Current status filter value |
| `search_query` | `str` | Current search text |
| `sort_by` | `str` | Current sort column name |
| `sort_order` | `str` | "asc" or "desc" |

### Backend Functions Used

- `list_papers(conn, status, search, sort_by, sort_order, limit, offset)` from `src/db.py` — returns filtered, sorted, paginated paper rows.
- `count_papers(conn, status, search)` — counting companion to `list_papers` that returns the total matching count (needed for pagination). Searches across `title`, `authors`, and `abstract`. Supports multi-word fuzzy search: each whitespace-separated word must match independently (AND logic), e.g. `"Diffusion Video"` matches papers containing both words anywhere in title, authors, or abstract.

`count_papers` implementation:

```python
def count_papers(conn, status: str | None = None, search: str | None = None) -> int:
    """Count papers matching the given filters.

    Used by the web UI for pagination. Mirrors the filter logic of list_papers().
    """
    conditions = []
    params: list = []

    if status is not None:
        conditions.append("status = ?")
        params.append(status)

    if search is not None:
        words = search.split()
        for word in words:
            conditions.append("(title LIKE ? OR authors LIKE ? OR abstract LIKE ?)")
            pattern = f"%{word}%"
            params.extend([pattern, pattern, pattern])

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    row = conn.execute(
        f"SELECT COUNT(*) as cnt FROM papers {where_clause}", params
    ).fetchone()
    return row["cnt"]
```

---

## Route Handler: `GET /partials/paper-rows`

This endpoint returns **only** the table body and pagination controls — no full page, no `base.html` wrapping. It's the HTMX swap target.

### Signature

```python
@app.get("/partials/paper-rows")
async def paper_rows_partial(
    request: Request,
    status: str | None = None,
    q: str | None = None,
    sort: str = "citation_velocity",
    order: str = "desc",
    page: int = 1,
):
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        papers = list_papers(
            conn,
            status=status,
            search=q,
            sort_by=sort,
            sort_order=order,
            limit=PAGE_SIZE,
            offset=(page - 1) * PAGE_SIZE,
        )
        total_count = count_papers(conn, status=status, search=q)

    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)

    return templates.TemplateResponse("papers/_rows.html", {
        "request": request,
        "papers": [dict(row) for row in papers],
        "total_count": total_count,
        "current_page": page,
        "total_pages": total_pages,
        "status_filter": status,
        "search_query": q or "",
        "sort_by": sort,
        "sort_order": order,
    })
```

**Note:** Same query parameters and logic as `GET /papers` but returns the partial template.

---

## Template: `src/web/templates/papers/list.html`

```html
{% extends "base.html" %}

{% block title %}Papers — Scholar Inbox Curate{% endblock %}

{% block content %}
<h1>Papers</h1>

<!-- Filters -->
<form id="paper-filters" role="search">
    <div class="grid">
        <div>
            <label for="status-filter">Status</label>
            <select id="status-filter" name="status"
                    hx-get="/partials/paper-rows"
                    hx-trigger="change"
                    hx-target="#paper-table-body"
                    hx-include="#paper-filters"
                    hx-push-url="true">
                <option value="">All</option>
                <option value="active" {% if status_filter == 'active' %}selected{% endif %}>Active</option>
                <option value="promoted" {% if status_filter == 'promoted' %}selected{% endif %}>Promoted</option>
                <option value="pruned" {% if status_filter == 'pruned' %}selected{% endif %}>Pruned</option>
            </select>
        </div>
        <div>
            <label for="search-input">Search</label>
            <input type="search"
                   id="search-input"
                   name="q"
                   placeholder="Search title, author, or abstract..."
                   value="{{ search_query }}"
                   hx-get="/partials/paper-rows"
                   hx-trigger="keyup changed delay:300ms"
                   hx-target="#paper-table-body"
                   hx-include="#paper-filters"
                   hx-push-url="true">
        </div>
    </div>

    <!-- Hidden inputs to carry sort state across HTMX requests -->
    <input type="hidden" name="sort" value="{{ sort_by }}">
    <input type="hidden" name="order" value="{{ sort_order }}">
    <input type="hidden" name="page" value="1">
</form>

<!-- Paper Table -->
<div id="paper-table-body">
    {% include "papers/_rows.html" %}
</div>

{% endblock %}
```

**Key design decision:** The `<div id="paper-table-body">` is placed **outside** the `<table>` element (not inside it). The full table structure including `<thead>` lives in `_rows.html`, so column headers are preserved when HTMX swaps the partial.

---

## Partial Template: `src/web/templates/papers/_rows.html`

This partial renders the complete table (including `<thead>` with sort headers, `<tbody>` with rows) and pagination. It's used both for initial page load (included in `list.html`) and for HTMX updates. By including the full table structure, column headers are preserved across HTMX swaps.

```html
<div class="table-responsive">
    <table>
        <caption class="sr-only">Tracked papers</caption>
        <thead>
            <tr>
                <!-- Sortable column headers with HTMX sort links -->
                <th scope="col">
                    <a href="#" hx-get="/partials/paper-rows" hx-vals='...' ...>
                        Title {% if sort_by == 'title' %}{{ '▲' if sort_order == 'asc' else '▼' }}{% endif %}
                    </a>
                </th>
                <th scope="col">Authors</th>
                <!-- ... Year, Score, Citations, Velocity, Status, Category, Ingested ... -->
            </tr>
        </thead>
        <tbody>
    {% if papers %}
        {% for paper in papers %}
        <tr>
            <td class="title-cell">
                <a href="/papers/{{ paper.id }}" title="{{ paper.title }}">{{ paper.title|truncate(80) }}</a>
            </td>
            <td>{{ paper.authors|first_author }}</td>
            <td>{{ paper.year or '—' }}</td>
            <td>{{ "%.0f"|format(paper.scholar_inbox_score) if paper.scholar_inbox_score else '—' }}</td>
            <td>{{ paper.citation_count }}</td>
            <td>{{ "%.1f"|format(paper.citation_velocity) }} /mo</td>
            <td>{% with status=paper.status %}{% include "components/_status_badge.html" %}{% endwith %}</td>
            <td>{{ paper.category or '—' }}</td>
            <td>{{ paper.ingested_at|relative_date }}</td>
        </tr>
        {% endfor %}
    {% else %}
        <tr>
            <td colspan="9">
                {% if search_query or status_filter %}
                    No papers match your filters.
                {% else %}
                    No papers tracked yet. <a href="/settings">Run an ingestion</a> to get started.
                {% endif %}
            </td>
        </tr>
    {% endif %}
        </tbody>
    </table>
</div>

<!-- Pagination -->
{% if total_pages > 1 %}
<nav aria-label="Pagination" style="margin-top: 1rem;">
    <ul>
        {% if current_page > 1 %}
        <li>
            <a href="#"
               hx-get="/partials/paper-rows"
               hx-vals='{"page": "{{ current_page - 1 }}"}'
               hx-target="#paper-table-body"
               hx-include="#paper-filters"
               hx-push-url="true">
                Previous
            </a>
        </li>
        {% endif %}

        {% for p in range(1, total_pages + 1) %}
            {% if p == current_page %}
            <li><a href="#" aria-current="page"><strong>{{ p }}</strong></a></li>
            {% elif p <= 3 or p > total_pages - 2 or (p >= current_page - 1 and p <= current_page + 1) %}
            <li>
                <a href="#"
                   hx-get="/partials/paper-rows"
                   hx-vals='{"page": "{{ p }}"}'
                   hx-target="#paper-table-body"
                   hx-include="#paper-filters"
                   hx-push-url="true">
                    {{ p }}
                </a>
            </li>
            {% elif p == 4 or p == total_pages - 2 %}
            <li><span>...</span></li>
            {% endif %}
        {% endfor %}

        {% if current_page < total_pages %}
        <li>
            <a href="#"
               hx-get="/partials/paper-rows"
               hx-vals='{"page": "{{ current_page + 1 }}"}'
               hx-target="#paper-table-body"
               hx-include="#paper-filters"
               hx-push-url="true">
                Next
            </a>
        </li>
        {% endif %}
    </ul>
    <small>Page {{ current_page }} of {{ total_pages }} ({{ total_count }} papers)</small>
</nav>
{% endif %}
```

---

## HTMX Interaction Flows

### Filter Change Flow

1. User types in search input or changes status dropdown.
2. HTMX fires `GET /partials/paper-rows` with all current filter values (`hx-include="#paper-filters"` serializes the form).
3. The hidden `page` input is always reset to `1` when filters change (handled by sort header links sending `"page": "1"`).
4. Server returns the `_rows.html` partial.
5. HTMX swaps the content of `#paper-table-body`.
6. `hx-push-url="true"` updates the browser URL (e.g., `/papers?status=active&q=transformer&sort=citation_velocity&order=desc`).

### Sort Change Flow

1. User clicks a sortable column header.
2. The `hx-vals` on the header link provides the new sort column and toggles the order if clicking the same column.
3. Page resets to 1.
4. Same swap and URL update as filter changes.

### Pagination Flow

1. User clicks a page number or prev/next link.
2. The page value is sent via `hx-vals`, other filters via `hx-include`.
3. Server returns new rows for that page.
4. URL updates.

### URL State Preservation

- All filter/sort/page state is reflected in the URL via `hx-push-url="true"`.
- On full page load (`GET /papers?status=active&sort=year&order=asc&page=2`), query params are parsed by the route handler and used to set initial filter values in the template.
- Bookmarking a filtered/sorted view works correctly.
- Browser back button works because HTMX pushes URL state.

### Partial Redirect on Direct Access

Since `hx-push-url="true"` pushes the partial URL (`/partials/paper-rows?...`) into the browser address bar, a page refresh would load the bare partial without the base layout. To prevent this, the `/partials/paper-rows` endpoint checks for the `HX-Request` header:

- **Present** (HTMX request): returns the partial template as normal.
- **Absent** (direct browser load / refresh): redirects to `/papers` with the same query parameters, rendering the full page.

---

## Sortable Columns

| Column | `sort` param | Default order | Sortable |
|--------|-------------|---------------|----------|
| Title | `title` | desc | Yes |
| Authors | — | — | No |
| Year | `year` | desc | Yes |
| Score | `scholar_inbox_score` | desc | Yes |
| Citations | `citation_count` | desc | Yes |
| Velocity | `citation_velocity` | desc (default sort) | Yes |
| Status | — | — | No |
| Category | — | — | No |
| Ingested | `ingested_at` | desc | Yes |

**Sort indicator:** `▲` for ascending, `▼` for descending, shown only on the active sort column.

**Default sort:** `citation_velocity DESC` when no sort is specified.

---

## Input Validation

The route handler validates sort parameters to prevent SQL injection:

```python
ALLOWED_SORT_COLUMNS = {
    "title", "year", "scholar_inbox_score",
    "citation_count", "citation_velocity", "ingested_at",
}
ALLOWED_SORT_ORDERS = {"asc", "desc"}

# In route handler:
if sort not in ALLOWED_SORT_COLUMNS:
    sort = "citation_velocity"
if order not in ALLOWED_SORT_ORDERS:
    order = "desc"
```

---

## Empty States

| Condition | Display |
|-----------|---------|
| No papers match filters | `<td colspan="9">No papers match your filters.</td>` |
| No papers in database | `<td colspan="9">No papers tracked yet. Run an ingestion to get started.</td>` with link to settings |

---

## Accessibility

- Search input has a `<label>` element.
- Status dropdown has a `<label>` element.
- Table has `<caption class="sr-only">`.
- Sort headers use `aria-sort="ascending"` / `"descending"` on the active sort `<th>`.
- Pagination uses `<nav aria-label="Pagination">`.
- Current page uses `aria-current="page"`.
- HTMX sets `aria-busy="true"` on the target element during requests automatically.
