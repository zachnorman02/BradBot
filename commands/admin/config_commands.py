"""Per-server feature configuration unrelated to any settings panel:
the counting-game channel/penalty role, and level-role naming."""
import discord
from discord import app_commands

from commands.common import GuildOnlyGroup
from commands.admin.modals import CountingConfigModal, LevelSettingsModal
from database import db
from utils.interaction_helpers import send_error, send_success


class AdminConfigGroup(GuildOnlyGroup):
    """Per-server feature configuration (counting, level roles)."""

    def __init__(self):
        super().__init__(name="config", description="Counting and level-role configuration")

    @app_commands.command(name="counting_config", description="Configure counting channel and penalty role")
    @app_commands.describe(
        channel="Channel to use for counting",
        disable="Disable counting in this server",
    )
    @app_commands.default_permissions(administrator=True)
    async def counting_config(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        disable: bool = False,
    ):
        """Set or disable the counting channel and penalty role."""
        if disable:
            await interaction.response.defer(ephemeral=True)
            if not db.connection_pool:
                db.init_pool()
            db.clear_counting_config(interaction.guild.id)
            await interaction.followup.send("🛑 Counting disabled and configuration cleared.", ephemeral=True)
            return

        if not channel:
            await send_error(interaction, "Please specify a channel for counting.")
            return

        if not db.connection_pool:
            db.init_pool()
        existing = db.get_counting_config(interaction.guild.id)
        await interaction.response.send_modal(CountingConfigModal(channel=channel, existing=existing))

    @app_commands.command(name="counting_set_number", description="Set the next expected counting number")
    @app_commands.describe(number="The next number users should post")
    @app_commands.default_permissions(administrator=True)
    async def counting_set_number(self, interaction: discord.Interaction, number: int):
        """Allow admins to set the counter to a specific number."""
        await interaction.response.defer(ephemeral=True)
        cfg = db.get_counting_config(interaction.guild.id)
        if not cfg:
            await send_error(interaction, "Counting is not configured. Run `/admin config counting_config` first.")
            return

        number = max(1, number)
        db.set_counting_number(interaction.guild.id, number)
        await send_success(interaction, f"Counting set. Next expected number is now **{number}**.")

    @app_commands.command(name="level_settings", description="Configure level role naming and verified/unverified roles")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(show="If true, only show current settings")
    async def level_settings(self, interaction: discord.Interaction, show: bool = False):
        """Configure how level/verified roles are detected (per guild)."""
        if not db.connection_pool:
            db.init_pool()

        current_prefix = db.get_guild_setting(interaction.guild.id, "level_role_prefix", "lvl ")
        current_verified = db.get_guild_setting(interaction.guild.id, "verified_role_name", "verified")
        current_unverified = db.get_guild_setting(interaction.guild.id, "unverified_role_name", "unverified")

        if show:
            await interaction.response.send_message(
                f"📋 Level settings:\n• level_role_prefix: `{current_prefix}`\n"
                f"• verified_role_name: `{current_verified}`\n• unverified_role_name: `{current_unverified}`",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            LevelSettingsModal(interaction.guild, current_prefix, current_verified, current_unverified)
        )
