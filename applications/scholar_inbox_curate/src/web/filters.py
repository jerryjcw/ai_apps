"""Custom Jinja2 filters for Scholar Inbox Curate templates."""

import json
from datetime import datetime, timezone


def relative_date(iso_str: str) -> str:
    """Convert ISO timestamp to relative string like '3 days ago'."""
    if not iso_str:
        return "\u2014"

    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        delta = now - dt
        seconds = int(delta.total_seconds())

        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif seconds < 604800:
            days = seconds // 86400
            return f"{days} day{'s' if days != 1 else ''} ago"
        elif seconds < 2592000:
            weeks = seconds // 604800
            return f"{weeks} week{'s' if weeks != 1 else ''} ago"
        else:
            return dt.strftime("%b %d, %Y")

    except (ValueError, TypeError):
        return iso_str


def first_author(authors_json: str) -> str:
    """Parse JSON author array, return 'First Author et al.' or single name."""
    if not authors_json:
        return "Unknown"

    try:
        if isinstance(authors_json, list):
            authors = authors_json
        else:
            authors = json.loads(authors_json)

        if not authors:
            return "Unknown"
        elif len(authors) == 1:
            return authors[0]
        else:
            return f"{authors[0]} et al."

    except (json.JSONDecodeError, TypeError):
        return "Unknown"


def format_duration(started_at: str, finished_at: str | None = None) -> str:
    """Compute duration between two ISO timestamps."""
    if not started_at:
        return "\u2014"
    if not finished_at:
        return "In progress"

    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(finished_at)
        delta = end - start
        total_seconds = int(delta.total_seconds())

        if total_seconds < 0:
            return "\u2014"
        elif total_seconds < 60:
            return f"{total_seconds}s"
        else:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            return f"{minutes}m {seconds}s"

    except (ValueError, TypeError):
        return "\u2014"


def cron_human(cron_expr: str) -> str:
    """Convert cron expression to human-readable text.

    Handles common patterns used in this project. Not a full cron parser.
    """
    if not cron_expr:
        return "\u2014"

    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return cron_expr

    minute, hour, dom, month, dow = parts

    day_names = {
        "0": "Sunday", "1": "Monday", "2": "Tuesday",
        "3": "Wednesday", "4": "Thursday", "5": "Friday",
        "6": "Saturday", "7": "Sunday",
    }

    if dom == "*" and month == "*" and dow != "*":
        day = day_names.get(dow, f"day {dow}")
        return f"Every {day} at {hour.zfill(2)}:{minute.zfill(2)}"

    if dom == "*" and month == "*" and dow == "*":
        return f"Daily at {hour.zfill(2)}:{minute.zfill(2)}"

    if month == "*" and dow == "*" and dom != "*":
        return f"Monthly on day {dom} at {hour.zfill(2)}:{minute.zfill(2)}"

    return cron_expr


def from_json(value: str):
    """Parse a JSON string. Returns the parsed object, or the original value on error."""
    if not value:
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
