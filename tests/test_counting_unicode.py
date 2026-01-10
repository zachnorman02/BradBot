import os
import sys
import pytest

# Ensure repo root on sys.path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.counting import _normalize_digits, _evaluate_expression, _is_expression_safe


@pytest.mark.parametrize(
    "expr, expected",
    [
        ("٣٤", 34),  # Arabic-Indic digits
        ("٣+٤", 7),
        ("१२", 12),  # Devanagari digits
        ("१२^२", 144),
        ("೨೩", 23),  # Kannada digits
        ("九", 9),  # CJK numeral
        ("七+三", 10),
        ("二十五", 25),
        ("十七", 17),
        ("IV", 4),  # Roman numerals
        ("X+V", 15),
        ("xii", 12),
        ("一万", 10000),
        ("一万三千二百", 13200),
    ],
)
def test_unicode_digits_normalize_and_eval(expr, expected):
    normalized = _normalize_digits(expr)
    assert normalized != expr  # ensure we actually normalized non-ASCII digits
    assert _is_expression_safe(normalized)
    assert _evaluate_expression(normalized) == expected


def test_non_digit_characters_unchanged():
    expr = "abc + ١٢"
    normalized = _normalize_digits(expr)
    # letters remain; only digits should be normalized
    assert "abc" in normalized
    assert any(ch.isdigit() for ch in normalized)
