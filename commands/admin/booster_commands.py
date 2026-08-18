"""Admin controls for which roles are eligible to be auto-detected as
someone's personal booster role (see commands/booster/helpers.py's
find_personal_roles "exactly one member" heuristic)."""
import discord
from discord import app_commands

from commands.common import GuildOnlyGroup
from utils.interaction_helpers import send_error, send_success


class AdminBoosterGroup(GuildOnlyGroup):
    """Admin controls for booster-role detection."""

    def __init__(self):
        super().__init__(name="booster", description="Control which roles can be detected as booster roles")

    @app_commands.command(name="exclude", description="Prevent a role from ever being treated as someone's booster role")
    @app_commands.describe(role="Role to exclude (e.g. an Admin role, a VIP award role)")
    @app_commands.default_permissions(administrator=True)
    async def exclude(self, interaction: discord.Interaction, role: discord.Role):
        """Guards against the 'exactly one member' personal-role heuristic
        picking up a role that just happens to have a single current holder
        but isn't meant to be anyone's customizable booster role."""
        from commands.booster.helpers import add_excluded_role

        add_excluded_role(interaction.guild.id, role.id)
        await send_success(interaction, f"{role.mention} will no longer be detected as anyone's booster role.")

    @app_commands.command(name="include", description="Allow a previously-excluded role to be treated as a booster role again")
    @app_commands.describe(role="Role to remove from the exclude list")
    @app_commands.default_permissions(administrator=True)
    async def include(self, interaction: discord.Interaction, role: discord.Role):
        from commands.booster.helpers import remove_excluded_role

        if remove_excluded_role(interaction.guild.id, role.id):
            await send_success(interaction, f"{role.mention} can be detected as a booster role again.")
        else:
            await send_error(interaction, f"{role.mention} wasn't on the exclude list.")

    @app_commands.command(name="list", description="List roles excluded from booster-role detection")
    @app_commands.default_permissions(administrator=True)
    async def list(self, interaction: discord.Interaction):
        from commands.booster.helpers import get_excluded_role_ids

        excluded_ids = get_excluded_role_ids(interaction.guild.id)
        if not excluded_ids:
            await interaction.response.send_message("No roles are currently excluded from booster-role detection.", ephemeral=True)
            return

        lines = []
        for role_id in excluded_ids:
            role = interaction.guild.get_role(role_id)
            lines.append(f"• {role.mention if role else f'`{role_id}` (deleted role)'}")
        await interaction.response.send_message("**Excluded from booster-role detection:**\n" + "\n".join(lines), ephemeral=True)
