"""Conditional role assignment: roles that are only granted when a member
doesn't have configured "blocking" roles, optionally deferred while they
hold a "deferral" role. Replaces admin_commands.py's single `conditionalrole`
command (13-way action dispatch) with plain, purpose-named subcommands.
"""
import discord
from discord import app_commands

from commands.common import GuildOnlyGroup
from commands.permissions.helpers import build_conditional_role_configs_embed, should_defer_assignment
from commands.permissions.modals import ConditionalRoleConfigModal
from commands.permissions.views import ConditionalRoleListView
from database import db
from utils.interaction_helpers import send_error, send_success, error_response


class PermissionsConditionalGroup(GuildOnlyGroup):
    """Conditional role assignment with blocking/deferral roles."""

    def __init__(self):
        super().__init__(name="conditional", description="Conditional role assignment with blocking/deferral roles")

    @app_commands.command(name="configure", description="Configure a conditional role's blocking/deferral roles")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(role="The role to configure")
    async def configure(self, interaction: discord.Interaction, role: discord.Role):
        if not db.connection_pool:
            db.init_pool()
        await interaction.response.send_modal(ConditionalRoleConfigModal(role=role))

    @app_commands.command(name="remove_config", description="Remove a conditional role's configuration")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(role="The configured role")
    async def remove_config(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        if not db.get_conditional_role_config(interaction.guild.id, role.id):
            await send_error(interaction, f"{role.mention} is not configured as a conditional role.")
            return
        db.remove_conditional_role_config(interaction.guild.id, role.id)
        await send_success(interaction, f"Removed conditional role configuration for {role.mention}")

    @app_commands.command(name="list", description="List all configured conditional roles")
    @app_commands.default_permissions(administrator=True)
    async def list_configs(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        embed = build_conditional_role_configs_embed(interaction.guild)
        await interaction.followup.send(embed=embed, view=ConditionalRoleListView(interaction.guild))

    @app_commands.command(name="list_eligible", description="Show users currently marked eligible for a conditional role")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(role="The configured role")
    async def list_eligible(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        config = db.get_conditional_role_config(interaction.guild.id, role.id)
        if not config:
            await send_error(interaction, f"{role.mention} is not configured as a conditional role.\nUse `/permissions conditional configure` first.")
            return

        eligible_users = db.get_conditional_role_eligible_users(interaction.guild.id, role.id)
        if not eligible_users:
            await interaction.followup.send(f"📋 No users currently marked as eligible for {role.mention}.", ephemeral=True)
            return

        embed = discord.Embed(title=f"🔓 Eligible Users for {role.name}", description=f"Found {len(eligible_users)} eligible user(s)", color=discord.Color.green())
        for user_data in eligible_users[:25]:
            member = interaction.guild.get_member(user_data['user_id'])
            member_name = member.display_name if member else "Unknown User"
            marked_by = ""
            if user_data['marked_by_user_id']:
                marker = interaction.guild.get_member(user_data['marked_by_user_id'])
                marked_by = f"\nMarked by: {marker.mention if marker else 'Unknown'}"
            notes = f"\nNotes: {user_data['notes']}" if user_data['notes'] else ""
            embed.add_field(
                name=f"✅ {member_name}",
                value=f"<@{user_data['user_id']}> • {user_data['marked_at'].strftime('%Y-%m-%d')}{marked_by}{notes}",
                inline=False,
            )
        if len(eligible_users) > 25:
            embed.set_footer(text=f"Showing 25 of {len(eligible_users)} eligible users")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="set_eligibility", description="Mark or unmark a user as eligible for a conditional role")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="Target user", role="Configured role", eligible="True to mark eligible, False to remove eligibility")
    async def set_eligibility(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role, eligible: bool):
        await interaction.response.defer(ephemeral=True)
        if not db.get_conditional_role_config(interaction.guild.id, role.id):
            await send_error(interaction, f"{role.mention} is not configured as a conditional role.\nUse `/permissions conditional configure` first.")
            return

        if eligible:
            db.mark_conditional_role_eligible(interaction.guild.id, user.id, role.id, interaction.user.id)
            await send_success(interaction, f"Marked {user.mention} as eligible for {role.mention}.")
        else:
            db.unmark_conditional_role_eligible(interaction.guild.id, user.id, role.id)
            await send_success(interaction, f"Removed eligibility for {user.mention} to receive {role.mention}.")

    @app_commands.command(name="check", description="Check a user's eligibility and override status for a conditional role")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="Target user", role="Configured role")
    async def check(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        is_eligible = db.is_conditional_role_eligible(interaction.guild.id, user.id, role.id)
        has_override = db.has_conditional_role_override(interaction.guild.id, user.id, role.id)

        status = f"✅ {user.mention} is eligible for {role.mention}." if is_eligible else f"❌ {user.mention} is NOT eligible for {role.mention}."
        if has_override:
            status += "\n🛡️ Override is enabled (blocking/deferral checks are bypassed)."
        await interaction.followup.send(status, ephemeral=True)

    @app_commands.command(name="set_override", description="Enable or disable the blocking/deferral bypass for a user")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="Target user", role="Configured role", enabled="True to enable the override, False to disable it")
    async def set_override(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role, enabled: bool):
        await interaction.response.defer(ephemeral=True)
        db.set_conditional_role_override(interaction.guild.id, user.id, role.id, enabled)

        if not enabled:
            await send_success(interaction, f"Override disabled for {user.mention} on {role.mention}. Future checks will enforce blocking/deferral rules again.")
            return

        assigned_now = False
        if role not in user.roles:
            try:
                await user.add_roles(role, reason=f"Conditional role override enabled by {interaction.user.display_name}")
                assigned_now = True
            except discord.Forbidden:
                await send_error(interaction, f"Override enabled for {user.mention} on {role.mention}, but I couldn't assign the role due to permissions.")
                return
            except Exception as e:
                await error_response(interaction, e, context="set_override")
                return

        db.unmark_conditional_role_eligible(interaction.guild.id, user.id, role.id)
        result = f"🛡️ Override enabled for {user.mention} on {role.mention}."
        result += "\n✅ Role assigned immediately." if assigned_now else "\nℹ️ User already has the role."
        await interaction.followup.send(result, ephemeral=True)

    @app_commands.command(name="list_overrides", description="List active blocking/deferral overrides")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(role="Limit to a specific configured role (optional)")
    async def list_overrides(self, interaction: discord.Interaction, role: discord.Role = None):
        await interaction.response.defer(ephemeral=True)
        overrides = db.get_conditional_role_overrides(interaction.guild.id, role.id if role else None)
        if not overrides:
            await interaction.followup.send(
                f"📋 No active overrides found for {role.mention}." if role else "📋 No active conditional-role overrides found.", ephemeral=True
            )
            return

        title = f"🛡️ Active Overrides for {role.name}" if role else "🛡️ Active Conditional-Role Overrides"
        embed = discord.Embed(title=title, description=f"Found {len(overrides)} override(s)", color=discord.Color.blue())
        for entry in overrides[:25]:
            member = interaction.guild.get_member(entry['user_id'])
            role_obj = interaction.guild.get_role(entry['role_id'])
            user_text = member.mention if member else f"<@{entry['user_id']}>"
            role_text = role_obj.mention if role_obj else f"<@&{entry['role_id']}>"
            when_text = entry['updated_at'].strftime('%Y-%m-%d %H:%M UTC') if entry.get('updated_at') else "Unknown"
            embed.add_field(name=f"User: {user_text}", value=f"Role: {role_text}\nUpdated: {when_text}", inline=False)
        if len(overrides) > 25:
            embed.set_footer(text=f"Showing 25 of {len(overrides)} overrides")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="assign", description="Assign a conditional role to a user if they're eligible (or overridden)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="Target user", role="Configured role")
    async def assign(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        config = db.get_conditional_role_config(interaction.guild.id, role.id)
        if not config:
            await send_error(interaction, f"{role.mention} is not configured as a conditional role.\nUse `/permissions conditional configure` first.")
            return

        has_override = db.has_conditional_role_override(interaction.guild.id, user.id, role.id)
        if has_override:
            try:
                await user.add_roles(role, reason=f"Conditional role override assignment by {interaction.user.display_name}")
                db.unmark_conditional_role_eligible(interaction.guild.id, user.id, role.id)
                await send_success(interaction, f"🛡️ Override active: assigned {role.mention} to {user.mention} (blocking/deferral ignored).")
            except discord.Forbidden:
                await send_error(interaction, f"I don't have permission to assign roles.\nMake sure my role is higher than {role.mention}.")
            except Exception as e:
                await error_response(interaction, e, context="conditional_assign")
            return

        if not db.is_conditional_role_eligible(interaction.guild.id, user.id, role.id):
            await send_error(interaction, f"{user.mention} has not been marked as eligible for {role.mention}.\nUse `/permissions conditional set_eligibility` first.")
            return

        blocking_role_ids = config['blocking_role_ids']
        user_role_ids = {r.id for r in user.roles}
        blocking_roles_found = [interaction.guild.get_role(rid) for rid in blocking_role_ids if rid in user_role_ids]
        if blocking_roles_found:
            mentions = ', '.join(r.mention for r in blocking_roles_found if r)
            await send_error(interaction, f"Cannot assign {role.mention} to {user.mention}.\nThey have one or more blocking roles: {mentions}\n\nRemove these roles first.")
            return

        if role in user.roles:
            await interaction.followup.send(f"ℹ️ {user.mention} already has {role.mention}.", ephemeral=True)
            return

        if should_defer_assignment(user, config):
            deferral_role_names = [
                interaction.guild.get_role(did).name for did in config.get('deferral_role_ids', []) if interaction.guild.get_role(did)
            ]
            db.mark_conditional_role_eligible(
                interaction.guild.id, user.id, role.id, interaction.user.id,
                notes=f"Deferred: has deferral role(s): {', '.join(deferral_role_names)}",
            )
            await interaction.followup.send(
                f"⏳ {user.mention} has been marked as eligible for {role.mention}.\n"
                f"**Assignment deferred:** They currently have one or more deferral roles: {', '.join(deferral_role_names)}\n"
                f"The role will be assignable once these roles are removed.",
                ephemeral=True,
            )
            return

        try:
            await user.add_roles(role, reason=f"Conditional role assigned by {interaction.user.display_name}")
            db.mark_conditional_role_eligible(interaction.guild.id, user.id, role.id, interaction.user.id, notes="Assigned directly by admin")
            await send_success(interaction, f"Successfully assigned {role.mention} to {user.mention}!")
        except discord.Forbidden:
            await send_error(interaction, f"I don't have permission to assign roles.\nMake sure my role is higher than {role.mention}.")
        except Exception as e:
            await error_response(interaction, e, context="conditional_assign")

    @app_commands.command(name="bulk_check", description="Scan all members against all conditional role configs and apply/report changes")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(dry_run="If True, only report what would change without making changes")
    async def bulk_check(self, interaction: discord.Interaction, dry_run: bool = True):
        await interaction.response.defer(ephemeral=True)
        configs = db.get_all_conditional_role_configs(interaction.guild.id)
        if not configs:
            await send_error(interaction, "No conditional roles configured for this server.")
            return

        results = {'removed': [], 'granted': [], 'errors': []}

        async for member in interaction.guild.fetch_members(limit=None):
            if member.bot:
                continue
            try:
                for config in configs:
                    conditional_role_id = config['role_id']
                    blocking_role_ids = config.get('blocking_role_ids', [])
                    deferral_role_ids = config.get('deferral_role_ids', [])

                    member_role_ids = {r.id for r in member.roles}
                    has_conditional_role = conditional_role_id in member_role_ids
                    has_blocking_role = any(rid in member_role_ids for rid in blocking_role_ids)
                    has_deferral_role = any(rid in member_role_ids for rid in deferral_role_ids)
                    has_override = db.has_conditional_role_override(interaction.guild.id, member.id, conditional_role_id)
                    eligibility = db.get_conditional_role_eligibility(interaction.guild.id, member.id, conditional_role_id)
                    is_deferred = bool(eligibility)

                    conditional_role = interaction.guild.get_role(conditional_role_id)
                    role_name = conditional_role.name if conditional_role else f"Role {conditional_role_id}"

                    if has_override:
                        if not has_conditional_role:
                            results['granted'].append(f"Grant {role_name} to {member.mention} (override enabled)")
                            if not dry_run and conditional_role:
                                try:
                                    await member.add_roles(conditional_role, reason="Conditional role override enabled")
                                    db.unmark_conditional_role_eligible(interaction.guild.id, member.id, conditional_role_id)
                                except Exception as e:
                                    results['errors'].append(f"Failed to grant {role_name} to {member.mention}: {e}")
                        continue

                    if has_conditional_role and has_blocking_role:
                        blocking_mentions = [interaction.guild.get_role(rid).mention for rid in blocking_role_ids if rid in member_role_ids and interaction.guild.get_role(rid)]
                        results['removed'].append(f"Remove {role_name} from {member.mention} (has blocking roles: {', '.join(blocking_mentions) if blocking_mentions else 'blocking role'})")
                        if not dry_run and conditional_role:
                            try:
                                await member.remove_roles(conditional_role, reason="Conditional role check: user has blocking roles")
                                db.unmark_conditional_role_eligible(interaction.guild.id, member.id, conditional_role_id)
                            except Exception as e:
                                results['errors'].append(f"Failed to remove {role_name} from {member.mention}: {e}")
                        continue

                    if has_conditional_role and has_deferral_role and deferral_role_ids:
                        results['removed'].append(f"Remove {role_name} from {member.mention} (has deferral roles)")
                        if not dry_run and conditional_role:
                            try:
                                await member.remove_roles(conditional_role, reason="Conditional role check: user has deferral roles")
                            except Exception as e:
                                results['errors'].append(f"Failed to remove {role_name} from {member.mention}: {e}")
                    elif is_deferred and not has_deferral_role and not has_conditional_role and not has_blocking_role and deferral_role_ids:
                        results['granted'].append(f"Grant {role_name} to {member.mention} (eligible, deferral criteria met)")
                        if not dry_run and conditional_role:
                            try:
                                await member.add_roles(conditional_role, reason="Conditional role check: criteria met")
                                db.unmark_conditional_role_eligible(interaction.guild.id, member.id, conditional_role_id)
                            except Exception as e:
                                results['errors'].append(f"Failed to grant {role_name} to {member.mention}: {e}")
            except Exception as e:
                results['errors'].append(f"Error checking member {member.mention}: {e}")

        mode_text = "📋 DRY RUN" if dry_run else "✅ EXECUTED"
        embed = discord.Embed(title=f"{mode_text} - Conditional Role Check", color=discord.Color.blue() if dry_run else discord.Color.green())

        for key, label, emoji in (('removed', 'To Remove', '🗑️'), ('granted', 'To Grant', '✨')):
            items = results[key]
            if items:
                embed.add_field(name=f"{emoji} {label} ({len(items)})", value="\n".join(items[:10]), inline=False)
                if len(items) > 10:
                    embed.add_field(name="...", value=f"and {len(items) - 10} more", inline=False)

        if results['errors']:
            embed.add_field(name=f"⚠️ Errors ({len(results['errors'])})", value="\n".join(results['errors'][:5]), inline=False)
            if len(results['errors']) > 5:
                embed.add_field(name="...", value=f"and {len(results['errors']) - 5} more", inline=False)

        if not results['removed'] and not results['granted'] and not results['errors']:
            embed.description = "✅ All conditional roles are correctly assigned!"
        elif dry_run:
            embed.set_footer(text="Use dry_run: false to apply these changes")

        await interaction.followup.send(embed=embed, ephemeral=True)
