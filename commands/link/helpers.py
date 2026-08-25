"""Business logic for editing/deleting the bot's replaced-link messages."""
import re

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


def validate_own_replaced_message(message: discord.Message, interaction: discord.Interaction) -> tuple[bool, str]:
    """Check that `message` is one of the bot's replaced-link messages
    belonging to the invoking user. Returns (ok, error_or_mention_prefix)."""
    if message.author.id != interaction.client.user.id:
        return False, "That message was not sent by me."

    mention_match = MENTION_PREFIX_RE.match(message.content.strip())
    if not mention_match or int(mention_match.group(1)) != interaction.user.id:
        return False, "You can only modify your own replaced messages."

    mention_str = mention_match.group(0)[:-1]  # remove trailing colon
    return True, mention_str
