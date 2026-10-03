"""Modals for the permissions domain -- both replace what used to be
comma-separated role-list *string* slash-command params with a small form,
using the shared utils.role_parsing.parse_role_list for resolution.
"""
import datetime as dt

import discord

from database import db
from commands.permissions.helpers import generate_role_rule_name, record_role_deny_attempt
from utils.role_parsing import parse_role_list
from utils.interaction_helpers import send_error, send_success, error_response
from utils.role_permissions import check_role_hierarchy
from utils.timestamp_helpers import create_discord_timestamp
from utils.logger import logger


class ConditionalRoleConfigModal(discord.ui.Modal, title="Configure Conditional Role"):
    blocking_roles = discord.ui.Label(
        text="Blocking Roles",
        description="Having ANY of these makes a member permanently ineligible for this role.",
        component=discord.ui.RoleSelect(min_values=0, max_values=25, required=False),
    )
    deferral_roles = discord.ui.Label(
        text="Deferral Roles",
        description="Having ANY of these makes them eligible, but delays granting the role until it's gone.",
        component=discord.ui.RoleSelect(min_values=0, max_values=25, required=False),
    )

    def __init__(self, role: discord.Role, existing: dict = None):
        super().__init__()
        self.role = role
        self.title = f"Configure: {role.name}"[:45]
        if existing:
            self.blocking_roles.component.default_values = [
                r for rid in existing.get('blocking_role_ids', []) if (r := role.guild.get_role(rid))
            ]
            self.deferral_roles.component.default_values = [
                r for rid in existing.get('deferral_role_ids', []) if (r := role.guild.get_role(rid))
            ]

    async def on_submit(self, interaction: discord.Interaction):
        blocking = list(self.blocking_roles.component.values)
        deferral = list(self.deferral_roles.component.values)

        db.add_conditional_role_config(
            interaction.guild.id, self.role.id, self.role.name,
            [r.id for r in blocking], [r.id for r in deferral],
        )

        lines = [f"✅ Configured conditional role: {self.role.mention}"]
        lines.append(f"**Blocking Roles:** {', '.join(r.mention for r in blocking) if blocking else 'None'}")
        lines.append(f"**Deferral Roles:** {', '.join(r.mention for r in deferral) if deferral else 'None'}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


class AutomationRuleModal(discord.ui.Modal, title="Configure Auto-Role Rule"):
    roles_to_add = discord.ui.Label(
        text="Roles To Add",
        description="Added to a member as soon as they get the trigger role.",
        component=discord.ui.RoleSelect(min_values=0, max_values=25, required=False),
    )
    roles_to_remove = discord.ui.Label(
        text="Roles To Remove",
        description="Removed from a member as soon as they get the trigger role.",
        component=discord.ui.RoleSelect(min_values=0, max_values=25, required=False),
    )

    def __init__(self, trigger_role: discord.Role, existing: dict = None):
        super().__init__()
        self.trigger_role = trigger_role
        self.title = f"Configure Rule: {trigger_role.name}"[:45]
        if existing:
            guild = trigger_role.guild
            self.roles_to_add.component.default_values = [
                r for rid in existing['roles_to_add'] if (r := guild.get_role(rid))
            ]
            self.roles_to_remove.component.default_values = [
                r for rid in existing['roles_to_remove'] if (r := guild.get_role(rid))
            ]

    async def on_submit(self, interaction: discord.Interaction):
        add_roles = list(self.roles_to_add.component.values)
        remove_roles = list(self.roles_to_remove.component.values)

        if not add_roles and not remove_roles:
            await send_error(interaction, "Please select at least one role to add or remove.")
            return

        rule_name = generate_role_rule_name(self.trigger_role, add_roles, remove_roles)
        db.add_role_rule(
            interaction.guild.id, rule_name, self.trigger_role.id,
            [r.id for r in add_roles], [r.id for r in remove_roles],
        )

        lines = [f"✅ Configured auto-role rule for {self.trigger_role.mention}"]
        if add_roles:
            lines.append(f"**Add:** {', '.join(r.mention for r in add_roles)}")
        if remove_roles:
            lines.append(f"**Remove:** {', '.join(r.mention for r in remove_roles)}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


class DenyModal(discord.ui.Modal, title="Role Deny"):
    role = discord.ui.Label(
        text="Role",
        description="The role this deny entry applies to.",
        component=discord.ui.RoleSelect(min_values=1, max_values=1),
    )
    action = discord.ui.Label(
        text="Action",
        description="Deny blocks the user from ever receiving the role; Allow removes an existing deny.",
        component=discord.ui.Select(options=[
            discord.SelectOption(label="Deny", value="deny", description="Block this user from receiving the role"),
            discord.SelectOption(label="Allow", value="allow", description="Remove an existing deny entry"),
        ]),
    )
    notes = discord.ui.Label(
        text="Notes (optional)",
        description="Only used when denying -- shown in /permissions deny list.",
        component=discord.ui.TextInput(style=discord.TextStyle.paragraph, required=False, max_length=500),
    )

    def __init__(self, user: discord.Member):
        super().__init__()
        self.target_user = user
        self.title = f"Role Deny: {user.display_name}"[:45]

    async def on_submit(self, interaction: discord.Interaction):
        role = self.role.component.values[0]
        action = self.action.component.values[0]
        user = self.target_user

        if not db.connection_pool:
            db.init_pool()

        if action == "deny":
            if db.is_role_denied(interaction.guild.id, user.id, role.id):
                await interaction.response.send_message(f"ℹ️ {user.mention} is already denied from receiving {role.mention}.", ephemeral=True)
                return
            db.add_role_deny(interaction.guild.id, user.id, role.id, interaction.user.id, self.notes.component.value)
            response = f"✅ Added deny: {user.mention} cannot receive {role.mention}."
            if self.notes.component.value:
                response += f"\n📝 Notes: {self.notes.component.value}"
            await interaction.response.send_message(response, ephemeral=True)
        else:
            if not db.is_role_denied(interaction.guild.id, user.id, role.id):
                await interaction.response.send_message(f"ℹ️ No deny entry exists for {user.mention} and {role.mention}.", ephemeral=True)
                return
            db.remove_role_deny(interaction.guild.id, user.id, role.id)
            await interaction.response.send_message(f"✅ Removed deny: {user.mention} can receive {role.mention} again.", ephemeral=True)


class DenyLogModal(discord.ui.Modal, title="Role Deny Logging"):
    channel = discord.ui.Label(
        text="Log Channel",
        description="Required for Set. Ignored for Test/Clear.",
        component=discord.ui.ChannelSelect(min_values=0, max_values=1, channel_types=[discord.ChannelType.text]),
    )
    action = discord.ui.Label(
        text="Action",
        description="Set starts logging attempts to the channel above; Test posts a sample message; Clear disables logging.",
        component=discord.ui.Select(options=[
            discord.SelectOption(label="Set", value="set", description="Start logging attempts to the selected channel"),
            discord.SelectOption(label="Test", value="test", description="Post a test message to the configured channel"),
            discord.SelectOption(label="Clear", value="clear", description="Disable logging for this deny entry"),
        ]),
    )

    def __init__(self, user: discord.Member, role: discord.Role):
        super().__init__()
        self.target_user = user
        self.target_role = role
        self.title = f"Deny Log: {user.display_name} / {role.name}"[:45]

    async def on_submit(self, interaction: discord.Interaction):
        user, role = self.target_user, self.target_role
        action = self.action.component.values[0]
        entry = db.get_role_deny_entry(interaction.guild.id, user.id, role.id)

        if action == "clear":
            if not entry:
                await interaction.response.send_message("No deny entry exists for that user+role.", ephemeral=True)
                return
            db.set_role_deny_log_channel(interaction.guild.id, user.id, role.id, None)
            await interaction.response.send_message(f"✅ Cleared role deny log channel for {user.mention} + {role.mention}.", ephemeral=True)
            return

        if action == "test":
            if not entry or not entry.get("log_channel_id"):
                await interaction.response.send_message("No log channel is configured for that deny entry. Use Set first.", ephemeral=True)
                return
            target_channel = interaction.guild.get_channel(entry["log_channel_id"])
            if not target_channel:
                try:
                    target_channel = await interaction.guild.fetch_channel(entry["log_channel_id"])
                except Exception as e:
                    await interaction.response.send_message(f"Could not access configured log channel: {e}", ephemeral=True)
                    return
            try:
                await target_channel.send(
                    "🧪 Role deny log test event\n"
                    f"• Triggered by: {interaction.user.mention} (`{interaction.user.id}`)\n"
                    f"• Guild: {interaction.guild.name} (`{interaction.guild.id}`)\n"
                    f"• Deny target: {user.mention} + {role.mention}"
                )
                await interaction.response.send_message(f"✅ Test message posted in {target_channel.mention}.", ephemeral=True)
            except Exception as e:
                await error_response(interaction, e, context="deny_log_test")
            return

        # action == "set"
        channels = list(self.channel.component.values)
        if not channels:
            await interaction.response.send_message("Select a channel to set as the log channel.", ephemeral=True)
            return
        channel = channels[0]
        me = interaction.guild.me
        if me and not channel.permissions_for(me).send_messages:
            await interaction.response.send_message(f"I cannot send messages in {channel.mention}. Please grant Send Messages and try again.", ephemeral=True)
            return
        if not entry:
            await interaction.response.send_message("No deny entry exists for that user+role. Add the deny first, then set the log channel.", ephemeral=True)
            return

        db.set_role_deny_log_channel(interaction.guild.id, user.id, role.id, channel.id)
        posted_test = False
        try:
            await channel.send("✅ Role deny logging is configured for this channel. This is a test message from deny log set.")
            posted_test = True
        except Exception as e:
            logger.warning(f"Error posting deny log set test message: {e}")

        if posted_test:
            await interaction.response.send_message(f"✅ Role deny attempt logs for {user.mention} + {role.mention} will be posted in {channel.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"⚠️ Saved {channel.mention} as the log channel for {user.mention} + {role.mention}, but the test message failed to send. "
                "Check channel permissions and system logs.",
                ephemeral=True,
            )


class ChannelRestrictionModal(discord.ui.Modal, title="Configure Channel Restriction"):
    role = discord.ui.Label(
        text="Role",
        description="Which role this restriction checks for.",
        component=discord.ui.RoleSelect(min_values=1, max_values=1),
    )
    action = discord.ui.Label(
        text="Action",
        description="What to do with this channel + role combination.",
        component=discord.ui.Select(options=[
            discord.SelectOption(label="Block", value="block", description="Members WITH this role lose access"),
            discord.SelectOption(label="Require", value="require", description="Members WITHOUT this role lose access"),
            discord.SelectOption(label="Remove restriction", value="remove", description="Clear any rule on this role for this channel"),
        ]),
    )

    def __init__(self, channel: discord.abc.GuildChannel):
        super().__init__()
        self.channel = channel
        self.title = f"Restrict: #{channel.name}"[:45]

    async def on_submit(self, interaction: discord.Interaction):
        role = self.role.component.values[0]
        action = self.action.component.values[0]

        if action == "remove":
            db.remove_channel_restriction(interaction.guild.id, self.channel.id, role.id, "block")
            db.remove_channel_restriction(interaction.guild.id, self.channel.id, role.id, "require")
            await interaction.response.send_message(
                f"✅ Removed channel restriction\n• Channel: {self.channel.mention}\n• Role: {role.mention}", ephemeral=True
            )
            return

        db.add_channel_restriction(interaction.guild.id, self.channel.id, role.id, action)
        await interaction.response.send_message(
            f"✅ Added channel restriction\n• Channel: {self.channel.mention}\n• Role: {role.mention}\n• Mode: {action}\n\n"
            f"{'Members with' if action == 'block' else 'Members without'} {role.mention} will be blocked from viewing {self.channel.mention}.\n"
            f"Use `restriction_apply` to apply this to existing members.",
            ephemeral=True,
        )


class ScheduleRoleModal(discord.ui.Modal, title="Schedule Role Change"):
    roles_to_add = discord.ui.Label(
        text="Roles To Add",
        description="Added to the member at the scheduled time.",
        component=discord.ui.RoleSelect(min_values=0, max_values=25, required=False),
    )
    roles_to_remove = discord.ui.Label(
        text="Roles To Remove",
        description="Removed from the member at the scheduled time.",
        component=discord.ui.RoleSelect(min_values=0, max_values=25, required=False),
    )
    date = discord.ui.Label(
        text="Date",
        description="Format: YYYY-MM-DD",
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=True, max_length=10),
    )
    time = discord.ui.Label(
        text="Time (optional)",
        description="24hr or 12hr, e.g. 14:00 or 2:00 PM. Defaults to 12:00 AM.",
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=10),
    )
    timezone_offset = discord.ui.Label(
        text="Timezone Offset (optional)",
        description="Hours behind UTC, e.g. -5 for EST, -8 for PST. Defaults to 0 (UTC).",
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=4),
    )

    def __init__(self, target_user: discord.Member):
        super().__init__()
        self.target_user = target_user
        self.title = f"Schedule Roles: {target_user.display_name}"[:45]

    async def on_submit(self, interaction: discord.Interaction):
        add_list = list(self.roles_to_add.component.values)
        rem_list = list(self.roles_to_remove.component.values)
        user = self.target_user

        if not add_list and not rem_list:
            await send_error(interaction, "Please select at least one role to add or remove.")
            return

        tz_raw = self.timezone_offset.component.value
        try:
            tz_offset = int(tz_raw) if tz_raw else 0
        except ValueError:
            await send_error(interaction, f"Timezone offset must be a whole number of hours, got `{tz_raw}`.")
            return

        await interaction.response.defer(ephemeral=True)
        if not db.connection_pool:
            db.init_pool()

        # Same guardrails as /permissions role set and temp -- scheduling a
        # change is still granting/revoking a role, so it shouldn't be a way
        # to route around the hierarchy check or the deny list.
        for role in add_list + rem_list:
            error = check_role_hierarchy(interaction.user, interaction.guild.me, role)
            if error:
                await send_error(interaction, f"{role.mention}: {error}")
                return
        for role in add_list:
            if db.is_role_denied(interaction.guild.id, user.id, role.id):
                logger.warning(f"[ROLE DENY] Blocked /permissions role schedule by {interaction.user.id} for user {user.id} role {role.id}")
                await record_role_deny_attempt(
                    interaction.guild, user, role, source="permissions_role_schedule",
                    actor_user_id=interaction.user.id, notes="Blocked by role deny policy during role schedule",
                )
                await send_error(interaction, f"Cannot schedule adding {role.mention} to {user.mention}: role is denied for this user.")
                return

        # Default the time of day to midnight rather than create_discord_timestamp's
        # own "now" default -- scheduling a date with no time means "that whole day
        # starts", not "whatever moment happens to run this command".
        unix_ts, _, run_dt_utc = create_discord_timestamp(self.date.component.value, self.time.component.value or "00:00", tz_offset)
        if unix_ts is None:
            await send_error(interaction, run_dt_utc)  # error message, on failure
            return
        run_dt = run_dt_utc.replace(tzinfo=dt.timezone.utc)

        sched_id = db.create_scheduled_role_change(
            interaction.guild.id, user.id, [r.id for r in add_list], [r.id for r in rem_list], run_dt, interaction.user.id
        )
        lines = [
            f"✅ Scheduled role change `{sched_id}` for {user.mention}",
            f"• Add: {', '.join(r.mention for r in add_list) if add_list else 'None'}",
            f"• Remove: {', '.join(r.mention for r in rem_list) if rem_list else 'None'}",
            f"• At: <t:{int(run_dt.timestamp())}:F>",
        ]
        await interaction.followup.send("\n".join(lines), ephemeral=True)
