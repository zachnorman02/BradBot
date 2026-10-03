"""Unit tests for utils.websites.get_site_name (pure pattern matching, no
network calls -- render() is async/networked and intentionally not tested
here)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.websites import get_site_name


@pytest.mark.parametrize("url, expected_name", [
    ("https://twitter.com/someuser/status/123456", "Twitter"),
    ("https://x.com/someuser/status/123456", "Twitter"),
    ("https://www.instagram.com/someuser/", "Instagram"),
    ("https://www.instagram.com/p/abc123/", "Instagram"),
    ("https://www.tiktok.com/@someuser", "TikTok"),
    ("https://www.tiktok.com/@someuser/video/123", "TikTok"),
    ("https://www.reddit.com/r/foo/comments/abc/title", "Reddit"),
    ("https://youtu.be/abc123", "YouTube"),
    ("https://www.youtube.com/watch?v=abc123", "YouTube"),
    ("https://www.threads.net/@someuser/post/abc", "Threads"),
    ("https://bsky.app/profile/someuser/post/abc", "Bluesky"),
    ("https://www.twitch.tv/someuser/clip/abc123", "Twitch"),
])
def test_get_site_name_recognizes_known_sites(url, expected_name):
    assert get_site_name(url) == expected_name


def test_get_site_name_returns_url_unchanged_for_unknown_site():
    url = "https://not-a-known-site.example.com/path"
    assert get_site_name(url) == url


def test_get_site_name_does_not_match_bare_twitter_profile():
    # Twitter/X only matches tweet/status URLs, not bare profile URLs --
    # this is intentional (see TwitterLink.routes), not a bug.
    url = "https://twitter.com/someuser"
    assert get_site_name(url) == url
