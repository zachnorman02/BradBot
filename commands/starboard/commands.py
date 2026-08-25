"""Starboard configuration commands. `lock`/`block`/`unblock` are replaced
entirely by the message context menus in context_menus.py."""
import discord
from discord import app_commands

from database import db
from utils.interaction_helpers import send_error, send_success, has_permission_or_owner
from commands.starboard.helpers import normalize_emoji_str


class StarboardGroup(app_commands.Group):
    """Configure hall-of-fame starboard channels."""

    def __init__(self):
        super().__init__(name="starboard", description="Manage starboard channels")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if await has_permission_or_owner(interaction, administrator=True):
            return True
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
        return False

    @app_commands.command(name="set", description="Create or update a starboard channel")
    @app_commands.describe(channel="Channel where starboard posts are sent", emoji="Emoji that triggers this board", threshold="Number of reactions required", allow_nsfw="Allow posts from NSFW channels")
    async def set_board(self, interaction: discord.Interaction, channel: discord.TextChannel, emoji: str, threshold: app_commands.Range[int, 1, None], allow_nsfw: bool = False):
        if not await has_permission_or_owner(interaction, manage_guild=True):
            await send_error(interaction, "You need Manage Server to do that.")
            return
        emoji_str = normalize_emoji_str(discord.PartialEmoji.from_str(emoji) or emoji)
        db.upsert_starboard_board(interaction.guild.id, channel.id, emoji_str, threshold, allow_nsfw)
        await send_success(interaction, f"Starboard set for {channel.mention} ({emoji_str} × {threshold}, NSFW allowed: {allow_nsfw}).")

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
            lines.append(f"{channel_name} — {board['emoji']} × {board['threshold']} • {'Allows' if board['allow_nsfw'] else 'Blocks'} NSFW")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="delete", description="Remove a starboard channel")
    async def delete_board(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await has_permission_or_owner(interaction, manage_guild=True):
            await send_error(interaction, "You need Manage Server to do that.")
            return
        db.delete_starboard_board(interaction.guild.id, channel.id)
        await send_success(interaction, f"Removed starboard for {channel.mention}.")

    @app_commands.command(name="top", description="List the most starred messages for a board")
    async def top_messages(self, interaction: discord.Interaction, starboard_channel: discord.TextChannel, limit: app_commands.Range[int, 1, 20] = 5):
        board = db.get_starboard_board(interaction.guild.id, starboard_channel.id)
        if not board:
            await send_error(interaction, "That channel is not a starboard.")
            return
        entries = db.list_top_starboard_posts(board["id"], limit)
        if not entries:
            await interaction.response.send_message("ℹ️ No starred messages yet.", ephemeral=True)
            return
        lines = []
        for entry in entries:
            channel = interaction.guild.get_channel(entry["channel_id"])
            channel_name = channel.mention if channel else f"`{entry['channel_id']}`"
            lines.append(f"{entry['current_count']} {board['emoji']} — {channel_name} (Message ID `{entry['message_id']}`)")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)
