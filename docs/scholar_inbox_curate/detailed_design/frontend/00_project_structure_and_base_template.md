# 00 — Project Structure & Base Template

## Overview

This document covers the FastAPI web module setup (`src/web/app.py`), the Jinja2 base template (`base.html`), CDN dependency management, navigation, error pages, and the conventions that all route handlers and templates follow. This is the foundation that all other frontend documents build on.

**Relationship to backend:** The web module is launched via `create_app(config)` called from the `serve` CLI command (see `detailed_design/backend/07_scheduler_and_cli.md`). It shares the same `AppConfig` and database layer as the rest of the application.

---

## FastAPI Web Module (`src/web/app.py`)

### App Factory

```python
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from src.config import AppConfig
from src.db import get_connection, init_db

def create_app(config: AppConfig) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Scholar Inbox Curate", docs_url=None, redoc_url=None)

    # Store config on app state for access in route handlers
    app.state.config = config
    app.state.db_path = config.db_path

    # Template engine
    templates = Jinja2Templates(directory="src/web/templates")
    _register_filters(templates)

    # Static files
    app.mount("/static", StaticFiles(directory="src/web/static"), name="static")

    # Register all routes (defined inline — app is small enough)
    _register_routes(app, templates)

    return app
```

**Design decisions:**

- `docs_url=None, redoc_url=None` — disables Swagger/ReDoc (not needed for a server-rendered app).
- All routes are registered in `app.py` directly — no separate router files. The entire frontend has ~12 routes; splitting into files adds indirection without benefit.
- `config` and `db_path` are stored on `app.state` so route handlers access them via `request.app.state.config`.

### Route Registration

```python
def _register_routes(app: FastAPI, templates: Jinja2Templates):
    """Register all page and partial routes."""

    @app.get("/")
    async def root():
        return RedirectResponse(url="/dashboard", status_code=302)

    @app.get("/dashboard")
    async def dashboard(request: Request):
        ...

    @app.get("/papers")
    async def paper_list(request: Request, ...):
        ...

    @app.get("/papers/{paper_id}")
    async def paper_detail(request: Request, paper_id: str):
        ...

    @app.get("/stats")
    async def stats(request: Request):
        ...

    @app.get("/settings")
    async def settings(request: Request):
        ...

    # HTMX partial endpoints
    @app.get("/partials/paper-rows")
    async def paper_rows_partial(request: Request, ...):
        ...

    @app.post("/partials/trigger-ingest")
    async def trigger_ingest(request: Request):
        ...

    @app.post("/partials/trigger-poll")
    async def trigger_poll(request: Request):
        ...

    @app.post("/partials/trigger-rules")
    async def trigger_rules(request: Request):
        ...

    @app.post("/partials/trigger-backfill")
    async def trigger_backfill(request: Request):
        ...

    @app.post("/partials/trigger-collect")
    async def trigger_collect(request: Request):
        ...

    @app.post("/papers/{paper_id}/status")
    async def update_status(request: Request, paper_id: str):
        ...

    # Health check (from backend doc 08)
    @app.get("/health")
    async def health():
        ...
```

---

## Route Handler Conventions

Every full-page route handler follows this pattern:

```python
@app.get("/dashboard")
async def dashboard(request: Request):
    config = request.app.state.config
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        # Query data
        ...

    return templates.TemplateResponse("dashboard.html", {
        "request": request,    # Required by Starlette
        "current_path": "/dashboard",  # For nav highlighting
        # ...page-specific data
    })
```

**Rules:**

1. **Context always includes `request`** — required by Starlette's `TemplateResponse`.
2. **`current_path`** — passed to every full-page template for navigation active-state highlighting.
3. **Database access** — open connection in the route handler via `get_connection()`, query data, close before rendering. No ORM, no Pydantic models for template data — plain `dict` from `sqlite3.Row`.
4. **Partial endpoints** return only fragment templates (prefixed with `_`), no base template wrapping.

### Base Context Helper

```python
def _base_context(request: Request) -> dict:
    """Return the dict every full-page template needs."""
    return {
        "request": request,
        "current_path": request.url.path,
    }
```

Usage: `context = {**_base_context(request), "papers": papers, ...}`

---

## CDN Dependencies

All frontend dependencies are loaded from CDNs. No npm, no build tools.

| Library   | Version | CDN URL | Notes |
|-----------|---------|---------|-------|
| HTMX      | 1.9.x   | `https://unpkg.com/htmx.org@1.9.12` | Loaded on every page (in base template) |
| Pico CSS  | 2.x     | `https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css` | Loaded on every page |
| Chart.js  | 4.x     | `https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js` | Loaded via `{% block extra_scripts %}` on the paper detail page and the stats page |

**Rationale for CDN over local static files:** Zero-maintenance versioning. The app is a personal tool accessed from a single machine, so CDN latency is negligible. If offline use is needed in the future, vendor the files into `src/web/static/vendor/`.

---

## Base Template (`src/web/templates/base.html`)

The base template defines the full HTML5 document structure. All page templates extend it.

```html
<!DOCTYPE html>
<html lang="en" data-theme="auto">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}Scholar Inbox Curate{% endblock %}</title>

    <!-- Pico CSS -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">

    <!-- Custom overrides -->
    <link rel="stylesheet" href="{{ url_for('static', path='style.css') }}">

    <!-- HTMX -->
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>

    {% block extra_head %}{% endblock %}
</head>
<body>

    <header class="container">
        <nav>
            <ul>
                <li><strong>Scholar Inbox Curate</strong></li>
            </ul>
            <ul>
                <li>
                    <a href="/dashboard"
                       {% if current_path.startswith('/dashboard') %}aria-current="page"{% endif %}>
                        Dashboard
                    </a>
                </li>
                <li>
                    <a href="/papers"
                       {% if current_path.startswith('/papers') %}aria-current="page"{% endif %}>
                        Papers
                    </a>
                </li>
                <li>
                    <a href="/stats"
                       {% if current_path.startswith('/stats') %}aria-current="page"{% endif %}>
                        Stats
                    </a>
                </li>
                <li>
                    <a href="/settings"
                       {% if current_path.startswith('/settings') %}aria-current="page"{% endif %}>
                        Settings
                    </a>
                </li>
            </ul>
        </nav>
    </header>

    <main class="container">
        {% block content %}{% endblock %}
    </main>

    <footer class="container">
        <small>Scholar Inbox Curate v0.1</small>
    </footer>

    <!-- Global HTMX error handlers -->
    <script>
        document.addEventListener('htmx:responseError', function(evt) {
            var target = evt.detail.target;
            if (target) {
                target.innerHTML = '<p role="alert" style="color:var(--color-error)">Request failed. Please try again.</p>';
            }
        });
        document.addEventListener('htmx:sendError', function(evt) {
            var target = evt.detail.target;
            if (target) {
                target.innerHTML = '<p role="alert" style="color:var(--color-error)">Network error. Check your connection.</p>';
            }
        });
    </script>

    {% block extra_scripts %}{% endblock %}

</body>
</html>
```

**Key design points:**

- `data-theme="auto"` — Pico CSS auto-detects OS light/dark mode preference.
- `aria-current="page"` — Pico CSS styles the active nav link automatically when this attribute is set.
- `{% block extra_head %}` — for page-specific `<meta>` or CSS (rarely used).
- `{% block extra_scripts %}` — for Chart.js on the paper detail page. Placed before `</body>` for proper DOM readiness.
- Global HTMX error handlers — catch failed requests across all pages and display inline error messages.
- HTMX `<meta>` config is not needed — defaults are fine (innerHTML swap, 20ms settle delay).

---

## Template Inheritance Pattern

Every page template extends `base.html`:

```html
{% extends "base.html" %}

{% block title %}Dashboard — Scholar Inbox Curate{% endblock %}

{% block content %}
    <h1>Dashboard</h1>
    <!-- Page content here -->
{% endblock %}
```

**Partial templates** (prefixed with `_`) never extend `base.html`. They render standalone HTML fragments for HTMX swaps:

```html
{# src/web/templates/papers/_rows.html — no extends, no block #}
{% for paper in papers %}
<tr>
    <td>...</td>
</tr>
{% endfor %}
```

---

## Error Pages

### Custom Exception Handlers

```python
from fastapi.responses import HTMLResponse

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return templates.TemplateResponse("error.html", {
        "request": request,
        "current_path": request.url.path,
        "error_code": 404,
        "error_message": "Page not found",
    }, status_code=404)

@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    import logging
    logging.getLogger(__name__).error("Internal error: %s", exc, exc_info=True)
    return templates.TemplateResponse("error.html", {
        "request": request,
        "current_path": request.url.path,
        "error_code": 500,
        "error_message": "Something went wrong",
    }, status_code=500)
```

### Error Template (`src/web/templates/error.html`)

```html
{% extends "base.html" %}

{% block title %}Error {{ error_code }}{% endblock %}

{% block content %}
<article>
    <header>
        <h1>{{ error_code }}</h1>
    </header>
    <p>{{ error_message }}</p>
    <p><a href="/dashboard">Back to Dashboard</a></p>
</article>
{% endblock %}
```

---

## Custom Jinja2 Filters

Filters are registered on the Jinja2 environment in `app.py`. Full implementation details are in `05_shared_components_and_htmx_patterns.md`.

```python
def _register_filters(templates: Jinja2Templates):
    """Register custom Jinja2 filters."""
    templates.env.filters["relative_date"] = relative_date
    templates.env.filters["first_author"] = first_author
    templates.env.filters["format_duration"] = format_duration
    templates.env.filters["cron_human"] = cron_human
    templates.env.filters["from_json"] = from_json
```

---

## File Listing

```
src/web/
├── __init__.py                # Empty
├── app.py                     # Factory + all routes + filter registration
├── filters.py                 # Custom Jinja2 filter implementations
├── templates/
│   ├── base.html              # Layout: head, nav, footer, CDN links
│   ├── error.html             # Shared error page (404, 500)
│   ├── dashboard.html         # Dashboard page
│   ├── papers/
│   │   ├── list.html          # Paper list page
│   │   ├── detail.html        # Paper detail page
│   │   └── _rows.html         # HTMX partial: table rows + pagination
│   ├── stats.html             # Database stats page (date coverage, poll freshness, ingestion/citation trends)
│   ├── settings.html          # Settings page
│   └── components/
│       ├── _summary_card.html
│       ├── _paper_table.html
│       ├── _citation_chart.html
│       ├── _status_badge.html
│       └── _status_section.html
└── static/
    └── style.css              # Minimal overrides on Pico CSS
```

**Naming conventions:**

- `_` prefix on templates = HTMX partial or include component (never rendered as a full page).
- `components/` directory = shared pieces used across multiple pages.
- `papers/` directory = templates specific to the paper views.
