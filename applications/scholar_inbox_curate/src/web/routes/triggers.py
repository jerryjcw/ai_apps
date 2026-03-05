"""HTMX trigger route handlers for manual ingestion operations."""

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.config import AppConfig
from src.db import get_connection, get_recent_ingestion_runs, now_utc
from src.web.filters import format_duration, relative_date


def _render_run_history_oob(runs: list[dict]) -> str:
    """Render run history tbody with hx-swap-oob for out-of-band update."""
    rows = ""
    for r in runs:
        status_class = f"run-status-{r['status']}"
        error_html = ""
        if r.get("error_message"):
            error_html = (
                f'<details><summary><small>Error details</small></summary>'
                f'<small><code>{r["error_message"]}</code></small></details>'
            )
        rows += (
            f'<tr>'
            f'<td>{relative_date(r["started_at"])}</td>'
            f'<td>{format_duration(r["started_at"], r.get("finished_at"))}</td>'
            f'<td>{r["papers_found"]}</td>'
            f'<td>{r["papers_ingested"]}</td>'
            f'<td><span class="{status_class}">{r["status"].capitalize()}</span>{error_html}</td>'
            f'</tr>'
        )
    return f'<tbody id="run-history-body" hx-swap-oob="innerHTML">{rows}</tbody>'


async def handle_trigger_ingest(
    request: Request,
    config: AppConfig,
    db_path: str,
    templates: Jinja2Templates,
) -> HTMLResponse:
    """Trigger paper ingestion (scrape + resolve + store)."""
    try:
        from src.ingestion.orchestrate import run_ingest

        result = await run_ingest(config)

        with get_connection(db_path) as conn:
            all_runs = get_recent_ingestion_runs(conn, limit=20)

        found = result.get("papers_found", 0)
        ingested = result.get("papers_ingested", 0)

        return HTMLResponse(
            f'<p class="trigger-success">Done. Found {found} papers, ingested {ingested} new.</p>'
            + _render_run_history_oob(all_runs)
        )
    except Exception as e:
        return HTMLResponse(f'<p class="trigger-error">Failed: {e}</p>')


async def handle_trigger_poll(
    request: Request,
    config: AppConfig,
    db_path: str,
    templates: Jinja2Templates,
) -> HTMLResponse:
    """Trigger citation polling for papers due for a poll."""
    try:
        from src.citations.poller import run_citation_poll

        count = await run_citation_poll(config, db_path)
        return HTMLResponse(f'<p class="trigger-success">Done. Updated {count} papers.</p>')
    except Exception as e:
        return HTMLResponse(f'<p class="trigger-error">Failed: {e}</p>')


async def handle_trigger_rules(
    request: Request,
    config: AppConfig,
    db_path: str,
    templates: Jinja2Templates,
) -> HTMLResponse:
    """Trigger prune/promote rules evaluation."""
    try:
        from src.rules import run_prune_promote

        with get_connection(db_path) as conn:
            result = run_prune_promote(conn, config, now_utc())

        return HTMLResponse(
            f'<p class="trigger-success">'
            f'Done. Pruned {result.papers_pruned}, promoted {result.papers_promoted} '
            f'(of {result.papers_evaluated} evaluated).'
            f'</p>'
        )
    except Exception as e:
        return HTMLResponse(f'<p class="trigger-error">Failed: {e}</p>')


async def handle_trigger_backfill(
    request: Request,
    config: AppConfig,
    db_path: str,
    templates: Jinja2Templates,
) -> HTMLResponse:
    """Trigger backfill for missed digest dates."""
    try:
        from src.ingestion.backfill import run_backfill

        result = await run_backfill(config)
        return HTMLResponse(
            f'<p class="trigger-success">Done. Backfilled {result.dates_processed} dates, '
            f'ingested {result.papers_ingested} new papers.</p>'
        )
    except Exception as e:
        return HTMLResponse(f'<p class="trigger-error">Failed: {e}</p>')


async def handle_trigger_collect(
    request: Request,
    config: AppConfig,
    db_path: str,
    templates: Jinja2Templates,
) -> HTMLResponse:
    """Trigger citation collection for papers never polled."""
    try:
        from src.citations.poller import collect_citations_for_unpolled

        count = await collect_citations_for_unpolled(config, db_path)
        return HTMLResponse(
            f'<p class="trigger-success">Done. Collected citations for {count} papers.</p>'
        )
    except Exception as e:
        return HTMLResponse(f'<p class="trigger-error">Failed: {e}</p>')
