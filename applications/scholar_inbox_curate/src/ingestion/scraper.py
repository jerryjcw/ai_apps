"""Scholar Inbox scraper — fetches recommended papers via the JSON API.

Handles authentication (cookie-based), session management, and paper parsing.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.constants import (
    SCHOLAR_INBOX_API_URL as API_URL,
    COOKIES_FILENAME,
    DEFAULT_TIMEOUT,
)
from src.errors import (
    ScraperError,
    CloudflareTimeoutError,
    LoginError,
    SessionExpiredError,
    APIError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RawPaper:
    """A paper as returned by the Scholar Inbox API, lightly parsed."""

    title: str
    authors: list[str]
    abstract: str
    score: float
    arxiv_id: str | None = None
    semantic_scholar_id: str | None = None
    paper_id: int | None = None
    venue: str | None = None
    year: int | None = None
    category: str | None = None
    scholar_inbox_url: str | None = None
    publication_date: str | None = None


# ---------------------------------------------------------------------------
# Cookie management
# ---------------------------------------------------------------------------

def _cookies_path(data_dir: str) -> Path:
    return Path(data_dir) / COOKIES_FILENAME


def save_cookies(cookies: list[dict], data_dir: str) -> None:
    """Persist browser cookies to ``data/cookies.json``."""
    path = _cookies_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cookies, indent=2))
    logger.info("Saved %d cookies to %s", len(cookies), path)


def load_session_cookie(data_dir: str) -> str | None:
    """Load the ``session`` cookie value from disk, or *None* if absent."""
    path = _cookies_path(data_dir)
    if not path.exists():
        return None
    try:
        cookies = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        logger.warning("Could not read cookies from %s", path)
        return None
    return _extract_session_cookie(cookies)


def _extract_session_cookie(cookies: list[dict]) -> str | None:
    """Find the ``session`` cookie value in a list of cookie dicts."""
    for c in cookies:
        if c.get("name") == "session":
            return c.get("value")
    return None


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

async def verify_session(client: httpx.AsyncClient, session_cookie: str) -> bool:
    """Return *True* if *session_cookie* is still valid on the API."""
    try:
        resp = await client.get(
            f"{API_URL}/api/session_info",
            cookies={"session": session_cookie},
        )
        resp.raise_for_status()
        return resp.json().get("is_logged_in", False)
    except (httpx.HTTPError, ValueError):
        return False


async def manual_login(config) -> list[dict]:
    """Open a headed browser for the user to log in and solve Turnstile.

    Pre-fills email/password from *config.secrets*, waits for the session
    cookie, then returns the browser cookies as a list of dicts.
    """
    from playwright.async_api import async_playwright

    email = config.secrets.scholar_inbox_email
    password = config.secrets.scholar_inbox_password

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://www.scholar-inbox.com/login")

        # Pre-fill credentials if available
        if email:
            await page.fill('input[name="email"], input[type="email"]', email)
        if password:
            await page.fill('input[name="password"], input[type="password"]', password)

        logger.info("Waiting for user to solve Turnstile and log in...")

        # Wait for session cookie to appear (max 120s)
        try:
            await page.wait_for_url(
                "**/scholar-inbox.com/**",
                timeout=120_000,
            )
            # Give some time for cookies to settle
            await page.wait_for_timeout(2000)
        except Exception as exc:
            await browser.close()
            raise CloudflareTimeoutError(
                "Timed out waiting for login / Turnstile to complete"
            ) from exc

        cookies = await context.cookies()
        cookie_dicts = [
            {"name": c["name"], "value": c["value"], "domain": c.get("domain", "")}
            for c in cookies
        ]

        session_value = _extract_session_cookie(cookie_dicts)
        if not session_value:
            await browser.close()
            raise LoginError("Login completed but no session cookie was found")

        await browser.close()

    # Persist cookies
    data_dir = str(Path(config.db_path).parent)
    save_cookies(cookie_dicts, data_dir)

    return cookie_dicts


async def extract_chrome_session(config) -> str:
    """Extract session cookie from Chrome and save to cookies.json.

    Uses browser_cookie3 to read Chrome's cookie store, verifies the
    cookie is valid, and persists it for future use.
    Raises LoginError if no valid cookie found.
    """
    try:
        import browser_cookie3
    except ImportError as exc:
        raise LoginError(
            "browser_cookie3 is not installed. "
            "Install it with: pip install browser-cookie3"
        ) from exc

    try:
        cj = browser_cookie3.chrome(domain_name="api.scholar-inbox.com")
    except Exception as exc:
        raise LoginError(f"Failed to read Chrome cookies: {exc}") from exc

    session_value = None
    for c in cj:
        if c.name == "session":
            session_value = c.value
            break

    if not session_value:
        raise LoginError(
            "No 'session' cookie found in Chrome for api.scholar-inbox.com. "
            "Make sure you are logged into Scholar Inbox in Chrome."
        )

    # Verify the cookie is still valid
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        if not await verify_session(client, session_value):
            raise LoginError(
                "Chrome session cookie found but it has expired. "
                "Please log into Scholar Inbox in Chrome again."
            )

    # Persist the cookie
    data_dir = str(Path(config.db_path).parent)
    cookie_dicts = [
        {"name": "session", "value": session_value, "domain": "api.scholar-inbox.com"}
    ]
    save_cookies(cookie_dicts, data_dir)
    logger.info("Extracted and saved valid session cookie from Chrome")

    return session_value


async def ensure_session(config) -> str:
    """Return a valid session cookie, re-authenticating if necessary.

    Fallback order: saved cookies → Chrome extraction → Playwright manual login.
    """
    data_dir = str(Path(config.db_path).parent)
    cookie = load_session_cookie(data_dir)

    if cookie:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            if await verify_session(client, cookie):
                logger.debug("Existing session cookie is valid")
                return cookie
        logger.info("Session cookie expired, trying Chrome extraction...")

    # Try Chrome cookie extraction before falling back to Playwright
    try:
        return await extract_chrome_session(config)
    except LoginError as exc:
        logger.info("Chrome extraction failed (%s), falling back to manual login...", exc)

    cookies = await manual_login(config)
    session = _extract_session_cookie(cookies)
    if not session:
        raise LoginError("Re-authentication did not yield a session cookie")
    return session


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

async def _fetch_papers(client: httpx.AsyncClient, params: dict) -> dict:
    """GET ``/api/`` and return the JSON response body."""
    try:
        resp = await client.get(f"{API_URL}/api/", params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        raise APIError(f"API returned HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise APIError(f"API request failed: {exc}") from exc
    except ValueError as exc:
        raise APIError("API returned invalid JSON") from exc


def _extract_year(display_venue: str | None) -> int | None:
    """Extract a 4-digit year from a venue string like ``'ArXiv 2026 (January 13)'``."""
    if not display_venue:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", display_venue)
    return int(match.group()) if match else None


def _epoch_ms_to_iso(epoch_ms) -> str | None:
    """Convert an epoch-millisecond timestamp to an ISO 8601 date string."""
    if epoch_ms is None:
        return None
    try:
        ts = int(epoch_ms) / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, TypeError, OSError):
        return None


def _parse_papers(data: dict, score_threshold: float) -> list[RawPaper]:
    """Parse the ``digest_df`` array, filtering by *score_threshold* (0.0-1.0 decimal scale).

    Args:
        data: Full API response dict
        score_threshold: Minimum ranking_score (0.0-1.0). API returns scores in this decimal range.
    """
    threshold = score_threshold  # score_threshold is already in decimal scale
    papers: list[RawPaper] = []

    for entry in data.get("digest_df", []):
        ranking_score = entry.get("ranking_score") or 0.0
        if ranking_score < threshold:
            continue

        authors_raw = entry.get("authors", "")
        authors = [a.strip() for a in authors_raw.split(",") if a.strip()] if authors_raw else []

        display_venue = entry.get("display_venue")

        arxiv_id = entry.get("arxiv_id")
        scholar_inbox_url = None
        if arxiv_id:
            scholar_inbox_url = f"https://www.scholar-inbox.com/paper/{arxiv_id}"

        papers.append(
            RawPaper(
                title=entry.get("title", ""),
                authors=authors,
                abstract=entry.get("abstract", ""),
                score=round(ranking_score * 100, 1),
                arxiv_id=arxiv_id,
                semantic_scholar_id=entry.get("semantic_scholar_id"),
                paper_id=entry.get("paper_id"),
                venue=display_venue,
                year=_extract_year(display_venue),
                category=entry.get("category"),
                scholar_inbox_url=scholar_inbox_url,
                publication_date=entry.get("publication_date"),
            )
        )

    return papers


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def scrape_recommendations(
    config,
    date: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[RawPaper]:
    """Fetch and return papers above the configured score threshold.

    Parameters
    ----------
    config : AppConfig
        Application configuration (secrets, thresholds, etc.).
    date : str, optional
        Specific digest date in ``MM-DD-YYYY`` format.
    from_date / to_date : str, optional
        Date range, both in ``MM-DD-YYYY`` format.

    Returns
    -------
    list[RawPaper]
        Papers whose ranking score meets or exceeds the threshold.
    """
    session_cookie = await ensure_session(config)

    params: dict = {}
    if date:
        params["date"] = date
    elif from_date and to_date:
        params["from"] = from_date
        params["to"] = to_date

    async with httpx.AsyncClient(
        cookies={"session": session_cookie},
        timeout=DEFAULT_TIMEOUT,
    ) as client:
        data = await _fetch_papers(client, params)

    papers = _parse_papers(data, config.ingestion.score_threshold)
    logger.info(
        "Fetched %d papers above threshold (%.0f%%) from Scholar Inbox",
        len(papers),
        config.ingestion.score_threshold * 100,
    )
    return papers


async def scrape_date(
    config,
    target_date: str,
    score_threshold: float | None = None,
) -> list[RawPaper]:
    """Fetch papers for a single digest date with an explicit score threshold.

    Parameters
    ----------
    config : AppConfig
        Application configuration.
    target_date : str
        Digest date in ``MM-DD-YYYY`` format (as the API expects).
    score_threshold : float, optional
        Override threshold (0.0-1.0 decimal scale). Defaults to ``config.ingestion.score_threshold``.

    Returns
    -------
    list[RawPaper]
        Papers meeting the threshold.
    """
    if score_threshold is None:
        score_threshold = config.ingestion.score_threshold

    session_cookie = await ensure_session(config)

    async with httpx.AsyncClient(
        cookies={"session": session_cookie},
        timeout=DEFAULT_TIMEOUT,
    ) as client:
        data = await _fetch_papers(client, {"date": target_date})

    papers = _parse_papers(data, score_threshold)
    logger.info(
        "scrape_date(%s): %d papers above %.0f%%",
        target_date,
        len(papers),
        score_threshold * 100,
    )
    return papers
