"""Stats page route handler.

Renders a dedicated tab showing paper-date coverage, last-poll staleness
buckets, monthly ingestion trends, and weekly citation-update activity.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.templating import Jinja2Templates

from src.db import (
    get_connection,
    get_monthly_ingest_counts,
    get_paper_date_range,
    get_poll_staleness_buckets,
    get_weekly_citation_updates,
)
from src.web.app import _base_context


async def render_stats(
    request: Request,
    db_path: str,
    templates: Jinja2Templates,
):
    """Render the database-stats page."""
    with get_connection(db_path) as conn:
        date_range = get_paper_date_range(conn)
        poll = get_poll_staleness_buckets(conn)
        monthly = get_monthly_ingest_counts(conn, months=12)
        weekly = get_weekly_citation_updates(conn, weeks=26)

    return templates.TemplateResponse(
        request,
        "stats.html",
        {
            **_base_context(request),
            "date_range": date_range,
            "poll": poll,
            "monthly": monthly,
            "weekly": weekly,
        },
    )
