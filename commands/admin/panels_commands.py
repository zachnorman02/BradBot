"""Interactive admin settings panels: the toggle-button UI for server
settings and for enabling/disabling echo/tts, each available as an
ephemeral menu (just for you) or a persistent panel (posted to a channel
for any admin to use)."""
import datetime as dt

import discord
from discord import app_commands

import config
from commands.common import GuildOnlyGroup
from commands.admin.views import AdminSettingsView, CommandToggleView
from database import db
from utils.logger import logger
from utils.interaction_helpers import send_error, send_success, error_response


class AdminPanelsGroup(GuildOnlyGroup):
    """Interactive settings panels (ephemeral menus and persistent posted panels)."""

    def __init__(self):
        super().__init__(name="panels", description="Interactive server settings panels")

    @app_commands.command(name="settings_menu", description="Open server settings menu")
    @app_commands.default_permissions(administrator=True)
    async def settings_menu(self, interaction: discord.Interaction):
        """Open interactive admin settings menu."""
        try:
            if not db.connection_pool:
                db.init_pool()
            view = AdminSettingsView(interaction.guild.id)
            await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=True)
        except Exception as e:
            logger.error(f"Error opening admin menu: {e}")
            await send_error(interaction, "An error occurred while opening the admin menu.")

    @app_commands.command(name="settings_panel", description="Create a persistent server settings panel in this channel")
    @app_commands.default_permissions(administrator=True)
    async def settings_panel(self, interaction: discord.Interaction):
        """Create a persistent admin settings panel in the channel."""
        try:
            if not db.connection_pool:
                db.init_pool()

            custom_prefix = f"admin_panel:{interaction.guild.id}:{int(dt.datetime.now(dt.timezone.utc).timestamp())}"
            view = AdminSettingsView(interaction.guild.id, persistent=True, custom_id_prefix=custom_prefix)

            message = await interaction.channel.send(embed=view.get_embed(), view=view)
            interaction.client.add_view(view, message_id=message.id)

            db.save_persistent_panel(
                message_id=message.id,
                guild_id=interaction.guild.id,
                channel_id=interaction.channel.id,
                panel_type=config.PANEL_TYPE_ADMIN_SETTINGS,
                metadata={'custom_id_prefix': custom_prefix},
            )

            await send_success(interaction, "Persistent admin panel created! Anyone with administrator permissions can use it.")
        except Exception as e:
            logger.error(f"Error creating admin panel: {e}")
            await send_error(interaction, "An error occurred while creating the admin panel.")

    @app_commands.command(name="commands_menu", description="Open command toggles menu")
    @app_commands.default_permissions(administrator=True)
    async def commands_menu(self, interaction: discord.Interaction):
        """Open interactive command toggle menu (echo/TTS)."""
        try:
            view = CommandToggleView(interaction.guild.id)
            await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=True)
        except Exception as e:
            logger.error(f"Error opening command toggle menu: {e}")
            await send_error(interaction, "An error occurred while opening the command toggle menu.")

    @app_commands.command(name="commands_panel", description="Create a persistent command toggles panel in this channel")
    @app_commands.default_permissions(administrator=True)
    async def commands_panel(self, interaction: discord.Interaction):
        """Create a persistent panel to toggle echo/TTS commands."""
        try:
            await interaction.response.defer(ephemeral=True)

            custom_prefix = f"command_panel:{interaction.guild.id}:{int(dt.datetime.now(dt.timezone.utc).timestamp())}"
            view = CommandToggleView(interaction.guild.id, persistent=True, custom_id_prefix=custom_prefix)
            view.timeout = None
            view._set_persistent_custom_ids()
            view.update_buttons()

            message = await interaction.channel.send(embed=view.get_embed(), view=view)
            interaction.client.add_view(view, message_id=message.id)

            db.save_persistent_panel(
                message_id=message.id,
                guild_id=interaction.guild.id,
                channel_id=interaction.channel.id,
                panel_type=config.PANEL_TYPE_COMMAND_SETTINGS,
                metadata={'custom_id_prefix': custom_prefix},
            )

            await interaction.followup.send("✅ Persistent command panel created! Administrators can toggle echo/TTS here.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating command panel: {e}")
            await error_response(interaction, e, context="commands_panel")
