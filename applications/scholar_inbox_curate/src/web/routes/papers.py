"""Paper list, detail, and status update route handlers."""

from fastapi import Request
from fastapi.templating import Jinja2Templates

from src.db import (
    count_papers,
    get_connection,
    get_paper,
    get_snapshots,
    list_papers,
    update_paper_status,
)
from src.web.app import _base_context

PAGE_SIZE = 25

ALLOWED_SORT_COLUMNS = {
    "title", "year", "scholar_inbox_score",
    "citation_count", "citation_velocity", "ingested_at",
}
ALLOWED_SORT_ORDERS = {"asc", "desc"}


def _validated_sort(sort: str, order: str) -> tuple[str, str]:
    if sort not in ALLOWED_SORT_COLUMNS:
        sort = "citation_velocity"
    if order not in ALLOWED_SORT_ORDERS:
        order = "desc"
    return sort, order


async def render_paper_list(
    request: Request,
    db_path: str,
    templates: Jinja2Templates,
    q: str = "",
    status: str = "",
    sort: str = "citation_velocity",
    order: str = "desc",
    page: int = 1,
):
    """Render the paper list page."""
    sort, order = _validated_sort(sort, order)
    status_val = status or None
    search_val = q or None
    page = max(1, page)

    with get_connection(db_path) as conn:
        papers = list_papers(
            conn,
            status=status_val,
            search=search_val,
            sort_by=sort,
            sort_order=order,
            limit=PAGE_SIZE,
            offset=(page - 1) * PAGE_SIZE,
        )
        total_count = count_papers(conn, status=status_val, search=search_val)

    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)

    return templates.TemplateResponse(
        request,
        "papers/list.html",
        {
            **_base_context(request),
            "papers": papers,
            "total_count": total_count,
            "current_page": page,
            "total_pages": total_pages,
            "status_filter": status_val,
            "search_query": q,
            "sort_by": sort,
            "sort_order": order,
        },
    )


async def render_paper_detail(
    request: Request,
    paper_id: str,
    db_path: str,
    templates: Jinja2Templates,
):
    """Render the paper detail page."""
    import json

    with get_connection(db_path) as conn:
        paper = get_paper(conn, paper_id)
        if paper is None:
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    **_base_context(request),
                    "error_code": 404,
                    "error_message": "Paper not found",
                },
                status_code=404,
            )

        # Fetch snapshots in ASC order for chart (template reverses for table)
        snapshot_rows = conn.execute(
            "SELECT checked_at, total_citations, source, yearly_breakdown "
            "FROM citation_snapshots WHERE paper_id = ? "
            "ORDER BY checked_at ASC",
            (paper_id,),
        ).fetchall()
        snapshots = [dict(s) for s in snapshot_rows]

    # Parse authors from JSON string
    authors = []
    if paper.get("authors"):
        try:
            authors = json.loads(paper["authors"])
        except (json.JSONDecodeError, TypeError):
            authors = []

    snapshots_json = json.dumps([
        {"date": s["checked_at"][:10], "total": s["total_citations"]}
        for s in snapshots
    ])

    return templates.TemplateResponse(
        request,
        "papers/detail.html",
        {
            **_base_context(request),
            "paper": paper,
            "authors": authors,
            "snapshots": snapshots,
            "snapshots_json": snapshots_json,
            "snapshot_count": len(snapshots),
        },
    )


async def render_paper_rows_partial(
    request: Request,
    db_path: str,
    templates: Jinja2Templates,
    q: str = "",
    status: str = "",
    sort: str = "citation_velocity",
    order: str = "desc",
    page: int = 1,
):
    """Render HTMX partial for paper table rows."""
    sort, order = _validated_sort(sort, order)
    status_val = status or None
    search_val = q or None
    page = max(1, page)

    with get_connection(db_path) as conn:
        papers = list_papers(
            conn,
            status=status_val,
            search=search_val,
            sort_by=sort,
            sort_order=order,
            limit=PAGE_SIZE,
            offset=(page - 1) * PAGE_SIZE,
        )
        total_count = count_papers(conn, status=status_val, search=search_val)

    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)

    return templates.TemplateResponse(
        request,
        "papers/_rows.html",
        {
            "papers": papers,
            "total_count": total_count,
            "current_page": page,
            "total_pages": total_pages,
            "status_filter": status_val,
            "search_query": q,
            "sort_by": sort,
            "sort_order": order,
        },
    )


async def handle_update_status(
    request: Request,
    paper_id: str,
    db_path: str,
    templates: Jinja2Templates,
):
    """Handle paper status update and return status section partial."""
    form = await request.form()
    new_status = form.get("status", "active")

    valid_statuses = {"active", "promoted", "pruned"}
    if new_status not in valid_statuses:
        new_status = "active"

    with get_connection(db_path) as conn:
        update_paper_status(conn, paper_id, new_status, manual=True)
        paper = get_paper(conn, paper_id)

    if paper is None:
        from fastapi.responses import HTMLResponse
        return HTMLResponse('<p class="trigger-error">Paper not found.</p>', status_code=404)

    return templates.TemplateResponse(
        request,
        "components/_status_section.html",
        {"paper": paper},
    )
