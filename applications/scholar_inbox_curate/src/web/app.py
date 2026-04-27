"""FastAPI web application for Scholar Inbox Curate.

Provides a server-rendered web UI using Jinja2 templates and HTMX.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import AppConfig
from src.db import get_connection
from src.web.filters import cron_human, first_author, format_duration, from_json, relative_date

logger = logging.getLogger(__name__)


def create_app(config: AppConfig) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Scholar Inbox Curate", docs_url=None, redoc_url=None)

    app.state.config = config
    app.state.db_path = config.db_path

    templates = Jinja2Templates(directory="src/web/templates")
    _register_filters(templates)

    app.mount("/static", StaticFiles(directory="src/web/static"), name="static")

    _register_routes(app, templates)

    return app


def _base_context(request: Request) -> dict:
    """Return the context dict every full-page template needs (excluding request)."""
    return {
        "current_path": request.url.path,
    }


def _register_filters(templates: Jinja2Templates) -> None:
    """Register custom Jinja2 filters."""
    templates.env.filters["relative_date"] = relative_date
    templates.env.filters["first_author"] = first_author
    templates.env.filters["format_duration"] = format_duration
    templates.env.filters["cron_human"] = cron_human
    templates.env.filters["from_json"] = from_json


def _register_routes(app: FastAPI, templates: Jinja2Templates) -> None:
    """Register all page and partial routes."""

    # --- Exception handlers ---

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                **_base_context(request),
                "error_code": 404,
                "error_message": "Page not found",
            },
            status_code=404,
        )

    @app.exception_handler(500)
    async def server_error_handler(request: Request, exc):
        logger.error("Internal error: %s", exc, exc_info=True)
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                **_base_context(request),
                "error_code": 500,
                "error_message": "Something went wrong",
            },
            status_code=500,
        )

    # --- Full-page routes ---

    @app.get("/")
    async def root():
        return RedirectResponse(url="/dashboard", status_code=302)

    @app.get("/dashboard")
    async def dashboard(request: Request):
        from src.web.routes.dashboard import render_dashboard

        config = request.app.state.config
        db_path = request.app.state.db_path
        return await render_dashboard(request, config, db_path, templates)

    @app.get("/papers")
    async def paper_list(
        request: Request,
        q: str = "",
        status: str = "",
        sort: str = "scraped_at",
        order: str = "desc",
        page: int = 1,
    ):
        from src.web.routes.papers import render_paper_list

        db_path = request.app.state.db_path
        return await render_paper_list(
            request, db_path, templates, q=q, status=status, sort=sort, order=order, page=page
        )

    @app.get("/papers/{paper_id}")
    async def paper_detail(request: Request, paper_id: str):
        from src.web.routes.papers import render_paper_detail

        db_path = request.app.state.db_path
        return await render_paper_detail(request, paper_id, db_path, templates)

    @app.get("/stats")
    async def stats(request: Request):
        from src.web.routes.stats import render_stats

        db_path = request.app.state.db_path
        return await render_stats(request, db_path, templates)

    @app.get("/settings")
    async def settings(request: Request):
        from src.web.routes.settings import render_settings

        config = request.app.state.config
        db_path = request.app.state.db_path
        return await render_settings(request, config, db_path, templates)

    # --- HTMX partial endpoints ---

    @app.get("/partials/paper-rows")
    async def paper_rows_partial(
        request: Request,
        q: str = "",
        status: str = "",
        sort: str = "scraped_at",
        order: str = "desc",
        page: int = 1,
    ):
        # Direct browser load (refresh) — redirect to the full page
        if "hx-request" not in request.headers:
            params = request.query_params
            qs = str(params) if params else ""
            url = f"/papers?{qs}" if qs else "/papers"
            return RedirectResponse(url=url, status_code=302)

        from src.web.routes.papers import render_paper_rows_partial

        db_path = request.app.state.db_path
        return await render_paper_rows_partial(
            request, db_path, templates, q=q, status=status, sort=sort, order=order, page=page
        )

    @app.post("/partials/trigger-ingest")
    async def trigger_ingest(request: Request):
        from src.web.routes.triggers import handle_trigger_ingest

        config = request.app.state.config
        db_path = request.app.state.db_path
        return await handle_trigger_ingest(request, config, db_path, templates)

    @app.post("/partials/trigger-poll")
    async def trigger_poll(request: Request):
        from src.web.routes.triggers import handle_trigger_poll

        config = request.app.state.config
        db_path = request.app.state.db_path
        return await handle_trigger_poll(request, config, db_path, templates)

    @app.post("/partials/trigger-rules")
    async def trigger_rules(request: Request):
        from src.web.routes.triggers import handle_trigger_rules

        config = request.app.state.config
        db_path = request.app.state.db_path
        return await handle_trigger_rules(request, config, db_path, templates)

    @app.post("/partials/trigger-backfill")
    async def trigger_backfill(request: Request):
        from src.web.routes.triggers import handle_trigger_backfill

        config = request.app.state.config
        db_path = request.app.state.db_path
        return await handle_trigger_backfill(request, config, db_path, templates)

    @app.post("/partials/trigger-collect")
    async def trigger_collect(request: Request):
        from src.web.routes.triggers import handle_trigger_collect

        config = request.app.state.config
        db_path = request.app.state.db_path
        return await handle_trigger_collect(request, config, db_path, templates)

    @app.post("/papers/{paper_id}/status")
    async def update_status(request: Request, paper_id: str):
        from src.web.routes.papers import handle_update_status

        db_path = request.app.state.db_path
        return await handle_update_status(request, paper_id, db_path, templates)

    # --- Health check ---

    @app.get("/health")
    async def health():
        try:
            db_path = app.state.db_path
            with get_connection(db_path) as conn:
                conn.execute("SELECT 1")
            return {"status": "ok", "service": "scholar-inbox-curate"}
        except Exception as e:
            return JSONResponse(
                status_code=503,
                content={"status": "error", "detail": str(e)},
            )
