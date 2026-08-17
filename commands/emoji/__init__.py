"""Emoji/sticker command domain. Message-targeted commands (copy, from
attachment, from reaction, save-from-message) are exposed as context menus,
not slash commands -- see context_menus.py."""
from commands.emoji.commands import EmojiGroup
from commands.emoji.context_menus import (
    copy_emoji_from_message_ctx,
    copy_emoji_from_reaction_ctx,
    create_emoji_from_attachment_ctx,
    save_emojis_from_message_ctx,
)

EMOJI_CONTEXT_MENUS = [
    copy_emoji_from_message_ctx,
    copy_emoji_from_reaction_ctx,
    create_emoji_from_attachment_ctx,
    save_emojis_from_message_ctx,
]

__all__ = ['EmojiGroup', 'EMOJI_CONTEXT_MENUS']
