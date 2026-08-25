"""Per-user role-deny entries: block a specific user from ever receiving a
specific role, with optional channel logging of attempts. Replaces
mod_tools_commands.py's `roledeny_user` (7-way action dispatch) with plain
subcommands."""
import discord
from discord import app_commands

from commands.common import GuildOnlyGroup, owner_or_permissions
from database import db
from utils.logger import logger
from utils.interaction_helpers import send_error, send_success, error_response


class PermissionsDenyGroup(GuildOnlyGroup):
    """Per-user role-deny entries and their attempt logging."""

    def __init__(self):
        super().__init__(name="deny", description="Per-user role-deny entries")

    @app_commands.command(name="add", description="Deny a user from ever receiving a role")
    @app_commands.describe(user="User to target", role="Role to deny", notes="Optional reason")
    @owner_or_permissions(manage_roles=True)
    async def add(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role, notes: str = None):
        await interaction.response.defer(ephemeral=True)
        if not db.connection_pool:
            db.init_pool()
        if db.is_role_denied(interaction.guild.id, user.id, role.id):
            await interaction.followup.send(f"ℹ️ {user.mention} is already denied from receiving {role.mention}.", ephemeral=True)
            return

        db.add_role_deny(interaction.guild.id, user.id, role.id, interaction.user.id, notes)
        response = f"✅ Added deny: {user.mention} cannot receive {role.mention}."
        if notes:
            response += f"\n📝 Notes: {notes}"
        await interaction.followup.send(response, ephemeral=True)

    @app_commands.command(name="remove", description="Remove a role-deny entry for a user")
    @app_commands.describe(user="User to target", role="Denied role")
    @owner_or_permissions(manage_roles=True)
    async def remove(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        if not db.connection_pool:
            db.init_pool()
        if not db.is_role_denied(interaction.guild.id, user.id, role.id):
            await interaction.followup.send(f"ℹ️ No deny entry exists for {user.mention} and {role.mention}.", ephemeral=True)
            return
        db.remove_role_deny(interaction.guild.id, user.id, role.id)
        await send_success(interaction, f"Removed deny: {user.mention} can receive {role.mention} again.")

    @app_commands.command(name="check", description="Check if a user is denied from a role")
    @app_commands.describe(user="User to target", role="Role to check")
    @owner_or_permissions(manage_roles=True)
    async def check(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        if not db.connection_pool:
            db.init_pool()
        denied = db.is_role_denied(interaction.guild.id, user.id, role.id)
        await interaction.followup.send(
            f"🚫 {user.mention} is denied from {role.mention}." if denied else f"✅ {user.mention} is not denied from {role.mention}.",
            ephemeral=True,
        )

    @app_commands.command(name="list", description="List role-deny entries, optionally filtered")
    @app_commands.describe(user="Filter by user (optional)", role="Filter by role (optional)")
    @owner_or_permissions(manage_roles=True)
    async def list_denies(self, interaction: discord.Interaction, user: discord.Member = None, role: discord.Role = None):
        await interaction.response.defer(ephemeral=True)
        if not db.connection_pool:
            db.init_pool()
        entries = db.get_role_denies(interaction.guild.id, user_id=user.id if user else None, role_id=role.id if role else None)
        if not entries:
            await interaction.followup.send("📋 No role deny entries found for this filter.", ephemeral=True)
            return

        embed = discord.Embed(title="🚫 Role Deny Entries", description=f"Found {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}", color=discord.Color.orange())
        for entry in entries[:20]:
            member = interaction.guild.get_member(entry['user_id'])
            role_obj = interaction.guild.get_role(entry['role_id'])
            actor = interaction.guild.get_member(entry['created_by_user_id']) if entry['created_by_user_id'] else None

            user_text = member.mention if member else f"<@{entry['user_id']}>"
            role_text = role_obj.mention if role_obj else f"<@&{entry['role_id']}>"
            actor_text = actor.mention if actor else (f"<@{entry['created_by_user_id']}>" if entry['created_by_user_id'] else "Unknown")
            updated_at = entry['updated_at'].strftime('%Y-%m-%d %H:%M UTC') if entry.get('updated_at') else "Unknown"
            notes_text = entry['notes'][:120] if entry.get('notes') else "None"
            channel_text = f"<#{entry['log_channel_id']}>" if entry.get('log_channel_id') else "Not set"

            embed.add_field(
                name=f"{user_text} -> {role_text}",
                value=f"By: {actor_text}\nUpdated: {updated_at}\nLog Channel: {channel_text}\nNotes: {notes_text}",
                inline=False,
            )
        if len(entries) > 20:
            embed.set_footer(text=f"Showing first 20 of {len(entries)} entries")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="log_set", description="Send role-deny attempt logs for a user+role to a channel")
    @app_commands.describe(user="User", role="Denied role", channel="Channel to log attempts to")
    @owner_or_permissions(manage_roles=True)
    async def log_set(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        if not db.connection_pool:
            db.init_pool()

        me = interaction.guild.me
        if me and not channel.permissions_for(me).send_messages:
            await send_error(interaction, f"I cannot send messages in {channel.mention}. Please grant Send Messages and try again.")
            return

        if not db.get_role_deny_entry(interaction.guild.id, user.id, role.id):
            await send_error(interaction, "No deny entry exists for that user+role. Add the deny first, then set the log channel.")
            return

        db.set_role_deny_log_channel(interaction.guild.id, user.id, role.id, channel.id)

        posted_test = False
        try:
            await channel.send("✅ Role deny logging is configured for this channel. This is a test message from log_set.")
            posted_test = True
        except Exception as e:
            logger.warning(f"Error posting log_set test message: {e}")

        if posted_test:
            await send_success(interaction, f"Role deny attempt logs for {user.mention} + {role.mention} will be posted in {channel.mention}.")
        else:
            await interaction.followup.send(
                f"⚠️ Saved {channel.mention} as the log channel for {user.mention} + {role.mention}, but the test message failed to send. "
                "Check channel permissions and system logs.",
                ephemeral=True,
            )

    @app_commands.command(name="log_test", description="Send a test message to a role-deny entry's configured log channel")
    @app_commands.describe(user="User", role="Denied role")
    @owner_or_permissions(manage_roles=True)
    async def log_test(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        entry = db.get_role_deny_entry(interaction.guild.id, user.id, role.id)
        if not entry:
            await send_error(interaction, "No deny entry exists for that user+role.")
            return

        target_channel_id = entry.get("log_channel_id")
        if not target_channel_id:
            await send_error(interaction, "No log channel is configured for that deny entry. Use log_set first.")
            return

        target_channel = interaction.guild.get_channel(target_channel_id)
        if not target_channel:
            try:
                target_channel = await interaction.guild.fetch_channel(target_channel_id)
            except Exception as e:
                await send_error(interaction, f"Could not access configured log channel ({target_channel_id}): {e}")
                return

        try:
            await target_channel.send(
                "🧪 Role deny log test event\n"
                f"• Triggered by: {interaction.user.mention} (`{interaction.user.id}`)\n"
                f"• Guild: {interaction.guild.name} (`{interaction.guild.id}`)\n"
                f"• Deny target: {user.mention} + {role.mention}"
            )
            await send_success(interaction, f"Test message posted in {target_channel.mention}.")
        except Exception as e:
            await error_response(interaction, e, context="deny_log_test")

    @app_commands.command(name="log_clear", description="Disable role-deny attempt logging for a user+role")
    @app_commands.describe(user="User", role="Denied role")
    @owner_or_permissions(manage_roles=True)
    async def log_clear(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        entry = db.get_role_deny_entry(interaction.guild.id, user.id, role.id)
        if not entry:
            await send_error(interaction, "No deny entry exists for that user+role.")
            return
        db.set_role_deny_log_channel(interaction.guild.id, user.id, role.id, None)
        await send_success(interaction, f"Cleared role deny log channel for {user.mention} + {role.mention}.")
