import os
import sys
from types import SimpleNamespace


# Ensure repo root on sys.path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message_processing import process_message_links


def _run_process(content: str):
    import asyncio

    message = SimpleNamespace(
        content=content,
        guild=None,
        mentions=[],
        author=SimpleNamespace(mention="<@1>"),
    )
    return asyncio.run(process_message_links(message))


def test_tiktok_trailing_period_is_replaced():
    result = _run_process("check this https://tiktok.com/ZNRQtb3Xh.")

    assert result is not None
    assert result["content_changed"] is True
    assert result["fixed_urls"] == {
        "https://tiktok.com/ZNRQtb3Xh.": "https://a.tnktok.com/ZNRQtb3Xh."
    }
    assert "https://a.tnktok.com/ZNRQtb3Xh." in result["new_content"]


def test_non_tiktok_trailing_punctuation_is_also_replaced():
    result = _run_process("check this https://twitter.com/user/status/12345.")

    assert result is not None
    assert result["content_changed"] is True
    assert result["fixed_urls"] == {
        "https://twitter.com/user/status/12345.": "https://fxtwitter.com/user/status/12345."
    }
    assert "https://fxtwitter.com/user/status/12345." in result["new_content"]


def test_angle_bracket_suppressed_url_is_not_processed():
    result = _run_process("<https://tiktok.com/ZNRQtb3Xh>.")

    assert result is None


def test_reddit_user_profile_url_is_not_processed():
    result = _run_process("check this https://reddit.com/u/spez")

    assert result is None


def test_reddit_subreddit_comments_url_is_not_rewritten_to_vxreddit():
    result = _run_process("check this https://www.reddit.com/r/python/comments/abc123/example_post/")

    assert result is not None
    assert "vxreddit.com" not in result["new_content"]
    assert "reddit.com/r/python/comments/abc123/example_post" in result["new_content"]
