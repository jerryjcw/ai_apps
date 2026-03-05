"""Dashboard page route handler."""

from datetime import datetime, timezone

from fastapi import Request
from fastapi.templating import Jinja2Templates

from src.config import AppConfig
from src.db import get_connection, get_dashboard_statistics, get_recent_ingestion_runs, get_trending_papers
from src.web.app import _base_context
from src.web.filters import cron_human


def _next_cron_run(cron_expr: str) -> str:
    """Compute the next fire time from a cron expression and format it."""
    try:
        from apscheduler.triggers.cron import CronTrigger

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


async def render_dashboard(
    request: Request,
    config: AppConfig,
    db_path: str,
    templates: Jinja2Templates,
):
    """Render the dashboard page."""
    with get_connection(db_path) as conn:
        stats = get_dashboard_statistics(conn)
        top_papers = get_trending_papers(conn, limit=10)
        recent_runs = get_recent_ingestion_runs(conn, limit=5)

    next_poll = _next_cron_run(config.citations.poll_schedule_cron)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            **_base_context(request),
            "total_papers": stats["total_papers"],
            "trending_count": stats["trending_count"],
            "recent_count": stats["recently_ingested"],
            "next_poll": next_poll,
            "top_papers": top_papers,
            "recent_runs": recent_runs,
        },
    )
