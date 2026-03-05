"""Tests for src.web.filters — custom Jinja2 filter implementations."""

from __future__ import annotations

import pytest

from src.web.filters import (
    cron_human,
    first_author,
    format_duration,
    from_json,
    relative_date,
)


class TestRelativeDate:
    def test_returns_dash_for_empty(self):
        assert relative_date("") == "\u2014"
        assert relative_date(None) == "\u2014"

    def test_just_now(self):
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        iso = (now - timedelta(seconds=30)).isoformat()
        assert relative_date(iso) == "just now"

    def test_minutes_ago(self):
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        iso = (now - timedelta(minutes=5)).isoformat()
        assert relative_date(iso) == "5 minutes ago"

    def test_one_minute_ago_singular(self):
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        iso = (now - timedelta(seconds=90)).isoformat()
        assert relative_date(iso) == "1 minute ago"

    def test_hours_ago(self):
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        iso = (now - timedelta(hours=3)).isoformat()
        assert relative_date(iso) == "3 hours ago"

    def test_one_hour_singular(self):
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        iso = (now - timedelta(hours=1, minutes=30)).isoformat()
        assert relative_date(iso) == "1 hour ago"

    def test_days_ago(self):
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        iso = (now - timedelta(days=3)).isoformat()
        assert relative_date(iso) == "3 days ago"

    def test_weeks_ago(self):
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        iso = (now - timedelta(weeks=2)).isoformat()
        assert relative_date(iso) == "2 weeks ago"

    def test_old_date_returns_absolute(self):
        result = relative_date("2020-01-15T12:00:00+00:00")
        assert "2020" in result
        assert "Jan" in result

    def test_naive_datetime_treated_as_utc(self):
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        naive = (now - timedelta(hours=2)).replace(tzinfo=None)
        iso = naive.isoformat()
        result = relative_date(iso)
        assert "hour" in result

    def test_invalid_string_returned_as_is(self):
        assert relative_date("not-a-date") == "not-a-date"


class TestFirstAuthor:
    def test_returns_unknown_for_empty(self):
        assert first_author("") == "Unknown"
        assert first_author(None) == "Unknown"

    def test_single_author(self):
        assert first_author('["Alice Smith"]') == "Alice Smith"

    def test_multiple_authors_et_al(self):
        assert first_author('["Alice Smith", "Bob Jones", "Carol Wu"]') == "Alice Smith et al."

    def test_two_authors_et_al(self):
        assert first_author('["Alice Smith", "Bob Jones"]') == "Alice Smith et al."

    def test_already_a_list(self):
        assert first_author(["Alice Smith", "Bob Jones"]) == "Alice Smith et al."

    def test_empty_json_array(self):
        assert first_author("[]") == "Unknown"

    def test_invalid_json(self):
        assert first_author("{bad json}") == "Unknown"


class TestFormatDuration:
    def test_returns_dash_for_no_start(self):
        assert format_duration("") == "\u2014"
        assert format_duration(None) == "\u2014"

    def test_returns_in_progress_for_no_end(self):
        assert format_duration("2025-01-01T10:00:00") == "In progress"

    def test_seconds_only(self):
        assert format_duration("2025-01-01T10:00:00", "2025-01-01T10:00:45") == "45s"

    def test_minutes_and_seconds(self):
        assert format_duration("2025-01-01T10:00:00", "2025-01-01T10:01:23") == "1m 23s"

    def test_zero_seconds(self):
        assert format_duration("2025-01-01T10:00:00", "2025-01-01T10:00:00") == "0s"

    def test_negative_duration_returns_dash(self):
        assert format_duration("2025-01-01T10:01:00", "2025-01-01T10:00:00") == "\u2014"

    def test_invalid_timestamps(self):
        assert format_duration("bad", "also-bad") == "\u2014"


class TestCronHuman:
    def test_returns_dash_for_empty(self):
        assert cron_human("") == "\u2014"
        assert cron_human(None) == "\u2014"

    def test_weekly_schedule(self):
        assert cron_human("0 8 * * 1") == "Every Monday at 08:00"

    def test_daily_schedule(self):
        assert cron_human("0 6 * * *") == "Daily at 06:00"

    def test_monthly_schedule(self):
        assert cron_human("0 9 15 * *") == "Monthly on day 15 at 09:00"

    def test_sunday_schedule(self):
        assert cron_human("30 10 * * 0") == "Every Sunday at 10:30"

    def test_saturday_schedule(self):
        assert cron_human("0 22 * * 6") == "Every Saturday at 22:00"

    def test_unknown_pattern_returns_raw(self):
        # 5-field but unusual pattern: specific month + day combination
        result = cron_human("0 9 1 1 *")
        assert result == "0 9 1 1 *"

    def test_invalid_field_count_returns_raw(self):
        assert cron_human("0 8 *") == "0 8 *"

    def test_zero_pad_hours_minutes(self):
        result = cron_human("5 9 * * 3")
        assert "09:05" in result


class TestFromJson:
    def test_returns_value_for_empty(self):
        assert from_json("") == ""
        assert from_json(None) is None

    def test_parses_dict(self):
        result = from_json('{"2025": 89, "2026": 53}')
        assert result == {"2025": 89, "2026": 53}

    def test_parses_list(self):
        result = from_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_invalid_json_returns_original(self):
        bad = "{bad json}"
        assert from_json(bad) == bad

    def test_parses_nested(self):
        result = from_json('{"a": [1, 2]}')
        assert result == {"a": [1, 2]}
