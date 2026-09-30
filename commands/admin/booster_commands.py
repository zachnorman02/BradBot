"""Admin controls for booster-role auto-detection/auto-creation:

- exclude/include/list: which roles are eligible to be auto-detected as
  someone's personal booster role (see commands/booster/helpers.py's
  find_personal_roles "exactly one member" heuristic).
- list_users: which users the bot should skip auto-creating/restoring a role
  for when they start boosting (see core/tasks.py's handle_booster_started).
  Manual /booster customize or /booster restore still work for an excluded
  user -- this only blocks the automatic on-boost creation. The
  exclude/include-a-user actions themselves are the "Exclude From Booster"/
  "Include In Booster" user context menus (commands/admin/context_menus.py)
  -- listing needs no target, so it stays a plain command, but toggling one
  specific user is exactly the "right-click them" shape.
"""
import discord
from discord import app_commands

from commands.common import GuildOnlyGroup, owner_or_permissions
from utils.interaction_helpers import send_error, send_success


class AdminBoosterGroup(GuildOnlyGroup):
    """Admin controls for booster-role detection."""

    def __init__(self):
        super().__init__(name="booster", description="Control which roles/users can get a booster role")

    @app_commands.command(name="exclude", description="Prevent a role from ever being treated as someone's booster role")
    @app_commands.describe(role="Role to exclude (e.g. an Admin role, a VIP award role)")
    @owner_or_permissions(manage_roles=True)
    async def exclude(self, interaction: discord.Interaction, role: discord.Role):
        """Guards against the 'exactly one member' personal-role heuristic
        picking up a role that just happens to have a single current holder
        but isn't meant to be anyone's customizable booster role."""
        from commands.booster.helpers import add_excluded_role

        purged = add_excluded_role(interaction.guild.id, role.id)
        note = f" ({purged} saved DB record(s) for this role also cleared.)" if purged else ""
        await send_success(interaction, f"{role.mention} will no longer be detected as anyone's booster role.{note}")

    @app_commands.command(name="include", description="Allow a previously-excluded role to be treated as a booster role again")
    @app_commands.describe(role="Role to remove from the exclude list")
    @owner_or_permissions(manage_roles=True)
    async def include(self, interaction: discord.Interaction, role: discord.Role):
        from commands.booster.helpers import remove_excluded_role

        if remove_excluded_role(interaction.guild.id, role.id):
            await send_success(interaction, f"{role.mention} can be detected as a booster role again.")
        else:
            await send_error(interaction, f"{role.mention} wasn't on the exclude list.")

    @app_commands.command(name="list", description="List roles excluded from booster-role detection")
    @owner_or_permissions(manage_roles=True)
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

    @app_commands.command(name="list_users", description="List users excluded from automatic booster-role creation")
    @owner_or_permissions(manage_roles=True)
    async def list_users(self, interaction: discord.Interaction):
        from commands.booster.helpers import get_excluded_user_ids

        excluded_ids = get_excluded_user_ids(interaction.guild.id)
        if not excluded_ids:
            await interaction.response.send_message("No users are currently excluded from automatic booster-role creation.", ephemeral=True)
            return

        lines = [f"• <@{user_id}>" for user_id in excluded_ids]
        await interaction.response.send_message("**Excluded from automatic booster-role creation:**\n" + "\n".join(lines), ephemeral=True)
