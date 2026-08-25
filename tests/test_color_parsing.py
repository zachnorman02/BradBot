"""Unit tests for utils.color_parsing."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from utils.color_parsing import parse_hex_color


def test_parse_hex_color_with_hash():
    color = parse_hex_color("#FF0000")
    assert color.value == 0xFF0000


def test_parse_hex_color_without_hash():
    color = parse_hex_color("00FF00")
    assert color.value == 0x00FF00


def test_parse_hex_color_invalid_raises_with_field_label():
    with pytest.raises(ValueError, match="Invalid secondary color hex format"):
        parse_hex_color("not-a-hex", field_label="secondary color")
