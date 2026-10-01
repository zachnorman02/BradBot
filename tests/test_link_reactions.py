"""Unit tests for commands.link.reactions.handle_link_message_reaction --
the delete/remove-embed reaction shortcuts on replaced-link messages, and
the author-only lock shared with the Apps context menus.

No pytest-asyncio dependency: each test runs the coroutine directly via
asyncio.run(), same approach test_link_replacement_punctuation.py uses.
"""
import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.link.reactions import handle_link_message_reaction, DELETE_EMOJI, REMOVE_EMBED_EMOJI

BOT_ID = 1
OWNER_ID = 2
OTHER_ID = 3


def _payload(user_id, emoji, member=None):
    return SimpleNamespace(user_id=user_id, emoji=emoji, channel_id=10, message_id=20, member=member)


def _message(author_id, content):
    msg = SimpleNamespace(
        author=SimpleNamespace(id=author_id),
        content=content,
        delete=AsyncMock(),
        edit=AsyncMock(),
        remove_reaction=AsyncMock(),
    )
    return msg


def _bot(message):
    channel = SimpleNamespace(fetch_message=AsyncMock(return_value=message))
    bot = SimpleNamespace(
        user=SimpleNamespace(id=BOT_ID),
        get_channel=lambda cid: channel,
        fetch_channel=AsyncMock(),
        get_user=lambda uid: SimpleNamespace(id=uid),
        fetch_user=AsyncMock(),
    )
    return bot


def _run(coro):
    return asyncio.run(coro)


def test_ignores_the_bots_own_reaction():
    message = _message(BOT_ID, f"<@{OWNER_ID}>: hi")
    bot = _bot(message)
    payload = _payload(BOT_ID, DELETE_EMOJI)
    _run(handle_link_message_reaction(bot, payload))
    message.delete.assert_not_awaited()


def test_ignores_unrelated_emoji():
    message = _message(BOT_ID, f"<@{OWNER_ID}>: hi")
    bot = _bot(message)
    payload = _payload(OWNER_ID, "👍")
    _run(handle_link_message_reaction(bot, payload))
    message.delete.assert_not_awaited()
    message.remove_reaction.assert_not_awaited()


def test_ignores_messages_that_arent_ours():
    message = _message(BOT_ID, "just a plain bot message, no mention prefix")
    bot = _bot(message)
    payload = _payload(OWNER_ID, DELETE_EMOJI)
    _run(handle_link_message_reaction(bot, payload))
    message.delete.assert_not_awaited()
    message.remove_reaction.assert_not_awaited()


def test_non_owner_reaction_is_bounced_back():
    message = _message(BOT_ID, f"<@{OWNER_ID}>: hi")
    bot = _bot(message)
    payload = _payload(OTHER_ID, DELETE_EMOJI)
    _run(handle_link_message_reaction(bot, payload))
    message.delete.assert_not_awaited()
    message.remove_reaction.assert_awaited_once()
    args = message.remove_reaction.call_args[0]
    assert args[0] == DELETE_EMOJI


def test_owner_delete_reaction_deletes_message():
    message = _message(BOT_ID, f"<@{OWNER_ID}>: hi")
    bot = _bot(message)
    payload = _payload(OWNER_ID, DELETE_EMOJI)
    _run(handle_link_message_reaction(bot, payload))
    message.delete.assert_awaited_once()
    message.remove_reaction.assert_not_awaited()  # message is gone, nothing to bounce


def test_owner_remove_embed_reaction_suppresses_and_bounces():
    message = _message(BOT_ID, f"<@{OWNER_ID}>: hi")
    bot = _bot(message)
    payload = _payload(OWNER_ID, REMOVE_EMBED_EMOJI)
    _run(handle_link_message_reaction(bot, payload))
    message.edit.assert_awaited_once_with(suppress=True)
    message.remove_reaction.assert_awaited_once()


def test_fetch_message_failure_is_handled_gracefully():
    bot = SimpleNamespace(
        user=SimpleNamespace(id=BOT_ID),
        get_channel=lambda cid: SimpleNamespace(fetch_message=AsyncMock(side_effect=discord.DiscordException("boom"))),
        fetch_channel=AsyncMock(),
        get_user=lambda uid: None,
        fetch_user=AsyncMock(),
    )
    payload = _payload(OWNER_ID, DELETE_EMOJI)
    # Should not raise.
    _run(handle_link_message_reaction(bot, payload))
