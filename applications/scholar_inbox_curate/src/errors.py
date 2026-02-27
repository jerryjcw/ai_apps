"""Unified error hierarchy and resilience utilities.

All custom exceptions inherit from ``ScholarCurateError`` for easy
catch-all handling.  The ``retry_async`` decorator provides configurable
retry logic with exponential backoff.
"""

from __future__ import annotations

import asyncio
import logging
from functools import wraps

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base exception
# ---------------------------------------------------------------------------

class ScholarCurateError(Exception):
    """Root exception for all Scholar Inbox Curate errors."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class ConfigError(ScholarCurateError):
    """Raised when configuration validation fails."""


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class DatabaseError(ScholarCurateError):
    """Raised for schema or migration failures (not query-level errors)."""


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

class ScraperError(ScholarCurateError):
    """Base exception for scraper errors."""


class CloudflareTimeoutError(ScraperError):
    """Turnstile challenge was not solved in time."""


class LoginError(ScraperError):
    """Login to Scholar Inbox failed."""


class SessionExpiredError(ScraperError):
    """Saved session cookie is no longer valid."""


class APIError(ScraperError):
    """Unexpected API response."""


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

class ResolverError(ScholarCurateError):
    """Raised when Semantic Scholar API is completely unreachable."""


# ---------------------------------------------------------------------------
# Citation polling
# ---------------------------------------------------------------------------

class CitationPollError(ScholarCurateError):
    """Raised when all citation sources fail for an entire poll cycle."""


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

class RulesError(ScholarCurateError):
    """Raised for logic errors in prune/promote (should not happen)."""


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

def retry_async(max_retries: int = 1, delay: float = 5.0, backoff: float = 2.0):
    """Decorator for async functions that retries on exception.

    Parameters
    ----------
    max_retries : int
        Maximum number of retry attempts (default 1 = 2 total attempts).
    delay : float
        Initial delay between retries in seconds.
    backoff : float
        Multiplier applied to delay after each retry.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        logger.warning(
                            "%s failed (attempt %d/%d), retrying in %.1fs: %s",
                            func.__name__,
                            attempt + 1,
                            max_retries + 1,
                            current_delay,
                            e,
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
            raise last_error
        return wrapper
    return decorator
