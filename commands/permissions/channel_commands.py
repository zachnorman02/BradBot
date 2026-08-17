"""Channel access-control: per-user/role deny overwrites, role-based channel
restriction rules, and the channel-visibility diagnostic. Replaces
mod_tools_commands.py's channeldeny_user/channelallow_user (merged into one
`access` command with an allow/deny flag) and admin_commands.py's
channelrestriction (its 4-way action dispatch split into plain subcommands).
"""
import discord
from discord import app_commands

from commands.common import GuildOnlyGroup
from commands.permissions.helpers import build_channel_restrictions_embed, compute_channel_visibility
from commands.permissions.views import ChannelRestrictionListView
from database import db
from utils.logger import logger
from utils.interaction_helpers import send_error, send_success, error_response
from utils.pagination import build_paginated_embed

DENY_OVERWRITE_FIELDS = (
    "view_channel", "send_messages", "send_messages_in_threads", "add_reactions",
    "speak", "connect", "stream", "use_application_commands",
    "create_public_threads", "create_private_threads",
)


class PermissionsChannelGroup(GuildOnlyGroup):
    """Per-user overwrites and role-based restriction rules for channels."""

    def __init__(self):
        super().__init__(name="channel", description="Channel access control")

    @app_commands.command(name="access", description="Allow or deny a user's access to a specific channel")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="Channel to modify",
        user="User to allow/deny",
        allow="True to clear deny overwrites (allow), False to deny access",
    )
    async def access(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, user: discord.Member, allow: bool):
        """Merges the old channeldeny_user/channelallow_user into one command."""
        await interaction.response.defer(ephemeral=True)
        try:
            me = interaction.guild.me
            if not me or not channel.permissions_for(me).manage_channels:
                await send_error(interaction, "I need `Manage Channels` permission in that channel to edit overwrites.")
                return

            overwrite = channel.overwrites_for(user)
            for field in DENY_OVERWRITE_FIELDS:
                setattr(overwrite, field, None if allow else False)

            if allow and overwrite.is_empty():
                await channel.set_permissions(user, overwrite=None, reason=f"Channel access allowed by {interaction.user}")
            else:
                await channel.set_permissions(user, overwrite=overwrite, reason=f"Channel access {'allowed' if allow else 'denied'} by {interaction.user}")

            if allow:
                await send_success(interaction, f"Cleared deny overwrite fields for {user.mention} in {channel.mention}.")
            else:
                await send_success(interaction, f"Denied {user.mention} from {channel.mention} (view, send, react, voice, app commands, threads).")
        except Exception as e:
            await error_response(interaction, e, context="channel_access")

    @app_commands.command(name="restriction_set", description="Restrict a channel based on whether a member has a role")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="Channel to restrict (text/voice/forum/stage/category)",
        blocking_role="Role to check",
        mode="Block members WITH the role, or require it (block members WITHOUT it)",
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Block (users WITH the role are blocked)", value="block"),
        app_commands.Choice(name="Require (users WITHOUT the role are blocked)", value="require"),
    ])
    async def restriction_set(
        self, interaction: discord.Interaction, channel: discord.abc.GuildChannel,
        blocking_role: discord.Role, mode: app_commands.Choice[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if not db.connection_pool:
            db.init_pool()

        mode_value = mode.value if mode else "block"
        db.add_channel_restriction(interaction.guild.id, channel.id, blocking_role.id, mode_value)
        await send_success(
            interaction,
            f"Added channel restriction\n• Channel: {channel.mention}\n• Role: {blocking_role.mention}\n• Mode: {mode_value}\n\n"
            f"{'Members with' if mode_value == 'block' else 'Members without'} {blocking_role.mention} will be blocked from viewing {channel.mention}.\n"
            f"Use `restriction_apply` to apply this to existing members.",
        )

    @app_commands.command(name="restriction_remove", description="Remove a role-based channel restriction")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Restricted channel", blocking_role="Role the restriction is on", mode="Leave blank to remove both block and require modes")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Block", value="block"),
        app_commands.Choice(name="Require", value="require"),
    ])
    async def restriction_remove(
        self, interaction: discord.Interaction, channel: discord.abc.GuildChannel,
        blocking_role: discord.Role, mode: app_commands.Choice[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if not db.connection_pool:
            db.init_pool()

        if mode:
            db.remove_channel_restriction(interaction.guild.id, channel.id, blocking_role.id, mode.value)
            mode_text = mode.value
        else:
            db.remove_channel_restriction(interaction.guild.id, channel.id, blocking_role.id, "block")
            db.remove_channel_restriction(interaction.guild.id, channel.id, blocking_role.id, "require")
            mode_text = "block & require"

        await send_success(interaction, f"Removed channel restriction\n• Channel: {channel.mention}\n• Role: {blocking_role.mention}\n• Mode: {mode_text}")

    @app_commands.command(name="restriction_list", description="List all role-based channel restrictions")
    @app_commands.default_permissions(administrator=True)
    async def restriction_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        embed = build_channel_restrictions_embed(interaction.guild)
        await interaction.followup.send(embed=embed, view=ChannelRestrictionListView(interaction.guild))

    @app_commands.command(name="restriction_apply", description="Apply configured channel restrictions to current members")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Limit to this channel only (optional)")
    async def restriction_apply(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel = None):
        import asyncio
        from collections import defaultdict

        if channel:
            await interaction.response.send_message(f"🔄 Applying channel restrictions to {channel.mention}...", ephemeral=True)
        else:
            await interaction.response.send_message("🔄 Applying channel restrictions to all members...", ephemeral=True)

        try:
            restrictions = db.get_channel_restrictions(interaction.guild.id)
            if channel:
                restrictions = [r for r in restrictions if r['channel_id'] == channel.id]
            if not restrictions:
                await interaction.followup.send("❌ No restrictions configured for that filter.", ephemeral=True)
                return

            results = {'blocked': 0, 'unblocked': 0, 'errors': []}
            changes_applied = 0

            by_channel = defaultdict(list)
            for r in restrictions:
                by_channel[r['channel_id']].append({'role_id': r['blocking_role_id'], 'mode': r.get('mode', 'block')})

            for channel_id, channel_restrictions in by_channel.items():
                channel_obj = interaction.guild.get_channel(channel_id)
                if not channel_obj:
                    results['errors'].append(f"Channel {channel_id} not found")
                    continue

                for member in interaction.guild.members:
                    if member.bot:
                        continue
                    member_role_ids = {r.id for r in member.roles}
                    should_block = False
                    for entry in channel_restrictions:
                        has_role = entry['role_id'] in member_role_ids
                        if entry.get('mode', 'block') == 'block' and has_role:
                            should_block = True
                            break
                        if entry.get('mode') == 'require' and not has_role:
                            should_block = True
                            break

                    try:
                        overwrite = channel_obj.overwrites_for(member)
                        if should_block and overwrite.view_channel is not False:
                            await channel_obj.set_permissions(member, view_channel=False, reason="Channel restriction enforcement")
                            results['blocked'] += 1
                            changes_applied += 1
                        elif not should_block and overwrite.view_channel is False:
                            await channel_obj.set_permissions(member, overwrite=None, reason="Removing channel restriction")
                            results['unblocked'] += 1
                            changes_applied += 1

                        if changes_applied and changes_applied % 10 == 0:
                            await asyncio.sleep(0.25)
                    except Exception as e:
                        results['errors'].append(f"{member.display_name}: {str(e)[:50]}")

            embed = discord.Embed(title="✅ Channel Restrictions Applied", color=discord.Color.green())
            embed.add_field(name="📊 Results", value=f"Blocked: {results['blocked']}\nUnblocked: {results['unblocked']}", inline=False)
            if results['errors']:
                error_text = "\n".join(results['errors'][:5])
                if len(results['errors']) > 5:
                    error_text += f"\n... and {len(results['errors']) - 5} more"
                embed.add_field(name="⚠️ Errors", value=error_text, inline=False)

            await interaction.followup.send(embed=embed, view=ChannelRestrictionListView(interaction.guild))
        except Exception as e:
            logger.error(f"Error in restriction_apply: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="visibility", description="Check which channels a user or role can/can't see")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="Check a specific member (exact)", role="Check a role (best-effort, no specific member)")
    async def visibility(self, interaction: discord.Interaction, user: discord.Member = None, role: discord.Role = None):
        if not user and not role:
            await send_error(interaction, "Specify either a user or a role.")
            return
        if user and role:
            await send_error(interaction, "Specify only one of user or role, not both.")
            return

        await interaction.response.defer(ephemeral=True)
        can_see, cannot_see = compute_channel_visibility(interaction.guild, member=user, role=role)
        target = user.mention if user else role.mention
        note = "" if user else "\n-# Best-effort: computed from @everyone + this role's overwrites, since visibility for a role alone depends on each member's other roles too."

        embed = build_paginated_embed(f"👁️ Channel Visibility: can see", can_see, color=discord.Color.green(), description=f"For {target}{note}")
        embed2 = build_paginated_embed("🚫 Cannot see", cannot_see, color=discord.Color.red())
        await interaction.followup.send(embeds=[embed, embed2], ephemeral=True)
