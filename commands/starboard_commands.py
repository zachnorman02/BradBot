import re

import discord
from discord import app_commands

from database import db
from core import starboard as starboard_core


def _parse_message_link(link: str):
    message_link_re = re.compile(
        r"https?://(?:canary\.|ptb\.)?discord(?:app)?\.com/channels/(?P<guild_id>\d+|@me)/(?P<channel_id>\d+)/(?P<message_id>\d+)"
    )
    match = message_link_re.match(link.strip())
    if not match:
        return None
    if match.group("guild_id") == "@me":
        return None
    return int(match.group("guild_id")), int(match.group("channel_id")), int(match.group("message_id"))


def _normalize_emoji_str(emoji: discord.PartialEmoji | str) -> str:
    if isinstance(emoji, discord.PartialEmoji):
        return emoji.to_str()
    return emoji


class StarboardGroup(app_commands.Group):
    """Configure hall-of-fame starboard channels."""

    def __init__(self):
        super().__init__(name="starboard", description="Manage starboard channels")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
        return False


    @app_commands.command(name="set", description="Create or update a starboard channel")
    @app_commands.describe(
        channel="Channel where starboard posts are sent",
        emoji="Emoji that triggers this board",
        threshold="Number of reactions required",
        allow_nsfw="Allow posts from NSFW channels"
    )
    async def set_board(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        emoji: str,
        threshold: app_commands.Range[int, 1, None],
        allow_nsfw: bool = False
    ):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need Manage Server to do that.", ephemeral=True)
            return
        emoji_str = _normalize_emoji_str(discord.PartialEmoji.from_str(emoji) or emoji)
        board_id = db.upsert_starboard_board(interaction.guild.id, channel.id, emoji_str, threshold, allow_nsfw)
        await interaction.response.send_message(
            f"✅ Starboard set for {channel.mention} ({emoji_str} × {threshold}, NSFW allowed: {allow_nsfw}).",
            ephemeral=True
        )

    @app_commands.command(name="list", description="List starboard channels in this server")
    async def list_boards(self, interaction: discord.Interaction):
        boards = db.get_starboard_boards(interaction.guild.id)
        if not boards:
            await interaction.response.send_message("ℹ️ No starboards configured.", ephemeral=True)
            return
        lines = []
        for board in boards:
            channel = interaction.guild.get_channel(board["channel_id"])
            channel_name = channel.mention if channel else f"`{board['channel_id']}`"
            lines.append(
                f"{channel_name} — {board['emoji']} × {board['threshold']} • "
                f"{'Allows' if board['allow_nsfw'] else 'Blocks'} NSFW"
            )
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="delete", description="Remove a starboard channel")
    async def delete_board(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need Manage Server to do that.", ephemeral=True)
            return
        db.delete_starboard_board(interaction.guild.id, channel.id)
        await interaction.response.send_message(f"✅ Removed starboard for {channel.mention}.", ephemeral=True)

    async def _fetch_message_from_link(self, interaction: discord.Interaction, message_link: str):
        parsed = _parse_message_link(message_link)
        if not parsed:
            await interaction.response.send_message("❌ Invalid message link.", ephemeral=True)
            return None
        guild_id, channel_id, message_id = parsed
        if guild_id != interaction.guild.id:
            await interaction.response.send_message("❌ That message is not from this server.", ephemeral=True)
            return None
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            try:
                channel = await interaction.guild.fetch_channel(channel_id)
            except discord.DiscordException:
                await interaction.response.send_message("❌ I cannot access that channel.", ephemeral=True)
                return None
        try:
            return await channel.fetch_message(message_id)
        except discord.DiscordException:
            await interaction.response.send_message("❌ Unable to fetch that message.", ephemeral=True)
            return None

    @app_commands.command(name="lock", description="Force a message into a starboard immediately")
    async def lock_message(
        self,
        interaction: discord.Interaction,
        message_link: str,
        starboard_channel: discord.TextChannel
    ):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You need Manage Messages to use this.", ephemeral=True)
            return
        board = db.get_starboard_board(interaction.guild.id, starboard_channel.id)
        if not board:
            await interaction.response.send_message("❌ That channel is not a starboard.", ephemeral=True)
            return
        message = await self._fetch_message_from_link(interaction, message_link)
        if not message:
            return
        await starboard_core.force_starboard_post(interaction.client, board, message)
        await interaction.response.send_message("✅ Message locked to starboard.", ephemeral=True)

    @app_commands.command(name="block", description="Block a message from being starred")
    async def block_message(
        self,
        interaction: discord.Interaction,
        message_link: str,
        starboard_channel: discord.TextChannel
    ):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You need Manage Messages.", ephemeral=True)
            return
        board = db.get_starboard_board(interaction.guild.id, starboard_channel.id)
        if not board:
            await interaction.response.send_message("❌ That channel is not a starboard.", ephemeral=True)
            return
        message = await self._fetch_message_from_link(interaction, message_link)
        if not message:
            return
        entry = db.get_starboard_post(message.id, board["id"])
        db.upsert_starboard_post(
            message_id=message.id,
            board_id=board["id"],
            guild_id=interaction.guild.id,
            channel_id=message.channel.id,
            author_id=message.author.id,
            star_message_id=entry.get("star_message_id") if entry else None,
            count=entry.get("current_count") if entry else 0,
            forced=entry.get("forced") if entry else False,
            blocked=True
        )
        if entry and entry.get("star_message_id"):
            channel = interaction.guild.get_channel(board["channel_id"])
            if channel:
                try:
                    star_msg = await channel.fetch_message(entry["star_message_id"])
                    await star_msg.delete()
                except discord.DiscordException:
                    pass
        await interaction.response.send_message("✅ Message blocked from starboard.", ephemeral=True)

    @app_commands.command(name="unblock", description="Remove block/force overrides for a message")
    async def unblock_message(
        self,
        interaction: discord.Interaction,
        message_link: str,
        starboard_channel: discord.TextChannel
    ):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You need Manage Messages.", ephemeral=True)
            return
        board = db.get_starboard_board(interaction.guild.id, starboard_channel.id)
        if not board:
            await interaction.response.send_message("❌ That channel is not a starboard.", ephemeral=True)
            return
        message = await self._fetch_message_from_link(interaction, message_link)
        if not message:
            return
        entry = db.get_starboard_post(message.id, board["id"])
        if entry:
            db.update_starboard_post(message.id, board["id"], blocked=False, forced=False)
        await starboard_core.process_board(interaction.client, board, message, board["emoji"])
        await interaction.response.send_message("✅ Overrides cleared.", ephemeral=True)

    @app_commands.command(name="top", description="List the most starred messages for a board")
    async def top_messages(
        self,
        interaction: discord.Interaction,
        starboard_channel: discord.TextChannel,
        limit: app_commands.Range[int, 1, 20] = 5
    ):
        board = db.get_starboard_board(interaction.guild.id, starboard_channel.id)
        if not board:
            await interaction.response.send_message("❌ That channel is not a starboard.", ephemeral=True)
            return
        entries = db.list_top_starboard_posts(board["id"], limit)
        if not entries:
            await interaction.response.send_message("ℹ️ No starred messages yet.", ephemeral=True)
            return
        lines = []
        for entry in entries:
            channel = interaction.guild.get_channel(entry["channel_id"])
            channel_name = channel.mention if channel else f"`{entry['channel_id']}`"
            lines.append(
                f"{entry['current_count']} {board['emoji']} — {channel_name} "
                f"(Message ID `{entry['message_id']}`)"
            )
        await interaction.response.send_message("\n".join(lines), ephemeral=True)
