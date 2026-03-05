"""Settings page route handler."""

from fastapi import Request
from fastapi.templating import Jinja2Templates

from src.config import AppConfig
from src.db import get_connection, get_recent_ingestion_runs
from src.web.app import _base_context


async def render_settings(
    request: Request,
    config: AppConfig,
    db_path: str,
    templates: Jinja2Templates,
):
    """Render the settings page."""
    with get_connection(db_path) as conn:
        ingestion_runs = get_recent_ingestion_runs(conn, limit=20)

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            **_base_context(request),
            "config": config,
            "ingestion_runs": ingestion_runs,
        },
    )
