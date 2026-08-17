"""Booster role commands. Replaces the old 4-command surface (restore,
color, label, icon) with 2: `restore` (recovery) and `customize` (a single
Modal covering name/color/icon -- see commands/booster/modals.py)."""
import discord
from discord import app_commands

from commands.booster.modals import BoosterCustomizeModal
from database import db
from utils.interaction_helpers import send_error, send_success, error_response


def _is_booster(member: discord.Member) -> bool:
    return any(role.is_premium_subscriber() for role in member.roles)


async def _can_use_booster_commands(interaction: discord.Interaction) -> bool:
    """Real boosters can always use these; the bot owner can too, so they
    can test booster-role behavior without actually boosting the server."""
    if _is_booster(interaction.user):
        return True
    app_info = await interaction.client.application_info()
    return interaction.user.id == app_info.owner.id


class BoosterRoleGroup(app_commands.Group):
    """Booster role customization commands."""

    def __init__(self):
        super().__init__(name="role", description="Customize your server booster role")

    @app_commands.command(name="restore", description="Restore your booster role (recreate if missing and reapply saved icon/colors)")
    async def restore(self, interaction: discord.Interaction):
        """Force re-fetch/create the personal booster role and reapply saved data (icon/colors)."""
        if not await _can_use_booster_commands(interaction):
            await send_error(interaction, "This command is only available to server boosters!")
            return

        from commands.booster.helpers import get_or_create_booster_role, _apply_icon

        db_role_data = db.get_booster_role(interaction.user.id, interaction.guild.id)
        if not db_role_data:
            await send_error(interaction, "No saved booster role data found.")
            return

        role = await get_or_create_booster_role(interaction, db_role_data)
        if not role:
            await send_error(interaction, "Could not restore your booster role.")
            return

        icon_applied = role.icon is not None
        if not icon_applied and db_role_data.get("icon_data"):
            icon_applied = await _apply_icon(role, db_role_data.get("icon_data"), interaction.guild)

        await interaction.response.send_message(
            f"✅ Booster role restored: {role.mention}\n"
            f"• Name: {role.name}\n"
            f"• Color type: {db_role_data.get('color_type', 'solid')}\n"
            f"• Icon: {'applied' if icon_applied else ('saved but failed' if db_role_data.get('icon_data') else 'none saved')}",
            ephemeral=True,
        )

    @app_commands.command(name="customize", description="Customize your booster role's name, color, and icon")
    async def customize(self, interaction: discord.Interaction):
        """Opens a single form covering name, color(s), holographic, and icon (including clearing it)."""
        if not await _can_use_booster_commands(interaction):
            await send_error(interaction, "This command is only available to server boosters!")
            return

        from commands.booster.helpers import get_or_create_booster_role

        db_role_data = db.get_booster_role(interaction.user.id, interaction.guild.id)
        role = await get_or_create_booster_role(interaction, db_role_data)
        if not role:
            await send_error(interaction, "Could not find or create your booster role.")
            return

        await interaction.response.send_modal(BoosterCustomizeModal(role=role, member=interaction.user))


class BoosterGroup(app_commands.Group):
    """Server booster commands."""

    def __init__(self):
        super().__init__(name="booster", description="Server booster role commands")
        self.add_command(BoosterRoleGroup())
