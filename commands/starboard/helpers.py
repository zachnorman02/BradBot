"""Business logic for the starboard message-action context menus (force,
block, unblock), shared between the "only one board configured" fast path
and the board-picker follow-up when a guild has more than one."""
import discord

from database import db
from core import starboard as starboard_core


def normalize_emoji_str(emoji: discord.PartialEmoji | str) -> str:
    if isinstance(emoji, discord.PartialEmoji):
        return emoji.to_str()
    return emoji


async def force_to_starboard(client, board: dict, message: discord.Message) -> None:
    await starboard_core.force_starboard_post(client, board, message)


async def block_from_starboard(guild: discord.Guild, board: dict, message: discord.Message) -> None:
    entry = db.get_starboard_post(message.id, board["id"])
    db.upsert_starboard_post(
        message_id=message.id, board_id=board["id"], guild_id=guild.id, channel_id=message.channel.id,
        author_id=message.author.id, star_message_id=entry.get("star_message_id") if entry else None,
        count=entry.get("current_count") if entry else 0, forced=entry.get("forced") if entry else False, blocked=True,
    )
    if entry and entry.get("star_message_id"):
        channel = guild.get_channel(board["channel_id"])
        if channel:
            try:
                star_msg = await channel.fetch_message(entry["star_message_id"])
                await star_msg.delete()
            except discord.DiscordException:
                pass


async def unblock_from_starboard(client, board: dict, message: discord.Message) -> None:
    entry = db.get_starboard_post(message.id, board["id"])
    if entry:
        db.update_starboard_post(message.id, board["id"], blocked=False, forced=False)
    await starboard_core.process_board(client, board, message, board["emoji"])
