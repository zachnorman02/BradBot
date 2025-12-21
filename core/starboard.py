import asyncio
from typing import Sequence

import discord

from database import db


def _normalize_emoji(value) -> str:
    if isinstance(value, discord.PartialEmoji):
        return str(value)
    if isinstance(value, discord.Emoji):
        return str(value)
    if isinstance(value, discord.Reaction):
        return _normalize_emoji(value.emoji)
    return str(value)


async def ensure_tables():
    if not getattr(db, "_starboard_tables_initialized", False):
        if not db.connection_pool:
            db.init_pool()
        db.init_starboard_tables()


async def handle_raw_reaction(bot: discord.Client, payload: discord.RawReactionActionEvent):
    if payload.guild_id is None or payload.user_id == bot.user.id:
        return
    await ensure_tables()
    emoji_str = _normalize_emoji(payload.emoji)
    boards = db.get_starboard_boards_by_emoji(payload.guild_id, emoji_str)
    if not boards:
        return

    channel = bot.get_channel(payload.channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(payload.channel_id)
        except discord.DiscordException:
            return
    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.DiscordException:
        return

    await asyncio.gather(
        *[process_board(bot, board, message, emoji_str) for board in boards]
    )


def _get_reaction_count(message: discord.Message, emoji_str: str) -> int:
    for reaction in message.reactions:
        if _normalize_emoji(reaction.emoji) == emoji_str:
            return reaction.count
    return 0


async def process_board(bot: discord.Client, board: dict, message: discord.Message, emoji_str: str, force: bool = False):
    count = _get_reaction_count(message, emoji_str)
    allow_nsfw = board.get("allow_nsfw", False)
    channel_is_nsfw = getattr(message.channel, "is_nsfw", lambda: False)()

    entry = db.get_starboard_post(message.id, board["id"])
    forced = force or (entry and entry.get("forced"))
    blocked = entry and entry.get("blocked")

    if blocked:
        return

    should_post = forced or count >= board["threshold"]

    if channel_is_nsfw and not allow_nsfw and not forced:
        # Update count but skip posting
        if entry:
            db.update_starboard_post(message.id, board["id"], current_count=count)
        else:
            db.upsert_starboard_post(
                message_id=message.id,
                board_id=board["id"],
                guild_id=message.guild.id,
                channel_id=message.channel.id,
                author_id=message.author.id,
                star_message_id=None,
                count=count,
            )
        return

    if not should_post:
        if entry and entry.get("star_message_id"):
            channel = bot.get_channel(board["channel_id"])
            if channel:
                try:
                    star_msg = await channel.fetch_message(entry["star_message_id"])
                    await star_msg.delete()
                except discord.DiscordException:
                    pass
            db.update_starboard_post(message.id, board["id"], star_message_id=None, current_count=count, forced=False)
        elif entry:
            db.update_starboard_post(message.id, board["id"], current_count=count, forced=False)
        return

    channel = bot.get_channel(board["channel_id"])
    if channel is None:
        try:
            channel = await bot.fetch_channel(board["channel_id"])
        except discord.DiscordException:
            return

    embed = build_starboard_embed(board, message, count)
    content = f"{board['emoji']} **{count}** <#{message.channel.id}>"

    star_message_id = None
    if entry and entry.get("star_message_id"):
        try:
            star_msg = await channel.fetch_message(entry["star_message_id"])
            await star_msg.edit(content=content, embed=embed)
            star_message_id = star_msg.id
        except discord.DiscordException:
            star_message_id = None

    if star_message_id is None:
        try:
            star_msg = await channel.send(content=content, embed=embed)
            star_message_id = star_msg.id
        except discord.DiscordException:
            return

    db.upsert_starboard_post(
        message_id=message.id,
        board_id=board["id"],
        guild_id=message.guild.id,
        channel_id=message.channel.id,
        author_id=message.author.id,
        star_message_id=star_message_id,
        count=count,
        forced=forced,
    )


def build_starboard_embed(board: dict, message: discord.Message, count: int) -> discord.Embed:
    description = message.content or ""
    embed = discord.Embed(
        description=description,
        color=discord.Color.gold()
    )
    embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
    embed.add_field(name="Original", value=f"[Jump to message]({message.jump_url})", inline=False)
    if message.attachments:
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image"):
                embed.set_image(url=attachment.url)
                break
    embed.set_footer(text=f"{count} {board['emoji']} • #{message.channel.name}")
    return embed


async def force_starboard_post(bot: discord.Client, board: dict, message: discord.Message):
    existing = db.get_starboard_post(message.id, board["id"])
    if existing:
        db.update_starboard_post(message.id, board["id"], forced=True)
    else:
        db.upsert_starboard_post(
            message_id=message.id,
            board_id=board["id"],
            guild_id=message.guild.id,
            channel_id=message.channel.id,
            author_id=message.author.id,
            forced=True,
        )
    await process_board(bot, board, message, board["emoji"], force=True)


def block_starboard_message(message_id: int, board_id: int, blocked: bool):
    db.update_starboard_post(message_id, board_id, blocked=blocked)
