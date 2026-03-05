#!/usr/bin/env python3
"""End-to-end test: scrape Oct 1-7 2025, poll citations, report results.

Authentication strategy:
  1. Try to load session cookie from e2e/scrape_test/cookies.json
  2. If not found, try browser_cookie3 (reads from Chrome)
  3. If neither works, open a headed Playwright browser for manual login

Run from the project root:
    cd applications/scholar_inbox_curate
    .venv/bin/python e2e/scrape_test/run_e2e.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

import httpx

from src.config import load_config
from src.db import (
    get_connection,
    init_db,
    record_scraped_date,
    upsert_paper,
    now_utc,
)
from src.ingestion.scraper import _parse_papers, RawPaper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("e2e")

# ── Config ──────────────────────────────────────────────────────────────
E2E_CONFIG_PATH = "e2e/scrape_test/config.toml"
API_URL = "https://api.scholar-inbox.com"
START_DATE = date(2025, 10, 1)
END_DATE = date(2025, 10, 7)
COOKIES_FILE = Path("e2e/scrape_test/cookies.json")


# ── Authentication ──────────────────────────────────────────────────────
def _load_saved_cookie() -> str | None:
    """Load session cookie from saved cookies.json."""
    if not COOKIES_FILE.exists():
        return None
    try:
        cookies = json.loads(COOKIES_FILE.read_text())
        for c in cookies:
            if c.get("name") == "session":
                return c["value"]
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _load_chrome_cookie() -> str | None:
    """Try to get session cookie from Chrome via browser_cookie3."""
    try:
        import browser_cookie3
        cj = browser_cookie3.chrome(domain_name="api.scholar-inbox.com")
        for c in cj:
            if c.name == "session":
                return c.value
    except Exception as exc:
        logger.debug("browser_cookie3 failed: %s", exc)
    return None


async def _playwright_login(config) -> str:
    """Open a headed browser for manual login. Returns session cookie value."""
    from playwright.async_api import async_playwright

    logger.info("Opening browser for manual login...")
    logger.info("Please log in and solve the CAPTCHA. The browser will close automatically.")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://www.scholar-inbox.com/login")

        # Wait for the user to complete login (session cookie appears)
        logger.info("Waiting up to 120s for login to complete...")
        session_value = None
        for _ in range(120):
            await page.wait_for_timeout(1000)
            cookies = await context.cookies()
            for c in cookies:
                if c["name"] == "session":
                    session_value = c["value"]
                    break
            if session_value:
                break

        await browser.close()

        if not session_value:
            raise RuntimeError("Login timed out — no session cookie found")

    # Save cookies for future runs
    COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIES_FILE.write_text(json.dumps(
        [{"name": "session", "value": session_value, "domain": "api.scholar-inbox.com"}],
        indent=2,
    ))
    logger.info("Session cookie saved to %s", COOKIES_FILE)
    return session_value


async def _verify_session(cookie: str) -> bool:
    """Check if the session cookie is still valid."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{API_URL}/api/session_info",
                cookies={"session": cookie},
            )
            return resp.json().get("is_logged_in", False)
    except Exception:
        return False


async def get_session_cookie(config) -> str:
    """Get a valid session cookie, trying multiple strategies."""
    # Strategy 1: Saved cookies
    cookie = _load_saved_cookie()
    if cookie:
        if await _verify_session(cookie):
            logger.info("Using saved session cookie")
            return cookie
        logger.info("Saved cookie expired")

    # Strategy 2: Chrome browser cookies
    cookie = _load_chrome_cookie()
    if cookie:
        if await _verify_session(cookie):
            logger.info("Using Chrome session cookie")
            # Save for future runs
            COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
            COOKIES_FILE.write_text(json.dumps(
                [{"name": "session", "value": cookie, "domain": "api.scholar-inbox.com"}],
                indent=2,
            ))
            return cookie
        logger.info("Chrome cookie expired")

    # Strategy 3: Playwright headed login
    return await _playwright_login(config)


# ── Helpers ─────────────────────────────────────────────────────────────
def _date_to_api_format(d: date) -> str:
    return d.strftime("%m-%d-%Y")


def _weekdays(start: date, end: date) -> list[date]:
    """Return weekdays (Mon-Fri) in [start, end] inclusive."""
    result = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            result.append(d)
        d += timedelta(days=1)
    return result


def _raw_paper_to_db_dict(paper: RawPaper, digest_date_iso: str) -> dict:
    paper_id = paper.semantic_scholar_id or paper.arxiv_id or f"si-{paper.paper_id}"
    return {
        "id": paper_id,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "url": paper.scholar_inbox_url,
        "arxiv_id": paper.arxiv_id,
        "venue": paper.venue,
        "year": paper.year,
        "published_date": paper.publication_date,
        "scholar_inbox_score": paper.score,
        "ingested_at": now_utc(),
    }


# ── Step 1: Scrape ─────────────────────────────────────────────────────
async def step_scrape(config, session_cookie: str) -> int:
    """Scrape each weekday from Oct 1-7 2025 and store papers."""
    dates = _weekdays(START_DATE, END_DATE)
    logger.info("Will scrape %d weekdays: %s .. %s", len(dates), dates[0], dates[-1])

    total_found = 0
    total_ingested = 0
    score_threshold = config.ingestion.score_threshold

    async with httpx.AsyncClient(
        cookies={"session": session_cookie},
        timeout=30,
    ) as client:
        for d in dates:
            api_date = _date_to_api_format(d)
            iso_date = d.isoformat()
            logger.info("── Scraping %s (%s) ──", iso_date, api_date)

            try:
                resp = await client.get(f"{API_URL}/api/", params={"date": api_date})
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.error("  FAILED to fetch: %s", exc)
                continue

            papers = _parse_papers(data, score_threshold)
            total_found += len(papers)
            ingested = 0

            with get_connection(config.db_path) as conn:
                for paper in papers:
                    db_dict = _raw_paper_to_db_dict(paper, iso_date)
                    was_new = upsert_paper(conn, db_dict)
                    if was_new:
                        ingested += 1
                record_scraped_date(conn, iso_date)

            total_ingested += ingested
            logger.info("  Found %d papers (>= %.0f%%), %d new",
                        len(papers), score_threshold * 100, ingested)

    logger.info(
        "Scrape complete: %d total found, %d total ingested", total_found, total_ingested
    )
    return total_ingested


# ── Step 2: Poll Citations ──────────────────────────────────────────────
async def step_poll_citations(config) -> int:
    """Poll citation counts for all ingested papers."""
    from src.citations.poller import run_citation_poll

    logger.info("── Polling citations ──")
    count = await run_citation_poll(config, config.db_path)
    logger.info("Citation poll: %d papers processed", count)
    return count


# ── Step 3: Report ──────────────────────────────────────────────────────
def step_report(config):
    """Print a summary report of the DB."""
    with get_connection(config.db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]

        status_rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM papers GROUP BY status"
        ).fetchall()
        status_counts = {r["status"]: r["cnt"] for r in status_rows}

        cited = conn.execute(
            "SELECT COUNT(*) FROM papers WHERE citation_count > 0"
        ).fetchone()[0]

        cite_stats = conn.execute("""\
            SELECT
                MIN(citation_count) as min_cites,
                MAX(citation_count) as max_cites,
                AVG(citation_count) as avg_cites,
                SUM(citation_count) as total_cites
            FROM papers
            WHERE citation_count > 0
        """).fetchone()

        vel_stats = conn.execute("""\
            SELECT
                MIN(citation_velocity) as min_vel,
                MAX(citation_velocity) as max_vel,
                AVG(citation_velocity) as avg_vel
            FROM papers
            WHERE citation_velocity IS NOT NULL AND citation_velocity > 0
        """).fetchone()

        top_cited = conn.execute("""\
            SELECT title, citation_count, citation_velocity, status, year
            FROM papers
            WHERE citation_count > 0
            ORDER BY citation_count DESC
            LIMIT 10
        """).fetchall()

        top_velocity = conn.execute("""\
            SELECT title, citation_count, citation_velocity, status, year
            FROM papers
            WHERE citation_velocity IS NOT NULL AND citation_velocity > 0
            ORDER BY citation_velocity DESC
            LIMIT 10
        """).fetchall()

        score_dist = conn.execute("""\
            SELECT
                CASE
                    WHEN scholar_inbox_score >= 90 THEN '90-100'
                    WHEN scholar_inbox_score >= 80 THEN '80-89'
                    WHEN scholar_inbox_score >= 70 THEN '70-79'
                    WHEN scholar_inbox_score >= 60 THEN '60-69'
                    ELSE 'below 60'
                END as score_range,
                COUNT(*) as cnt
            FROM papers
            GROUP BY score_range
            ORDER BY score_range DESC
        """).fetchall()

        scraped = conn.execute(
            "SELECT digest_date FROM scraped_dates ORDER BY digest_date"
        ).fetchall()

    # ── Print report ────────────────────────────────────────────────
    sep = "=" * 60
    print(f"\n{sep}")
    print("  E2E SCRAPE TEST REPORT")
    print(f"  Date range: {START_DATE} to {END_DATE}")
    print(sep)

    print(f"\n  DB Overview")
    print(f"  {'Total papers:':<25} {total}")
    for status, cnt in sorted(status_counts.items()):
        print(f"  {status + ':':<25} {cnt}")
    print(f"  {'Papers with citations:':<25} {cited}")
    print(f"  {'Scraped dates:':<25} {len(scraped)}")
    for row in scraped:
        print(f"    - {row['digest_date']}")

    print(f"\n  Score Distribution")
    for row in score_dist:
        bar = "#" * min(row["cnt"], 50)
        print(f"  {row['score_range']:>10}: {row['cnt']:>4}  {bar}")

    if cite_stats and cite_stats["total_cites"]:
        print(f"\n  Citation Statistics")
        print(f"  {'Min citations:':<25} {cite_stats['min_cites']}")
        print(f"  {'Max citations:':<25} {cite_stats['max_cites']}")
        print(f"  {'Avg citations:':<25} {cite_stats['avg_cites']:.1f}")
        print(f"  {'Total citations:':<25} {cite_stats['total_cites']}")
    else:
        print(f"\n  Citation Statistics")
        print("  No citation data collected yet.")

    if vel_stats and vel_stats["max_vel"]:
        print(f"\n  Velocity Statistics")
        print(f"  {'Min velocity:':<25} {vel_stats['min_vel']:.2f}")
        print(f"  {'Max velocity:':<25} {vel_stats['max_vel']:.2f}")
        print(f"  {'Avg velocity:':<25} {vel_stats['avg_vel']:.2f}")

    if top_cited:
        print(f"\n  Top 10 by Citations")
        for i, row in enumerate(top_cited, 1):
            title = row["title"][:55] + "..." if len(row["title"]) > 55 else row["title"]
            print(f"  {i:>2}. [{row['citation_count']:>5} cites] {title}")

    if top_velocity:
        print(f"\n  Top 10 by Velocity")
        for i, row in enumerate(top_velocity, 1):
            title = row["title"][:55] + "..." if len(row["title"]) > 55 else row["title"]
            print(f"  {i:>2}. [{row['citation_velocity']:>7.2f}/mo] {title}")

    print(f"\n{sep}")
    print(f"  DB path: {config.db_path}")
    print(f"{sep}\n")


# ── Main ────────────────────────────────────────────────────────────────
async def main():
    config = load_config(E2E_CONFIG_PATH)
    logger.info("Config loaded: db=%s", config.db_path)

    # Initialize fresh DB
    db_path = Path(config.db_path)
    if db_path.exists():
        db_path.unlink()
        logger.info("Removed existing DB")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(config.db_path)
    logger.info("DB initialized at %s", config.db_path)

    # Authenticate
    session_cookie = await get_session_cookie(config)
    logger.info("Session authenticated")

    # Step 1: Scrape Oct 1-7 2025
    await step_scrape(config, session_cookie)

    # Step 2: Poll citations
    await step_poll_citations(config)

    # Step 3: Report
    step_report(config)


if __name__ == "__main__":
    asyncio.run(main())
