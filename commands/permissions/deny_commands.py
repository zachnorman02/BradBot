"""Per-user role-deny entries: block a specific user from ever receiving a
specific role, with optional channel logging of attempts. Replaces
mod_tools_commands.py's `roledeny_user` (7-way action dispatch) with plain
subcommands."""
import discord
from discord import app_commands

from commands.common import GuildOnlyGroup, owner_or_permissions
from commands.permissions.modals import DenyModal, DenyLogModal
from database import db


class PermissionsDenyGroup(GuildOnlyGroup):
    """Per-user role-deny entries and their attempt logging."""

    def __init__(self):
        super().__init__(name="deny", description="Per-user role-deny entries")

    @app_commands.command(name="set", description="Deny or allow a user from receiving a role")
    @app_commands.describe(user="User to target")
    @owner_or_permissions(manage_roles=True)
    async def set_deny(self, interaction: discord.Interaction, user: discord.Member):
        if not db.connection_pool:
            db.init_pool()
        await interaction.response.send_modal(DenyModal(user=user))

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

    @app_commands.command(name="log", description="Set, test, or clear role-deny attempt logging for a user+role")
    @app_commands.describe(user="User", role="Denied role")
    @owner_or_permissions(manage_roles=True)
    async def log(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        if not db.connection_pool:
            db.init_pool()
        await interaction.response.send_modal(DenyLogModal(user=user, role=role))
