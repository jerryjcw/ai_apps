# 07 — Scheduler & CLI

## Overview

The CLI is the primary interface for operating the application. It provides commands for manual triggers and a long-running scheduler mode for automated operation. Built with Click.

---

## Module: `src/cli.py`

### CLI Group Structure

```python
import click
import asyncio
import logging
from src.config import load_config, AppConfig
from src.db import init_db, get_connection

@click.group()
@click.option("--config", default="config.toml", help="Path to config file")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx, config, verbose):
    """Scholar Inbox Curate — Track paper citation traction."""
    setup_logging(verbose)
    cfg = load_config(config)
    ensure_data_dir(cfg)
    init_db(cfg.db_path)
    ctx.ensure_object(dict)
    ctx.obj["config"] = cfg
```

---

## Commands

### `scholar-curate ingest`

Run paper ingestion from Scholar Inbox.

```python
@cli.command()
@click.pass_context
def ingest(ctx):
    """Scrape Scholar Inbox for new paper recommendations."""
    config = ctx.obj["config"]
    asyncio.run(run_ingest(config))
```

The ingestion logic lives in `src/ingestion/orchestrate.py` as a public async function, shared between the CLI and the web UI trigger endpoints:

```python
# src/ingestion/orchestrate.py

async def run_ingest(config: AppConfig):
    """Execute a full paper ingestion cycle.

    Called by both the CLI `ingest` command and the web UI
    POST /partials/trigger-ingest endpoint.
    """
    from datetime import datetime
    from src.ingestion.scraper import scrape_recommendations
    from src.ingestion.resolver import resolve_papers, paper_to_dict
    from src.db import (
        get_connection, create_ingestion_run, update_ingestion_run,
        upsert_paper, paper_exists, insert_snapshot, record_scraped_date,
    )
    import httpx

    with get_connection(config.db_path) as conn:
        run_id = create_ingestion_run(conn)

    try:
        # 1. Scrape
        raw_papers = await scrape_recommendations(config)
        logger.info("Scraped %d papers above threshold", len(raw_papers))

        # 2. Resolve (only papers missing semantic_scholar_id need API calls;
        #    most papers already have it from Scholar Inbox)
        async with httpx.AsyncClient() as client:
            resolved = await resolve_papers(client, raw_papers)

        # 3. Store
        new_count = 0
        today = datetime.now().strftime("%Y-%m-%d")
        with get_connection(config.db_path) as conn:
            for paper in resolved:
                if not paper_exists(conn, paper.semantic_scholar_id):
                    upsert_paper(conn, paper_to_dict(paper))
                    insert_snapshot(
                        conn, paper.semantic_scholar_id,
                        paper.citation_count, "semantic_scholar"
                    )
                    new_count += 1

            # Record that today's digest was successfully scraped
            record_scraped_date(conn, today, run_id, len(raw_papers))

            update_ingestion_run(
                conn, run_id,
                papers_found=len(raw_papers),
                papers_ingested=new_count,
                status="completed",
            )

        logger.info("Ingestion complete: %d found, %d new", len(raw_papers), new_count)

    except Exception as e:
        logger.error("Ingestion failed: %s", e)
        with get_connection(config.db_path) as conn:
            update_ingestion_run(conn, run_id, 0, 0, "failed", str(e))
        raise
```

### `scholar-curate poll-citations`

Run citation polling for papers due for a check. Respects the `poll_budget_fraction` setting to cap each cycle to a fraction of non-pruned papers, prioritizing the most overdue papers first.

```python
@cli.command("poll-citations")
@click.pass_context
def poll_citations(ctx):
    """Poll citation counts for tracked papers."""
    config = ctx.obj["config"]
    asyncio.run(run_citation_poll(config, config.db_path))
```

### `scholar-curate prune`

Run prune/promote rules.

```python
@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would happen without making changes")
@click.pass_context
def prune(ctx, dry_run):
    """Run prune/promote rules on tracked papers."""
    config = ctx.obj["config"]
    from src.rules import run_prune_promote, dry_run_prune_promote
    from src.db import get_connection, now_utc

    with get_connection(config.db_path) as conn:
        now = now_utc()
        if dry_run:
            result = dry_run_prune_promote(conn, config, now)
            click.echo(f"[DRY RUN] Would prune {result.papers_pruned}, "
                      f"promote {result.papers_promoted} "
                      f"(of {result.papers_evaluated} evaluated)")
        else:
            result = run_prune_promote(conn, config, now)
            click.echo(f"Pruned {result.papers_pruned}, "
                      f"promoted {result.papers_promoted} "
                      f"(of {result.papers_evaluated} evaluated)")
```

### `scholar-curate stats`

Print database summary.

```python
@cli.command()
@click.pass_context
def stats(ctx):
    """Print database summary statistics."""
    config = ctx.obj["config"]
    from src.db import get_connection, get_paper_count_by_status

    with get_connection(config.db_path) as conn:
        counts = get_paper_count_by_status(conn)
        total = sum(counts.values())

        click.echo(f"Total papers: {total}")
        for status, count in sorted(counts.items()):
            click.echo(f"  {status}: {count}")

        # Additional stats
        trending = conn.execute(
            "SELECT COUNT(*) FROM papers WHERE citation_velocity > 5.0 "
            "AND status IN ('active', 'promoted')"
        ).fetchone()[0]
        click.echo(f"Trending (velocity > 5/month): {trending}")

        recent = conn.execute(
            "SELECT COUNT(*) FROM papers "
            "WHERE julianday('now') - julianday(ingested_at) <= 7"
        ).fetchone()[0]
        click.echo(f"Ingested in last 7 days: {recent}")
```

### `scholar-curate backfill`

Scrape missed digest dates within a configurable lookback window.

```python
@cli.command()
@click.option("--lookback", type=int, default=None,
              help="Days to look back (default: from config)")
@click.option("--threshold", type=float, default=None,
              help="Score threshold override (0.0-1.0)")
@click.pass_context
def backfill(ctx, lookback, threshold):
    """Scrape missed digest dates within the lookback window."""
    config = ctx.obj["config"]
    asyncio.run(run_backfill(config, lookback_days=lookback, score_threshold=threshold))
```

The backfill command:

1. Queries the `scraped_dates` table to find digest dates that have **not** been scraped within the lookback window (default: 30 days, configurable via `backfill_lookback_days`).
2. Iterates day-by-day over the missing dates, calling `scrape_date()` for each.
3. Uses `backfill_score_threshold` (default 0.60) instead of the regular `score_threshold`.
4. Records each successfully scraped date in `scraped_dates` to prevent redundant re-scraping.
5. **Re-resolves dangling papers:** After all dates are scraped, automatically calls `re_resolve_dangling()` to re-attempt S2 resolution for any papers with synthetic fallback IDs (`title:` or `si-` prefix). This ensures that papers which failed resolution due to temporary HTTP errors (429, 4xx, 5xx) are retried on every backfill call, regardless of schedule.
6. Reports a summary: dates checked, dates scraped, papers found, papers new, re-resolved count, and any per-date errors.

Per-date errors are non-fatal — the command continues with remaining dates and reports failures at the end.

Example output:

```
$ scholar-curate backfill --lookback 14
[*] Checking 14-day lookback window...
[*] Found 3 missing dates: 2026-02-15, 2026-02-18, 2026-02-22
[+] 02-15-2026: 8 papers found (5 new)
[+] 02-18-2026: 12 papers found (9 new)
[+] 02-22-2026: 6 papers found (3 new)
[*] Backfill complete: 3 dates scraped, 26 papers found, 17 new
```

### `scholar-curate re-resolve`

Re-attempt Semantic Scholar resolution for papers with synthetic fallback IDs.

```python
@cli.command("re-resolve")
@click.pass_context
def re_resolve(ctx):
    """Re-attempt resolution for papers with fallback IDs."""
    config = ctx.obj["config"]
    from src.ingestion.reresolver import re_resolve_dangling

    result = asyncio.run(re_resolve_dangling(config))
    click.echo(f"Dangling papers:  {result.total_dangling}")
    click.echo(f"Resolved:         {result.resolved}")
    click.echo(f"Duplicates:       {result.already_exists}")
    click.echo(f"Still unresolved: {result.still_unresolved}")
    if result.errors:
        click.echo(f"Errors ({len(result.errors)}):")
        for err in result.errors:
            click.echo(f"  - {err}")
```

This command is also called automatically at the end of `run_backfill()`, so papers with synthetic IDs are re-resolved on every backfill cycle without manual intervention.

### `scholar-curate serve`

Start the web UI.

```python
@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind host")
@click.option("--port", default=8000, type=int, help="Bind port")
@click.pass_context
def serve(ctx, host, port):
    """Start the web UI server."""
    import uvicorn
    from src.web.app import create_app

    config = ctx.obj["config"]
    app = create_app(config)
    uvicorn.run(app, host=host, port=port)
```

### `scholar-curate run`

Start the background scheduler for automated operation.

```python
@cli.command()
@click.pass_context
def run(ctx):
    """Start the scheduler for automated ingestion and polling."""
    config = ctx.obj["config"]
    from src.scheduler import start_scheduler
    start_scheduler(config)
```

### `scholar-curate collect-citations`

Collect citation data for papers that have never been polled (e.g. backfilled papers).

```python
@cli.command("collect-citations")
@click.pass_context
def collect_citations(ctx):
    """Collect citation data for papers that have never been polled."""
    from src.citations.poller import collect_citations_for_unpolled

    config = ctx.obj["config"]
    count = asyncio.run(collect_citations_for_unpolled(config, config.db_path))
    click.echo(f"Citation collection complete: {count} unpolled papers processed")
```

### `scholar-curate grab-session`

Extract the session cookie from the user's Chrome browser (no browser interaction needed).

```python
@cli.command("grab-session")
@click.pass_context
def grab_session(ctx):
    """Extract session cookie from Chrome browser."""
    from src.ingestion.scraper import extract_chrome_session

    config = ctx.obj["config"]
    asyncio.run(extract_chrome_session(config))
    click.echo("Session cookie extracted from Chrome and saved.")
```

### `scholar-curate login`

Launch a headed browser for manual Turnstile authentication. Use this when cookies have expired and you need to re-authenticate without deleting the browser profile.

```python
@cli.command()
@click.pass_context
def login(ctx):
    """Launch headed browser for manual Scholar Inbox authentication."""
    from src.ingestion.scraper import manual_login

    config = ctx.obj["config"]
    asyncio.run(manual_login(config))
    click.echo("Login successful. Cookies saved.")
```

### `scholar-curate reset-session`

Delete cookies and browser profile to force re-authentication on next use.

```python
@cli.command("reset-session")
@click.confirmation_option(prompt="Delete browser session and cookies? You'll need to re-authenticate.")
@click.pass_context
def reset_session(ctx):
    """Delete cookies and browser profile to force re-authentication."""
    import shutil

    config = ctx.obj["config"]
    cookies_path = Path(config.db_path).parent / "cookies.json"
    if cookies_path.exists():
        cookies_path.unlink()
        click.echo(f"Cookies deleted: {cookies_path}")

    profile = Path(config.browser.profile_dir)
    if profile.exists():
        shutil.rmtree(profile)
        click.echo(f"Browser profile deleted: {profile}")

    click.echo("Browser session cleared.")
```

---

## Module: `src/scheduler.py`

### APScheduler Setup

```python
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
import logging

logger = logging.getLogger(__name__)


def start_scheduler(config: AppConfig):
    """Start the blocking scheduler with configured cron jobs.

    Runs indefinitely until interrupted (Ctrl+C).
    """
    scheduler = BlockingScheduler()

    # Parse cron expressions from config
    ingest_cron = _parse_cron(config.ingestion.schedule_cron)
    poll_cron = _parse_cron(config.citations.poll_schedule_cron)

    # Add jobs
    scheduler.add_job(
        _job_ingest,
        trigger=ingest_cron,
        args=[config],
        id="ingest",
        name="Paper Ingestion",
        misfire_grace_time=3600,  # 1 hour grace period
    )

    scheduler.add_job(
        _job_poll_citations,
        trigger=poll_cron,
        args=[config],
        id="poll_citations",
        name="Citation Polling",
        misfire_grace_time=3600,
    )

    logger.info("Scheduler started. Ingestion: %s, Polling: %s",
                config.ingestion.schedule_cron,
                config.citations.poll_schedule_cron)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
        scheduler.shutdown()
```

### Job Wrapper Functions

Each job runs in its own async event loop (since APScheduler's `BlockingScheduler` runs jobs in threads):

```python
def _job_ingest(config: AppConfig):
    """Scheduled job: run paper ingestion."""
    logger.info("Scheduled ingestion starting")
    try:
        asyncio.run(run_ingest(config))
        logger.info("Scheduled ingestion completed")
    except Exception as e:
        logger.error("Scheduled ingestion failed: %s", e)


def _job_poll_citations(config: AppConfig):
    """Scheduled job: run citation polling + prune/promote."""
    logger.info("Scheduled citation poll starting")
    try:
        asyncio.run(run_citation_poll(config, config.db_path))
        # Run rules after polling
        with get_connection(config.db_path) as conn:
            result = run_prune_promote(conn, config, now_utc())
            logger.info("Rules: pruned=%d, promoted=%d",
                       result.papers_pruned, result.papers_promoted)
        logger.info("Scheduled citation poll completed")
    except Exception as e:
        logger.error("Scheduled citation poll failed: %s", e)
```

### Cron Expression Parsing

```python
def _parse_cron(cron_expr: str) -> CronTrigger:
    """Parse a standard 5-field cron expression into an APScheduler CronTrigger.

    Format: minute hour day_of_month month day_of_week
    Example: "0 8 * * 1" = every Monday at 8:00 AM
    """
    parts = cron_expr.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expr}")

    return CronTrigger(
        minute=parts[0],
        hour=parts[1],
        day=parts[2],
        month=parts[3],
        day_of_week=parts[4],
    )
```

### Misfire Grace Time

`misfire_grace_time=3600` means if the system was asleep/off when a scheduled job was supposed to run, it will still run when the system wakes up — as long as it's within 1 hour of the scheduled time. Jobs that miss their window by more than 1 hour are skipped entirely (they'll run at the next scheduled time).

---

## Concurrent Scheduler + Web Server

For users who want both the scheduler and web UI running simultaneously, the `run` command can optionally start the web server in a background thread:

```python
@cli.command()
@click.option("--with-web", is_flag=True, help="Also start the web UI")
@click.option("--port", default=8000, type=int, help="Web UI port")
@click.pass_context
def run(ctx, with_web, port):
    """Start the scheduler for automated ingestion and polling."""
    config = ctx.obj["config"]

    if with_web:
        import threading
        import uvicorn
        from src.web.app import create_app

        app = create_app(config)
        web_thread = threading.Thread(
            target=uvicorn.run,
            kwargs={"app": app, "host": "127.0.0.1", "port": port},
            daemon=True,
        )
        web_thread.start()
        logger.info("Web UI started on http://127.0.0.1:%d", port)

    start_scheduler(config)
```

---

## CLI Help Output

```
$ scholar-curate --help
Usage: scholar-curate [OPTIONS] COMMAND [ARGS]...

  Scholar Inbox Curate — track citation traction for recommended papers.

Options:
  -v, --verbose  Enable debug logging
  --config TEXT   Path to config.toml  [default: config.toml]
  --help          Show this message and exit.

Commands:
  backfill           Scrape missed digest dates within the lookback window.
  collect-citations  Collect citation data for papers that have never been polled.
  grab-session       Extract session cookie from Chrome browser.
  ingest             Scrape Scholar Inbox for new paper recommendations.
  login              Launch headed browser for manual Scholar Inbox authentication.
  poll-citations     Poll citation counts for tracked papers.
  prune              Run prune/promote rules on tracked papers.
  re-resolve         Re-attempt S2 resolution for papers with fallback IDs.
  reset-session      Delete cookies and browser profile to force re-authentication.
  run                Start the scheduler for automated ingestion and polling.
  serve              Start the web UI server.
  stats              Print database summary statistics.
```
