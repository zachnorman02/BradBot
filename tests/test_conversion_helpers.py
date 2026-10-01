"""Unit tests for utils.conversion_helpers.convert_testosterone."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.conversion_helpers import convert_testosterone


def test_gel_to_cypionate_known_values():
    # 100mg gel daily: weekly_absorbed = 100 * 7 * 0.125 = 87.5mg
    # cyp_weekly = 87.5 / 0.70 = 125.00mg
    result = convert_testosterone("gel", 100, 1)
    assert "87.50mg weekly" in result
    assert "125.00mg per week" in result


def test_cypionate_to_gel_known_values():
    # 100mg cypionate every 7 days: weekly_absorbed = 100 * 1 * 0.70 = 70mg
    # gel_daily = 70 / (7 * 0.125) = 80.00mg
    result = convert_testosterone("cypionate", 100, 7)
    assert "70.00mg weekly" in result
    assert "80.00mg per day" in result


def test_invalid_conversion_type_returns_error_message():
    assert convert_testosterone("unknown", 100, 7) == "❌ Invalid conversion type."


def test_gel_result_mentions_input_dose_and_frequency():
    result = convert_testosterone("gel", 50, 2)
    assert "50mg gel every 2 day(s)" in result
