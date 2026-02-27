"""Click CLI entry point for Scholar Inbox Curate."""

import asyncio
import logging
from pathlib import Path

import click

from src.config import AppConfig, load_config
from src.db import init_db


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def ensure_data_dir(config: AppConfig) -> None:
    Path(config.db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(config.browser.profile_dir).mkdir(parents=True, exist_ok=True)


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
@click.option(
    "--config",
    "config_path",
    default="config.toml",
    help="Path to config.toml",
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool, config_path: str) -> None:
    """Scholar Inbox Curate — track citation traction for recommended papers."""
    setup_logging(verbose)
    config = load_config(config_path=config_path)
    ensure_data_dir(config)
    init_db(config.db_path)
    ctx.ensure_object(dict)
    ctx.obj["config"] = config


@cli.command()
@click.pass_context
def ingest(ctx: click.Context) -> None:
    """Scrape Scholar Inbox for new paper recommendations."""
    from src.ingestion.orchestrate import run_ingest

    config: AppConfig = ctx.obj["config"]
    result = asyncio.run(run_ingest(config))
    click.echo(
        f"Ingestion complete: {result['papers_found']} found, "
        f"{result['papers_ingested']} new"
    )


@cli.command("poll-citations")
@click.pass_context
def poll_citations(ctx: click.Context) -> None:
    """Poll citation counts for tracked papers."""
    from src.citations.poller import run_citation_poll

    config: AppConfig = ctx.obj["config"]
    count = asyncio.run(run_citation_poll(config, config.db_path))
    click.echo(f"Citation poll complete: {count} papers processed")


@cli.command()
@click.option(
    "--dry-run", is_flag=True, help="Show what would happen without making changes"
)
@click.pass_context
def prune(ctx: click.Context, dry_run: bool) -> None:
    """Run prune/promote rules on tracked papers."""
    from src.db import get_connection, now_utc
    from src.rules import dry_run_prune_promote, run_prune_promote

    config: AppConfig = ctx.obj["config"]
    with get_connection(config.db_path) as conn:
        now = now_utc()
        if dry_run:
            result = dry_run_prune_promote(conn, config, now)
            click.echo(
                f"[DRY RUN] Would prune {result.papers_pruned}, "
                f"promote {result.papers_promoted} "
                f"(of {result.papers_evaluated} evaluated)"
            )
        else:
            result = run_prune_promote(conn, config, now)
            click.echo(
                f"Pruned {result.papers_pruned}, "
                f"promoted {result.papers_promoted} "
                f"(of {result.papers_evaluated} evaluated)"
            )


@cli.command()
@click.pass_context
def stats(ctx: click.Context) -> None:
    """Print database summary statistics."""
    from src.db import get_connection, get_paper_count_by_status

    config: AppConfig = ctx.obj["config"]
    with get_connection(config.db_path) as conn:
        counts = get_paper_count_by_status(conn)
        total = sum(counts.values())

        click.echo(f"Total papers: {total}")
        for status, count in sorted(counts.items()):
            click.echo(f"  {status}: {count}")

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


@cli.command()
@click.option(
    "--lookback",
    type=int,
    default=None,
    help="Number of days to look back (default: from config).",
)
@click.option(
    "--threshold",
    type=float,
    default=None,
    help="Score threshold 0.0-1.0 (default: from config).",
)
@click.pass_context
def backfill(ctx: click.Context, lookback: int | None, threshold: float | None) -> None:
    """Scrape missed digest dates within the lookback window."""
    from src.ingestion.backfill import run_backfill

    config: AppConfig = ctx.obj["config"]
    result = asyncio.run(
        run_backfill(config, lookback_days=lookback, score_threshold=threshold)
    )

    click.echo(f"Dates checked:   {result.dates_checked}")
    click.echo(f"Dates scraped:   {result.dates_scraped}")
    click.echo(f"Papers found:    {result.total_papers_found}")
    click.echo(f"Papers ingested: {result.total_papers_ingested}")
    if result.errors:
        click.echo(f"Errors ({len(result.errors)}):")
        for err in result.errors:
            click.echo(f"  - {err}")


@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind host")
@click.option("--port", default=8000, type=int, help="Bind port")
@click.pass_context
def serve(ctx: click.Context, host: str, port: int) -> None:
    """Start the web UI server."""
    import uvicorn
    from src.web.app import create_app

    config: AppConfig = ctx.obj["config"]
    app = create_app(config)
    uvicorn.run(app, host=host, port=port)


@cli.command()
@click.option("--with-web", is_flag=True, help="Also start the web UI")
@click.option("--port", default=8000, type=int, help="Web UI port")
@click.pass_context
def run(ctx: click.Context, with_web: bool, port: int) -> None:
    """Start the scheduler for automated ingestion and polling."""
    config: AppConfig = ctx.obj["config"]

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
        click.echo(f"Web UI started on http://127.0.0.1:{port}")

    from src.scheduler import start_scheduler

    start_scheduler(config)


@cli.command()
@click.pass_context
def login(ctx: click.Context) -> None:
    """Launch headed browser for manual Scholar Inbox authentication."""
    from src.ingestion.scraper import manual_login

    config: AppConfig = ctx.obj["config"]
    asyncio.run(manual_login(config))
    click.echo("Login successful. Cookies saved.")


@cli.command("reset-session")
@click.confirmation_option(
    prompt="Delete browser session and cookies? You'll need to re-authenticate."
)
@click.pass_context
def reset_session(ctx: click.Context) -> None:
    """Delete cookies and browser profile to force re-authentication."""
    import shutil

    config: AppConfig = ctx.obj["config"]

    # Delete cookies file
    cookies_path = Path(config.db_path).parent / "cookies.json"
    if cookies_path.exists():
        cookies_path.unlink()
        click.echo(f"Cookies deleted: {cookies_path}")

    # Delete browser profile
    profile = Path(config.browser.profile_dir)
    if profile.exists():
        shutil.rmtree(profile)
        click.echo(f"Browser profile deleted: {profile}")

    click.echo("Browser session cleared.")
