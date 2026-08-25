"""Direct and scheduled role grants/removals for individual members."""
import datetime as dt

import discord
from discord import app_commands

from commands.common import GuildOnlyGroup, owner_or_permissions
from commands.permissions.helpers import record_role_deny_attempt
from database import db
from utils.logger import logger
from utils.interaction_helpers import send_error, send_success, error_response
from utils.role_permissions import check_role_hierarchy
from utils.role_parsing import parse_role_list


def _parse_duration_seconds(duration: str) -> int | None:
    """Parse shorthand duration strings like 10m/2h/1d into seconds."""
    import re

    if not duration:
        return None
    match = re.fullmatch(r"(\d+)([smhd])", duration.strip().lower())
    if not match:
        return None
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return int(match.group(1)) * multipliers.get(match.group(2), 0)


class PermissionsRoleGroup(GuildOnlyGroup):
    """Direct and scheduled role grants for individual members."""

    def __init__(self):
        super().__init__(name="role", description="Add, remove, or schedule roles for a member")

    @app_commands.command(name="set", description="Add or remove a role from a specific member")
    @app_commands.describe(user="The member to modify", role="The role to add or remove", action="Add or remove")
    @app_commands.choices(action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Remove", value="remove"),
    ])
    @owner_or_permissions(manage_roles=True)
    async def set_role(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role, action: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        try:
            error = check_role_hierarchy(interaction.user, interaction.guild.me, role)
            if error:
                await send_error(interaction, error)
                return

            if action.value == "add":
                if role in user.roles:
                    await interaction.followup.send(f"ℹ️ {user.mention} already has {role.mention}.", ephemeral=True)
                    return
                if db.is_role_denied(interaction.guild.id, user.id, role.id):
                    logger.warning(f"[ROLE DENY] Blocked /permissions role set add by {interaction.user.id} for user {user.id} role {role.id}")
                    await record_role_deny_attempt(
                        interaction.guild, user, role, source="permissions_role_set",
                        actor_user_id=interaction.user.id, notes="Blocked by role deny policy during role set add",
                    )
                    await send_error(interaction, f"Cannot add {role.mention} to {user.mention}: role is denied for this user.")
                    return
                await user.add_roles(role, reason=f"Set by {interaction.user}")
                await send_success(interaction, f"Added {role.mention} to {user.mention}.")
            else:
                if role not in user.roles:
                    await interaction.followup.send(f"ℹ️ {user.mention} does not have {role.mention}.", ephemeral=True)
                    return
                await user.remove_roles(role, reason=f"Removed by {interaction.user}")
                await send_success(interaction, f"Removed {role.mention} from {user.mention}.")
        except Exception as e:
            await error_response(interaction, e, context="permissions_role_set")

    @app_commands.command(name="temp", description="Add a role to a member for a limited duration (auto-removes after)")
    @app_commands.describe(user="The member to modify", role="The role to add temporarily", duration="How long to keep it (e.g., 30m, 2h, 1d)")
    @owner_or_permissions(manage_roles=True)
    async def temp_role(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role, duration: str):
        seconds = _parse_duration_seconds(duration)
        max_seconds = 60 * 60 * 24 * 30
        if not seconds or seconds <= 0:
            await send_error(interaction, "Invalid duration. Use formats like `30m`, `2h`, or `1d`.")
            return
        if seconds > max_seconds:
            await send_error(interaction, "Duration too long. Please choose 30 days or less.")
            return

        await interaction.response.defer(ephemeral=True)
        try:
            error = check_role_hierarchy(interaction.user, interaction.guild.me, role)
            if error:
                await send_error(interaction, error)
                return

            added_now = False
            if role not in user.roles:
                if db.is_role_denied(interaction.guild.id, user.id, role.id):
                    logger.warning(f"[ROLE DENY] Blocked /permissions role temp by {interaction.user.id} for user {user.id} role {role.id}")
                    await record_role_deny_attempt(
                        interaction.guild, user, role, source="permissions_role_temp",
                        actor_user_id=interaction.user.id, notes="Blocked by role deny policy during role temp",
                    )
                    await send_error(interaction, f"Cannot set temporary role: {role.mention} is denied for {user.mention}.")
                    return
                await user.add_roles(role, reason=f"Temporary role until {duration} (set by {interaction.user})")
                added_now = True

            expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)
            if not db.connection_pool:
                db.init_pool()

            sched_id = db.create_scheduled_role_change(interaction.guild.id, user.id, [], [role.id], expires_at, interaction.user.id)

            await interaction.followup.send(
                f"✅ {role.mention} {'added to' if added_now else 'already on'} {user.mention}.\n"
                f"⏳ Will be removed at <t:{int(expires_at.timestamp())}:F> (<t:{int(expires_at.timestamp())}:R>)\n"
                f"🪪 Scheduled job ID: `{sched_id}` (managed by scheduled role runner)",
                ephemeral=True,
            )
        except Exception as e:
            await error_response(interaction, e, context="permissions_role_temp")

    @app_commands.command(name="schedule", description="Schedule role add/remove for a member at a specific time")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        user="User to modify",
        add_roles="Roles to add at the scheduled time (mentions, names, or IDs, comma-separated)",
        remove_roles="Roles to remove at the scheduled time (mentions, names, or IDs, comma-separated)",
        run_at="When to apply (ISO timestamp, e.g., 2024-12-31T23:59:00Z)",
    )
    async def schedule(self, interaction: discord.Interaction, user: discord.Member, run_at: str, add_roles: str = "", remove_roles: str = ""):
        await interaction.response.defer(ephemeral=True)
        if not db.connection_pool:
            db.init_pool()

        add_list, unresolved_a = parse_role_list(interaction.guild, add_roles)
        rem_list, unresolved_r = parse_role_list(interaction.guild, remove_roles)

        try:
            run_dt = dt.datetime.fromisoformat(run_at.replace("Z", "+00:00"))
        except Exception:
            await send_error(interaction, "Invalid run_at format. Use ISO like 2024-12-31T23:59:00Z.")
            return

        sched_id = db.create_scheduled_role_change(
            interaction.guild.id, user.id, [r.id for r in add_list], [r.id for r in rem_list], run_dt, interaction.user.id
        )
        add_text = ", ".join(r.mention for r in add_list) if add_list else "None"
        rem_text = ", ".join(r.mention for r in rem_list) if rem_list else "None"

        lines = [
            f"✅ Scheduled role change `{sched_id}` for {user.mention}",
            f"• Add: {add_text}",
            f"• Remove: {rem_text}",
            f"• At: <t:{int(run_dt.timestamp())}:F>",
        ]
        unresolved = unresolved_a + unresolved_r
        if unresolved:
            lines.append(f"⚠️ Could not resolve: {', '.join(unresolved)}")

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name="schedule_list", description="List scheduled role changes")
    @app_commands.default_permissions(administrator=True)
    async def schedule_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not db.connection_pool:
            db.init_pool()
        entries = db.list_scheduled_role_changes(interaction.guild.id)
        if not entries:
            await interaction.followup.send("📋 No scheduled role changes.", ephemeral=True)
            return

        lines = []
        for e in entries[:20]:
            add_mentions = [interaction.guild.get_role(rid).mention for rid in e["add_ids"] if interaction.guild.get_role(rid)]
            rem_mentions = [interaction.guild.get_role(rid).mention for rid in e["remove_ids"] if interaction.guild.get_role(rid)]
            user_obj = interaction.guild.get_member(e["user_id"])
            lines.append(
                f"ID `{e['id']}` • User: {user_obj.mention if user_obj else e['user_id']} • "
                f"Adds: {', '.join(add_mentions) if add_mentions else 'None'} • "
                f"Removes: {', '.join(rem_mentions) if rem_mentions else 'None'} • "
                f"Run at: <t:{int(e['run_at'].timestamp())}:F> • Status: {e['status']}"
                + (f" • Error: {e['last_error']}" if e.get("last_error") else "")
            )
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name="schedule_delete", description="Delete a scheduled role change")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(schedule_id="ID of the scheduled change to delete (from schedule_list)")
    async def schedule_delete(self, interaction: discord.Interaction, schedule_id: int):
        await interaction.response.defer(ephemeral=True)
        if not db.connection_pool:
            db.init_pool()
        db.delete_scheduled_role_change(schedule_id, interaction.guild.id)
        await send_success(interaction, f"Deleted scheduled role change `{schedule_id}`.")
