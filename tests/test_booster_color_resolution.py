"""Unit tests for commands.booster.modals' Colors-field parsing
(no live Discord connection needed)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.booster.modals import _resolve_color_field, _resolve_colors_field


def test_resolve_color_field_blank_means_keep():
    action, value = _resolve_color_field("", field_label="primary color")
    assert action == "keep"
    assert value is None


def test_resolve_color_field_clear_token():
    action, value = _resolve_color_field("clear", field_label="primary color")
    assert action == "clear"
    assert value is None


def test_resolve_color_field_clear_token_case_insensitive():
    action, _ = _resolve_color_field("CLEAR", field_label="primary color")
    assert action == "clear"


def test_resolve_color_field_sets_valid_hex():
    action, value = _resolve_color_field("#FF0000", field_label="primary color")
    assert action == "set"
    assert value.value == 0xFF0000


def test_resolve_color_field_invalid_hex_raises():
    import pytest
    with pytest.raises(ValueError):
        _resolve_color_field("not-a-color", field_label="primary color")


def test_resolve_colors_field_blank_keeps_both():
    p_action, p_value, s_action, s_value = _resolve_colors_field("")
    assert (p_action, p_value, s_action, s_value) == ("keep", None, "keep", None)


def test_resolve_colors_field_single_value_sets_primary_and_clears_secondary():
    p_action, p_value, s_action, s_value = _resolve_colors_field("#00FF00")
    assert p_action == "set"
    assert p_value.value == 0x00FF00
    assert s_action == "clear"
    assert s_value is None


def test_resolve_colors_field_comma_sets_both_independently():
    p_action, p_value, s_action, s_value = _resolve_colors_field("#FF0000,#0000FF")
    assert p_action == "set" and p_value.value == 0xFF0000
    assert s_action == "set" and s_value.value == 0x0000FF


def test_resolve_colors_field_comma_with_clear_and_blank():
    p_action, p_value, s_action, s_value = _resolve_colors_field("clear, ")
    assert p_action == "clear"
    assert s_action == "keep"
