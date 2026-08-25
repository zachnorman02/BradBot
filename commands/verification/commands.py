"""Rules-agreement tracking commands. `setup`'s free-text multiline
message_urls param moves into a Modal (it was already effectively
modal-shaped)."""
import discord
from discord import app_commands

from database import db
from utils.logger import logger
from utils.interaction_helpers import require_guild, send_error, send_success, send_info
from commands.common import owner_or_permissions
from commands.verification.helpers import run_rules_reaction_cleanup
from commands.verification.modals import SetupRulesMessagesModal


class RulesAgreementGroup(app_commands.Group):
    """Commands for managing rules agreement tracking."""

    def __init__(self):
        super().__init__(name="verify", description="Manage rules agreement tracking")

    @app_commands.command(name="remove_on_verify", description="Toggle auto-removal of tracked rules reactions when a member gets verified (Admin only)")
    @app_commands.describe(enabled="Enable or disable automatic cleanup")
    @owner_or_permissions(administrator=True)
    async def toggle_remove_on_verify(self, interaction: discord.Interaction, enabled: bool):
        if not await require_guild(interaction):
            return
        db.set_guild_setting(interaction.guild.id, 'rules_reaction_cleanup_on_verify_enabled', 'true' if enabled else 'false')
        await send_success(interaction, f"Rules reaction cleanup on verify is now **{'enabled' if enabled else 'disabled'}**.")

    @app_commands.command(name="remove_on_leave", description="Toggle auto-removal of tracked rules reactions when a member leaves (Admin only)")
    @app_commands.describe(enabled="Enable or disable automatic cleanup")
    @owner_or_permissions(administrator=True)
    async def toggle_remove_on_leave(self, interaction: discord.Interaction, enabled: bool):
        if not await require_guild(interaction):
            return
        db.set_guild_setting(interaction.guild.id, 'rules_reaction_cleanup_on_leave_enabled', 'true' if enabled else 'false')
        await send_success(interaction, f"Rules reaction cleanup on leave is now **{'enabled' if enabled else 'disabled'}**.")

    @app_commands.command(name="setup", description="Set up rules messages to track (Admin only)")
    @owner_or_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction):
        if not await require_guild(interaction):
            return
        await interaction.response.send_modal(SetupRulesMessagesModal())

    @app_commands.command(name="set_verified_role", description="Set which role is treated as verified for rules cleanup (Admin only)")
    @app_commands.describe(role="The role that should be treated as verified")
    @owner_or_permissions(administrator=True)
    async def set_verified_role(self, interaction: discord.Interaction, role: discord.Role):
        if not await require_guild(interaction):
            return
        db.set_guild_setting(interaction.guild.id, 'verified_role_name', role.name)
        await send_success(interaction, f"Verified role set to {role.mention}.")

    @app_commands.command(name="check", description="Check which rules messages a user has reacted to")
    @app_commands.describe(user="The user to check")
    async def check(self, interaction: discord.Interaction, user: discord.User):
        if not await require_guild(interaction):
            return

        rules_messages = db.get_rules_agreement_messages(interaction.guild.id)
        if not rules_messages:
            await send_error(interaction, "Rules agreement tracking is not set up. Use `/verify setup` first.")
            return

        await interaction.response.defer()

        results = []
        for msg_data in rules_messages:
            try:
                channel = interaction.guild.get_channel(msg_data['channel_id'])
                if not channel:
                    results.append({'reacted': False, 'error': 'Channel not found', 'jump_url': msg_data.get('jump_url', '#')})
                    continue

                message = await channel.fetch_message(msg_data['message_id'])
                user_reacted = False
                user_reactions = []
                for reaction in message.reactions:
                    users = [u async for u in reaction.users()]
                    if user in users:
                        user_reacted = True
                        user_reactions.append(str(reaction.emoji))

                results.append({'reacted': user_reacted, 'reactions': user_reactions, 'jump_url': message.jump_url})
            except discord.NotFound:
                results.append({'reacted': False, 'error': 'Message not found', 'jump_url': msg_data.get('jump_url', '#')})
            except discord.Forbidden:
                results.append({'reacted': False, 'error': 'No permission', 'jump_url': msg_data.get('jump_url', '#')})

        agreed_count = sum(1 for r in results if r['reacted'])
        total_count = len(results)
        all_agreed = agreed_count == total_count

        embed = discord.Embed(
            title="📋 Rules Agreement Check",
            description=f"**User:** {user.mention}\n**Status:** {agreed_count}/{total_count} messages reacted",
            color=discord.Color.green() if all_agreed else discord.Color.orange(),
        )
        for i, result in enumerate(results, 1):
            if result['reacted']:
                status = f"✅ Agreed ({' '.join(result['reactions'])})"
            elif 'error' in result:
                status = f"⚠️ {result['error']}"
            else:
                status = "❌ Not agreed"
            embed.add_field(name=f"Message {i}", value=f"{status}\n[Jump to message]({result['jump_url']})", inline=False)

        embed.set_footer(text="✅ User has agreed to all rules!" if all_agreed else "⚠️ User has not agreed to all rules")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="status", description="Show current rules agreement configuration")
    async def status(self, interaction: discord.Interaction):
        if not await require_guild(interaction):
            return

        rules_messages = db.get_rules_agreement_messages(interaction.guild.id)
        if not rules_messages:
            await send_info(interaction, "Rules agreement tracking is not set up.\nAdministrators can use `/verify setup` to configure it.")
            return

        embed = discord.Embed(
            title="📋 Rules Agreement Configuration",
            description=f"Tracking {len(rules_messages)} message(s) for rules agreement.",
            color=discord.Color.blue(),
        )

        remove_on_verify = db.get_guild_setting(interaction.guild.id, 'rules_reaction_cleanup_on_verify_enabled', 'false').lower() == 'true'
        remove_on_leave = db.get_guild_setting(interaction.guild.id, 'rules_reaction_cleanup_on_leave_enabled', 'false').lower() == 'true'
        verified_role_name = db.get_guild_setting(interaction.guild.id, 'verified_role_name', 'verified')
        verified_role = discord.utils.get(interaction.guild.roles, name=verified_role_name)

        embed.add_field(name="🧹 Remove Reactions On Verify", value="🟢 Enabled" if remove_on_verify else "🔴 Disabled", inline=False)
        embed.add_field(name="🚪 Remove Reactions On Leave", value="🟢 Enabled" if remove_on_leave else "🔴 Disabled", inline=False)
        embed.add_field(name="✅ Verified Role", value=verified_role.mention if verified_role else f"{verified_role_name} (not found)", inline=False)

        for i, msg_data in enumerate(rules_messages, 1):
            embed.add_field(name=f"Message {i}", value=f"Channel: <#{msg_data['channel_id']}>\n[Jump to message]({msg_data.get('jump_url', '#')})", inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="cleanup", description="Remove tracked rules reactions for verified and/or departed users (Admin only)")
    @app_commands.describe(dry_run="Preview counts only without removing reactions", include_verified="Include members with the configured verified role", include_departed="Include users no longer in the server")
    @owner_or_permissions(administrator=True)
    async def cleanup(self, interaction: discord.Interaction, dry_run: bool = False, include_verified: bool = True, include_departed: bool = True):
        if not await require_guild(interaction):
            return
        await run_rules_reaction_cleanup(interaction, dry_run, include_verified, include_departed)

    @app_commands.command(name="clear", description="Clear rules agreement configuration (Admin only)")
    @owner_or_permissions(administrator=True)
    async def clear(self, interaction: discord.Interaction):
        if not await require_guild(interaction):
            return

        rules_messages = db.get_rules_agreement_messages(interaction.guild.id)
        if not rules_messages:
            await send_info(interaction, "Rules agreement tracking is not currently set up.")
            return

        db.clear_rules_agreement_messages(interaction.guild.id)
        await send_success(interaction, f"Cleared rules agreement tracking ({len(rules_messages)} message(s) removed).")
        logger.info(f"Rules agreement cleared by {interaction.user} in {interaction.guild.name}")
