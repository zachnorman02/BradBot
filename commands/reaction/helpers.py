"""Reaction-check business logic. Consolidates 3 old implementations
(reaction.check by message_id + all-channel search, reaction.check_url by
URL, utility.check_reaction by URL with an emoji filter -- kept as the
"most capable" base) into one function operating on an already-resolved
discord.Message, since the context menu hands that over directly.
"""
from typing import Optional

import discord


def normalize_emoji(e) -> Optional[str]:
    if e is None:
        return None
    if isinstance(e, str):
        return e
    if hasattr(e, "id") and e.id:
        prefix = "<a" if getattr(e, "animated", False) else "<"
        return f"{prefix}:{e.name}:{e.id}>"
    return str(e)


async def check_message_reactions(
    message: discord.Message,
    user: Optional[discord.abc.User] = None,
    emoji_filter: Optional[str] = None,
):
    """Return (matches, error). `matches` is a list of (user, matched_emoji)
    tuples. If `user` is given, only that user's reactions are checked; if
    `emoji_filter` is given, only that emoji's reactors are checked."""
    normalized_filter = normalize_emoji(emoji_filter) if emoji_filter else None
    matches = []

    try:
        for reaction in message.reactions:
            if normalized_filter and normalize_emoji(reaction.emoji) != normalized_filter:
                continue
            async for reactor in reaction.users(limit=None):
                if user is not None and reactor.id != user.id:
                    continue
                matches.append((reactor, normalize_emoji(reaction.emoji)))
                if user is not None:
                    return matches, None
    except Exception as e:
        return [], str(e)

    return matches, None
