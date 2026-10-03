"""Direct and scheduled role grants/removals for individual members."""
import datetime as dt

import discord
from discord import app_commands, ui

from commands.common import GuildOnlyGroup, owner_or_permissions
from commands.permissions.helpers import record_role_deny_attempt
from commands.permissions.modals import ScheduleRoleModal
from database import db
from utils.logger import logger
from utils.interaction_helpers import send_error, send_success, error_response
from utils.role_permissions import check_role_hierarchy


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


class ScheduleDeleteSelect(ui.Select):
    """Dropdown of a guild's pending scheduled role changes; picking one
    deletes it immediately -- no need to look up and retype a numeric ID."""

    def __init__(self, guild: discord.Guild, entries: list[dict]):
        options = []
        for e in entries[:25]:
            member = guild.get_member(e["user_id"])
            user_label = member.display_name if member else f"User {e['user_id']}"
            add_names = [guild.get_role(rid).name for rid in e["add_ids"] if guild.get_role(rid)]
            rem_names = [guild.get_role(rid).name for rid in e["remove_ids"] if guild.get_role(rid)]
            parts = []
            if add_names:
                parts.append("+" + ",".join(add_names))
            if rem_names:
                parts.append("-" + ",".join(rem_names))
            when = e["run_at"].strftime("%Y-%m-%d %H:%M UTC")
            options.append(discord.SelectOption(
                label=f"{user_label} • {' '.join(parts)}"[:100],
                value=str(e["id"]),
                description=f"Runs {when}"[:100],
            ))
        super().__init__(placeholder="Select a scheduled change to delete...", options=options)

    async def callback(self, interaction: discord.Interaction):
        sched_id = int(self.values[0])
        db.delete_scheduled_role_change(sched_id, interaction.guild.id)
        await interaction.response.edit_message(content=f"🗑️ Deleted scheduled role change `{sched_id}`", view=None)


class ScheduleDeleteView(ui.View):
    def __init__(self, guild: discord.Guild, entries: list[dict]):
        super().__init__(timeout=300)
        self.add_item(ScheduleDeleteSelect(guild, entries))


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

    @app_commands.command(name="schedule", description="Schedule role add/remove for a member at a specific date/time")
    @app_commands.describe(user="User to modify")
    @owner_or_permissions(manage_roles=True)
    async def schedule(self, interaction: discord.Interaction, user: discord.Member):
        if not db.connection_pool:
            db.init_pool()
        await interaction.response.send_modal(ScheduleRoleModal(target_user=user))

    @app_commands.command(name="schedule_list", description="List scheduled role changes")
    @owner_or_permissions(manage_roles=True)
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
    @owner_or_permissions(manage_roles=True)
    async def schedule_delete(self, interaction: discord.Interaction):
        if not db.connection_pool:
            db.init_pool()
        entries = [e for e in db.list_scheduled_role_changes(interaction.guild.id) if e["status"] == "pending"]
        if not entries:
            await interaction.response.send_message("📋 No pending scheduled role changes.", ephemeral=True)
            return
        if len(entries) > 25:
            await interaction.response.send_message(
                "⚠️ Too many pending schedules to list in one dropdown (25 max) -- delete a few, then try again.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            "Pick a scheduled change to delete:", view=ScheduleDeleteView(interaction.guild, entries), ephemeral=True
        )
