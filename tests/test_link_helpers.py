"""Unit tests for commands.link.helpers (no live Discord connection needed)."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.link.helpers import split_user_text, parse_replaced_message_owner, validate_own_replaced_message

BOT_ID = 111
OWNER_ID = 222
OTHER_ID = 333


def _message(author_id, content):
    return SimpleNamespace(author=SimpleNamespace(id=author_id), content=content)


def _interaction(user_id, bot_id=BOT_ID):
    return SimpleNamespace(client=SimpleNamespace(user=SimpleNamespace(id=bot_id)), user=SimpleNamespace(id=user_id))


def test_split_user_text_strips_mention_prefix():
    base, extra = split_user_text(f"<@{OWNER_ID}>: hello world", f"<@{OWNER_ID}>")
    assert base == "hello world"
    assert extra == []


def test_split_user_text_separates_footnote_lines():
    content = f"<@{OWNER_ID}>: main text\n-# footnote one\n-# footnote two"
    base, extra = split_user_text(content, f"<@{OWNER_ID}>")
    assert base == "main text"
    assert extra == ["-# footnote one", "-# footnote two"]


def test_split_user_text_without_matching_prefix_is_unchanged():
    base, extra = split_user_text("no prefix here", f"<@{OWNER_ID}>")
    assert base == "no prefix here"
    assert extra == []


def test_parse_replaced_message_owner_wrong_author_returns_none():
    message = _message(OTHER_ID, f"<@{OWNER_ID}>: hello")
    assert parse_replaced_message_owner(message, BOT_ID) is None


def test_parse_replaced_message_owner_no_mention_prefix_returns_none():
    message = _message(BOT_ID, "just some text, no mention prefix")
    assert parse_replaced_message_owner(message, BOT_ID) is None


def test_parse_replaced_message_owner_returns_mentioned_user_id():
    message = _message(BOT_ID, f"<@{OWNER_ID}>: hello")
    assert parse_replaced_message_owner(message, BOT_ID) == OWNER_ID


def test_parse_replaced_message_owner_handles_nickname_mention_format():
    message = _message(BOT_ID, f"<@!{OWNER_ID}>: hello")
    assert parse_replaced_message_owner(message, BOT_ID) == OWNER_ID


def test_validate_own_replaced_message_rejects_non_bot_author():
    message = _message(OTHER_ID, f"<@{OWNER_ID}>: hello")
    ok, result = validate_own_replaced_message(message, _interaction(OWNER_ID))
    assert ok is False
    assert result == "That message was not sent by me."


def test_validate_own_replaced_message_rejects_non_owner():
    message = _message(BOT_ID, f"<@{OWNER_ID}>: hello")
    ok, result = validate_own_replaced_message(message, _interaction(OTHER_ID))
    assert ok is False
    assert "your own" in result


def test_validate_own_replaced_message_accepts_owner():
    message = _message(BOT_ID, f"<@{OWNER_ID}>: hello")
    ok, mention = validate_own_replaced_message(message, _interaction(OWNER_ID))
    assert ok is True
    assert mention == f"<@{OWNER_ID}>"
