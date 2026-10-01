"""Unit tests for small pure helpers in core.message_processing."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message_processing import (
    _strip_trailing_slash,
    _split_url_trailing_punctuation,
    _should_skip_link_replacement,
)


@pytest.mark.parametrize("url, expected", [
    ("https://example.com/path/", "https://example.com/path"),
    ("https://example.com/path", "https://example.com/path"),
    ("https://example.com/", "https://example.com"),
    ("https://example.com//", "https://example.com"),
])
def test_strip_trailing_slash(url, expected):
    assert _strip_trailing_slash(url) == expected


def test_strip_trailing_slash_leaves_bare_scheme_untouched():
    # The bare "https://" edge case is explicitly excluded.
    assert _strip_trailing_slash("https://") == "https://"


@pytest.mark.parametrize("url, expected_url, expected_punct", [
    ("https://example.com/path.", "https://example.com/path", "."),
    ("https://example.com/path!", "https://example.com/path", "!"),
    ("https://example.com/path", "https://example.com/path", ""),
    ("https://example.com/path...", "https://example.com/path", "..."),
    ("https://example.com/path?!", "https://example.com/path", "?!"),
])
def test_split_url_trailing_punctuation(url, expected_url, expected_punct):
    normalized, punct = _split_url_trailing_punctuation(url)
    assert normalized == expected_url
    assert punct == expected_punct


def test_split_url_trailing_punctuation_all_punctuation_keeps_original():
    # If stripping punctuation would leave nothing, the original URL is
    # returned untouched rather than an empty string.
    normalized, punct = _split_url_trailing_punctuation("...")
    assert normalized == "..."
    assert punct == ""


def test_should_skip_reddit_user_profile():
    assert _should_skip_link_replacement("https://www.reddit.com/user/someone") is True
    assert _should_skip_link_replacement("https://reddit.com/u/someone/") is True


def test_should_not_skip_reddit_post_or_subreddit():
    assert _should_skip_link_replacement("https://www.reddit.com/r/foo/comments/abc") is False
    assert _should_skip_link_replacement("https://www.reddit.com/r/foo") is False


def test_should_not_skip_non_reddit_url():
    assert _should_skip_link_replacement("https://example.com/user/someone") is False
