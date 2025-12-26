"""
Message audit logging for edits and deletions.
"""
import discord

from database import db


async def log_message_edit_event(before: discord.Message | None, after: discord.Message | None):
    """Log a message edit to the database."""
    guild = getattr(after or before, "guild", None)
    if not guild:
        return

    if not db.connection_pool:
        db.init_pool()

    guild_id = guild.id
    channel_id = getattr(after or before, "channel", None)
    channel_id = channel_id.id if channel_id else None
    message_id = getattr(after or before, "id", None)
    author = getattr(after or before, "author", None)
    user_id = author.id if author else None

    old_content = getattr(before, "content", None) if before else None
    new_content = getattr(after, "content", None) if after else None

    try:
        db.log_message_edit(guild_id, channel_id, message_id, user_id, old_content, new_content)
    except Exception as e:
        print(f"[MESSAGE LOG] Failed to log edit for message {message_id}: {e}")


async def log_message_delete_event(message: discord.Message):
    """Log a message deletion to the database."""
    if not message.guild:
        return

    if not db.connection_pool:
        db.init_pool()

    guild_id = message.guild.id
    channel_id = message.channel.id if getattr(message, "channel", None) else None
    message_id = message.id
    author = getattr(message, "author", None)
    user_id = author.id if author else None
    old_content = getattr(message, "content", None)

    try:
        db.log_message_delete(guild_id, channel_id, message_id, user_id, old_content)
    except Exception as e:
        print(f"[MESSAGE LOG] Failed to log delete for message {message_id}: {e}")


async def log_raw_message_delete_event(payload: discord.RawMessageDeleteEvent):
    """Log a deletion when only payload is available."""
    if not payload.guild_id:
        return

    if not db.connection_pool:
        db.init_pool()

    try:
        db.log_message_delete(
            payload.guild_id,
            payload.channel_id,
            payload.message_id,
            None,
            None
        )
    except Exception as e:
        print(f"[MESSAGE LOG] Failed to log raw delete for message {payload.message_id}: {e}")
