"""Unit tests for commands.permissions.role_commands._parse_duration_seconds."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.permissions.role_commands import _parse_duration_seconds


@pytest.mark.parametrize("raw, expected_seconds", [
    ("30s", 30),
    ("10m", 600),
    ("2h", 7200),
    ("1d", 86400),
    ("0m", 0),
    ("  2H  ", 7200),  # whitespace + case insensitive
])
def test_valid_durations(raw, expected_seconds):
    assert _parse_duration_seconds(raw) == expected_seconds


@pytest.mark.parametrize("raw", [
    "",
    None,
    "abc",
    "5",
    "5x",
    "m5",
    "5 m",
    "-5m",
])
def test_invalid_durations_return_none(raw):
    assert _parse_duration_seconds(raw) is None
