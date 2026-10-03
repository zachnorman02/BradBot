"""Business logic for editing/deleting the bot's replaced-link messages."""
import re
from typing import Optional

import discord

MENTION_PREFIX_RE = re.compile(r"^<@!?(\d+)>:")


def split_user_text(content: str, mention: str) -> tuple[str, list[str]]:
    """Split a bot-replaced message's content back into the base text and any
    '-# ' footnote lines, stripping the leading mention prefix."""
    text = content
    prefix = f"{mention}:"
    if text.startswith(prefix):
        text = text[len(prefix):].lstrip()

    main_lines, extra_lines = [], []
    for line in text.split("\n"):
        if line.strip().startswith("-# "):
            extra_lines.append(line.strip())
        else:
            main_lines.append(line)
    base_text = "\n".join(main_lines).strip()
    return base_text, extra_lines


def parse_replaced_message_owner(message: discord.Message, bot_user_id: int) -> Optional[int]:
    """Return the user id a bot-replaced-link message was sent for, or None
    if `message` isn't one of ours (wrong author, or no recognizable mention
    prefix). Shared ownership check behind both the Apps context menus
    (validate_own_replaced_message below) and the reaction shortcuts
    (commands/link/reactions.py) -- one place deciding who "owns" one of
    these messages, so both surfaces stay locked to the same person."""
    if message.author.id != bot_user_id:
        return None
    mention_match = MENTION_PREFIX_RE.match(message.content.strip())
    if not mention_match:
        return None
    return int(mention_match.group(1))


def validate_own_replaced_message(message: discord.Message, interaction: discord.Interaction) -> tuple[bool, str]:
    """Check that `message` is one of the bot's replaced-link messages
    belonging to the invoking user. Returns (ok, error_or_mention_prefix)."""
    if message.author.id != interaction.client.user.id:
        return False, "That message was not sent by me."

    owner_id = parse_replaced_message_owner(message, interaction.client.user.id)
    if owner_id is None or owner_id != interaction.user.id:
        return False, "You can only modify your own replaced messages."

    mention_match = MENTION_PREFIX_RE.match(message.content.strip())
    mention_str = mention_match.group(0)[:-1]  # remove trailing colon
    return True, mention_str
