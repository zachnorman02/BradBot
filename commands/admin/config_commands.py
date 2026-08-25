"""Per-server feature configuration unrelated to any settings panel:
the counting-game channel/penalty role, and level-role naming."""
import discord
from discord import app_commands

from commands.common import GuildOnlyGroup
from database import db
from utils.interaction_helpers import send_error, send_success


class AdminConfigGroup(GuildOnlyGroup):
    """Per-server feature configuration (counting, level roles)."""

    def __init__(self):
        super().__init__(name="config", description="Counting and level-role configuration")

    @app_commands.command(name="counting_config", description="Configure counting channel and penalty role")
    @app_commands.describe(
        channel="Channel to use for counting",
        idiot_role="Role to give users who break the count (24h)",
        start_number="Number to start from (next expected) — leave blank to keep current",
        disable="Disable counting in this server",
        clear_idiot_role="Clear any existing penalty role",
    )
    @app_commands.default_permissions(administrator=True)
    async def counting_config(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        idiot_role: discord.Role | None = None,
        start_number: int | None = None,
        disable: bool = False,
        clear_idiot_role: bool = False,
    ):
        """Set or disable the counting channel and penalty role."""
        await interaction.response.defer(ephemeral=True)
        if not db.connection_pool:
            db.init_pool()

        existing = db.get_counting_config(interaction.guild.id)

        if disable:
            db.clear_counting_config(interaction.guild.id)
            await interaction.followup.send("🛑 Counting disabled and configuration cleared.", ephemeral=True)
            return

        if not channel:
            await send_error(interaction, "Please specify a channel for counting.")
            return

        if start_number is not None:
            start_number = max(1, start_number)
        elif existing and existing.get("next_number"):
            start_number = existing["next_number"]
        else:
            start_number = 1

        idiot_role_obj = None
        idiot_role_id = None
        if clear_idiot_role:
            idiot_role_id = None
        elif idiot_role:
            idiot_role_obj = idiot_role
            idiot_role_id = idiot_role.id
        elif existing and existing.get("idiot_role_id"):
            idiot_role_id = existing["idiot_role_id"]
            idiot_role_obj = interaction.guild.get_role(idiot_role_id)

        db.set_counting_config(interaction.guild.id, channel.id, idiot_role_id, start_number)

        if idiot_role_obj:
            role_text = idiot_role_obj.mention
        elif clear_idiot_role:
            role_text = "None (penalty role cleared)"
        else:
            role_text = "None (penalties skipped)"

        await interaction.followup.send(
            f"✅ Counting configured.\n• Channel: {channel.mention}\n• Penalty role: {role_text}\n• Next number: {start_number}",
            ephemeral=True,
        )

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
    @app_commands.describe(
        level_prefix="Prefix for level roles (default: 'lvl ')",
        verified_role="Role considered verified (default: 'Verified')",
        unverified_role="Role considered unverified (default: 'Unverified')",
        show="If true, only show current settings",
    )
    async def level_settings(
        self,
        interaction: discord.Interaction,
        level_prefix: str | None = None,
        verified_role: discord.Role | None = None,
        unverified_role: discord.Role | None = None,
        show: bool = False,
    ):
        """Configure how level/verified roles are detected (per guild)."""
        await interaction.response.defer(ephemeral=True)
        if not db.connection_pool:
            db.init_pool()

        current_prefix = db.get_guild_setting(interaction.guild.id, "level_role_prefix", "lvl ")
        current_verified = db.get_guild_setting(interaction.guild.id, "verified_role_name", "verified")
        current_unverified = db.get_guild_setting(interaction.guild.id, "unverified_role_name", "unverified")

        if show or (level_prefix is None and verified_role is None and unverified_role is None):
            await interaction.followup.send(
                f"📋 Level settings:\n• level_role_prefix: `{current_prefix}`\n"
                f"• verified_role_name: `{current_verified}`\n• unverified_role_name: `{current_unverified}`",
                ephemeral=True,
            )
            return

        if level_prefix is not None:
            db.set_guild_setting(interaction.guild.id, "level_role_prefix", level_prefix)
            current_prefix = level_prefix
        if verified_role is not None:
            db.set_guild_setting(interaction.guild.id, "verified_role_name", verified_role.name)
            current_verified = verified_role.name
        if unverified_role is not None:
            db.set_guild_setting(interaction.guild.id, "unverified_role_name", unverified_role.name)
            current_unverified = unverified_role.name

        await interaction.followup.send(
            f"✅ Updated level settings:\n• level_role_prefix: `{current_prefix}`\n"
            f"• verified_role_name: `{current_verified}`\n• unverified_role_name: `{current_unverified}`",
            ephemeral=True,
        )
