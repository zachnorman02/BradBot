"""User settings and preferences. `sendpings`/`notify` were removed --
they duplicated exactly what SettingsView's own buttons already do."""
import discord
from discord import app_commands

from database import db
from utils.logger import logger
from commands.settings.views import SettingsView


class SettingsGroup(app_commands.Group):
    """User settings and preferences."""

    def __init__(self):
        super().__init__(name="settings", description="User settings and preferences")

    @app_commands.command(name="menu", description="Open your settings menu")
    async def menu(self, interaction: discord.Interaction):
        """Open interactive settings menu."""
        try:
            if not db.connection_pool:
                db.init_pool()

            guild_id = interaction.guild.id if interaction.guild else None
            view = SettingsView(interaction.user.id, guild_id)
            await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=True)
        except Exception as e:
            logger.error(f"Error opening settings menu: {e}")
            await interaction.response.send_message("❌ An error occurred while opening the settings menu.", ephemeral=True)
