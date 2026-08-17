"""Business logic for the emoji domain: permission checks, emoji/sticker
creation with overwrite, and extracting emoji/image/reaction candidates from
a discord.Message (shared by both the slash commands and the message
context menus, which already have the Message object and skip link parsing).
"""
import io
import re

import discord

from database import db
from utils.http_download import download_bytes
from utils.interaction_helpers import has_permission_or_owner


async def check_emoji_permissions(interaction: discord.Interaction) -> str | None:
    """Return an error message if the user/bot lack emoji management perms, else None."""
    if not interaction.guild:
        return "This command can only be used in a server!"
    if not await has_permission_or_owner(interaction, manage_emojis_and_stickers=True):
        return "You need 'Manage Expressions' permission to use this command."
    if not interaction.guild.me.guild_permissions.manage_emojis_and_stickers:
        return "I don't have 'Manage Expressions' permission to create/edit emojis or stickers."
    return None


def parse_index_selection(which: str, max_len: int) -> list[int]:
    """Parse a '2' or '1,3' style 1-based index string into valid 0-based indices."""
    indices = [int(i.strip()) - 1 for i in which.split(",") if i.strip().isdigit()]
    return [i for i in indices if 0 <= i < max_len]


async def create_emoji_or_sticker_with_overwrite(
    guild: discord.Guild,
    name: str,
    image_bytes: bytes,
    source_name: str = "image",
    create_sticker: bool = False,
    replace_existing: bool = True,
) -> str:
    """Create an emoji or sticker, optionally replacing an existing one with the same name."""
    if create_sticker:
        sticker_limit = guild.sticker_limit
        existing_sticker = discord.utils.get(guild.stickers, name=name)

        if existing_sticker:
            if replace_existing:
                try:
                    await existing_sticker.delete(reason="Replaced with new sticker")
                except discord.Forbidden:
                    return f"I don't have permission to delete the existing sticker '{name}'."
                except Exception as e:
                    return f"Failed to delete existing sticker: {e}"
            else:
                return f"A sticker named '{name}' already exists. Use replace_existing=True to overwrite."

        if len(guild.stickers) >= sticker_limit:
            return f"This server has reached its sticker limit ({sticker_limit})."

        try:
            new_sticker = await guild.create_sticker(
                name=name, description=f"Imported from {source_name}", emoji="⭐",
                file=discord.File(io.BytesIO(image_bytes), filename=f"{name}.png"),
                reason="Created via bot command",
            )
            return f"✅ Created sticker: {new_sticker.name}"
        except discord.Forbidden:
            return "❌ I don't have permission to create stickers."
        except discord.HTTPException as e:
            return f"❌ Failed to create sticker: {e}"
    else:
        emoji_limit = guild.emoji_limit
        existing_emoji = discord.utils.get(guild.emojis, name=name)

        if existing_emoji:
            if replace_existing:
                try:
                    await existing_emoji.delete(reason="Replaced with new emoji")
                except discord.Forbidden:
                    return f"❌ I don't have permission to delete the existing emoji '{name}'."
                except Exception as e:
                    return f"❌ Failed to delete existing emoji: {e}"
            else:
                return f"❌ An emoji named '{name}' already exists. Use replace_existing=True to overwrite."

        if len(guild.emojis) >= emoji_limit:
            return f"❌ This server has reached its emoji limit ({emoji_limit})."

        try:
            new_emoji = await guild.create_custom_emoji(name=name, image=image_bytes, reason="Created via bot command")
            return f"✅ Created emoji: {new_emoji}"
        except discord.Forbidden:
            return "❌ I don't have permission to create emojis."
        except discord.HTTPException as e:
            return f"❌ Failed to create emoji: {e}"


EMOJI_PATTERN = re.compile(r'<(a?):(\w+):(\d+)>')


def extract_message_emojis(message: discord.Message):
    """Return a list of (name, id, animated) for custom emoji in message content."""
    return [(m.group(2), m.group(3), m.group(1) == 'a') for m in EMOJI_PATTERN.finditer(message.content)]


def extract_message_images(message: discord.Message):
    """Return a list of ('attachment', Attachment) | ('embed', url) image candidates."""
    images = []
    for att in message.attachments:
        if any(att.filename.lower().endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            images.append(('attachment', att))
    for embed in message.embeds:
        if embed.image:
            images.append(('embed', embed.image.url))
        elif embed.thumbnail:
            images.append(('embed', embed.thumbnail.url))
    return images


def extract_message_reaction_emojis(message: discord.Message):
    """Return the custom (non-unicode) emoji used as reactions on a message."""
    return [r.emoji for r in message.reactions if hasattr(r.emoji, 'id')]


async def download_emoji_bytes(emoji_id: str, animated: bool) -> bytes:
    ext = 'gif' if animated else 'png'
    return await download_bytes(f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}")
