"""Unit tests for utils.timestamp_helpers (no live Discord connection needed)."""
import os
import sys
import datetime as dt

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.timestamp_helpers import parse_time, create_discord_timestamp


@pytest.mark.parametrize("raw, expected", [
    ("13:00", dt.time(13, 0)),
    ("13:00:30", dt.time(13, 0, 30)),
    ("1 PM", dt.time(13, 0)),
    ("1:00 PM", dt.time(13, 0)),
    ("1:00:30 PM", dt.time(13, 0, 30)),
    ("12 AM", dt.time(0, 0)),
    ("12 PM", dt.time(12, 0)),
])
def test_parse_time_valid_formats(raw, expected):
    assert parse_time(raw) == expected


def test_parse_time_invalid_returns_none():
    assert parse_time("not a time") is None


def test_create_discord_timestamp_defaults_time_to_midnight_when_given():
    unix_ts, local_dt, utc_dt = create_discord_timestamp("2027-03-15", "00:00", 0)
    assert unix_ts is not None
    assert utc_dt == dt.datetime(2027, 3, 15, 0, 0)


def test_create_discord_timestamp_applies_positive_offset_behind_utc():
    # timezone_offset is "hours behind UTC", so a local 9:30 AM at UTC-5
    # (EST) is 14:30 UTC.
    unix_ts, local_dt, utc_dt = create_discord_timestamp("2027-03-15", "9:30 AM", -5)
    assert utc_dt == dt.datetime(2027, 3, 15, 14, 30)


def test_create_discord_timestamp_matches_unix_timestamp():
    unix_ts, _, utc_dt = create_discord_timestamp("2027-01-01", "00:00", 0)
    expected = int(utc_dt.replace(tzinfo=dt.timezone.utc).timestamp())
    assert unix_ts == expected


def test_create_discord_timestamp_invalid_date_returns_error():
    unix_ts, local_dt, error = create_discord_timestamp("not-a-date", None, 0)
    assert unix_ts is None
    assert local_dt is None
    assert "Invalid date format" in error


def test_create_discord_timestamp_invalid_time_returns_error():
    unix_ts, local_dt, error = create_discord_timestamp("2027-01-01", "not-a-time", 0)
    assert unix_ts is None
    assert "Invalid time format" in error


def test_create_discord_timestamp_defaults_date_to_today():
    unix_ts, local_dt, utc_dt = create_discord_timestamp(None, "00:00", 0)
    assert local_dt.date() == dt.datetime.now().date()
