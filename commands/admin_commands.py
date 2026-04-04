"""Admin command group for server and database management"""
import discord
from discord import app_commands
from discord.ext import commands
from discord import ui
import datetime as dt
import asyncio
import re
from typing import Optional

from commands.booster_commands import restore_member_booster_role
from commands.views import (
    AdminSettingsView,
    CommandToggleView,
    ChannelRestrictionListView,
    ConditionalRoleListView
)
from database import db
from utils.logger import logger


async def _enforce_default_permissions(interaction: discord.Interaction) -> bool:
    command = interaction.command
    if not command:
        return True
    required = getattr(command, "default_permissions", None)
    if required is None:
        return True
    if not interaction.guild:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ This command can only be used in a server!",
                ephemeral=True
            )
        return False
    if interaction.user.guild_permissions.is_superset(required):
        return True
    if not interaction.response.is_done():
        await interaction.response.send_message(
            "❌ You don't have permission to use this command.",
            ephemeral=True
        )
    return False


# View classes moved to commands/views/admin_views.py


class AdminToolsGroup(app_commands.Group):
    """Database and role management tools"""
    
    def __init__(self):
        super().__init__(name="tools", description="Database and role management tools")

    # Helpers for listing panels
    def _build_channel_restrictions_embed(self, guild: discord.Guild) -> discord.Embed:
        restrictions = db.get_channel_restrictions(guild.id)
        embed = discord.Embed(
            title="🔒 Channel Restrictions",
            description=f"Found {len(restrictions)} restriction(s)" if restrictions else "No restrictions configured",
            color=discord.Color.blue()
        )
        if not restrictions:
            return embed

        from collections import defaultdict
        by_channel = defaultdict(list)
        for r in restrictions:
            by_channel[r['channel_id']].append(r)

        for channel_id, channel_restrictions in by_channel.items():
            channel_obj = guild.get_channel(channel_id)
            channel_name = channel_obj.mention if channel_obj else f"Unknown Channel ({channel_id})"

            require_mentions = []
            block_mentions = []
            for r in channel_restrictions:
                role = guild.get_role(r['blocking_role_id'])
                label = "Require" if r.get('mode') == 'require' else "Block"
                mention = role.mention if role else f"Unknown ({r['blocking_role_id']})"
                if label == "Require":
                    require_mentions.append(mention)
                else:
                    block_mentions.append(mention)

            rules_lines = []
            rules_lines.append(f"**Channel:** {channel_name}")
            rules_lines.append(f"**Require:** {', '.join(require_mentions) if require_mentions else 'None'}")
            rules_lines.append(f"**Block:** {', '.join(block_mentions) if block_mentions else 'None'}")

            embed.add_field(
                name=f"🔒 {channel_obj.name if channel_obj else 'Unknown'}",
                value="\n".join(rules_lines),
                inline=False
            )
        return embed

    def _build_conditional_role_configs_embed(self, guild: discord.Guild) -> discord.Embed:
        configs = db.get_all_conditional_role_configs(guild.id)
        embed = discord.Embed(
            title="⚙️ Conditional Role Configurations",
            description=f"Found {len(configs)} configured role(s)" if configs else "No conditional roles configured",
            color=discord.Color.blue()
        )
        for config in configs:
            role_obj = guild.get_role(config['role_id'])
            role_mention = role_obj.mention if role_obj else f"<@&{config['role_id']}> (deleted)"

            blocking_mentions = []
            for blocking_id in config['blocking_role_ids']:
                blocking_role = guild.get_role(blocking_id)
                blocking_mentions.append(blocking_role.mention if blocking_role else f"<@&{blocking_id}> (deleted)")

            blocking_text = ", ".join(blocking_mentions) if blocking_mentions else "None"

            deferral_mentions = []
            for deferral_id in config.get('deferral_role_ids', []):
                deferral_role = guild.get_role(deferral_id)
                deferral_mentions.append(deferral_role.mention if deferral_role else f"<@&{deferral_id}> (deleted)")

            deferral_text = ", ".join(deferral_mentions) if deferral_mentions else "None"

            # How many users are currently marked eligible/deferred for this role
            eligible_count = 0
            try:
                eligible_count = len(db.get_conditional_role_eligible_users(guild.id, config['role_id']))
            except Exception:
                eligible_count = 0

            embed.add_field(
                name=f"🔒 {config.get('role_name', 'Unknown')}",
                value=(
                    f"**Role:** {role_mention}\n"
                    f"**Blocking Roles:** {blocking_text}\n"
                    f"**Deferral Roles:** {deferral_text}\n"
                    f"**Queued/Eligible:** {eligible_count}"
                ),
                inline=False
            )
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _enforce_default_permissions(interaction)
    
    def _should_defer_assignment(self, member: discord.Member, config: dict) -> bool:
        """Check if role assignment should be deferred based on config.
        
        Deferred if user has ANY of the deferral_role_ids from config.
        
        Args:
            member: Discord member to check
            config: Conditional role config dict with 'deferral_role_ids'
        
        Returns:
            True if assignment should be deferred, False otherwise
        """
        deferral_role_ids = config.get('deferral_role_ids', [])
        
        if not deferral_role_ids:
            return False  # No deferral roles configured
        
        # Check if user has any deferral role
        user_role_ids = {r.id for r in member.roles}
        return any(role_id in user_role_ids for role_id in deferral_role_ids)

    @app_commands.command(name="loadboosterroles", description="Load existing booster roles into the database")
    @app_commands.default_permissions(administrator=True)
    async def load_booster_roles(self, interaction: discord.Interaction):
        """Scan server for existing booster roles and save them to database (requires administrator permission)"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        # Defer response since this might take a while
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            guild = interaction.guild
            roles_found = 0
            roles_saved = 0
            errors = 0
            
            # Build a report
            report_lines = []
            
            # Scan all members for boosters and their custom roles
            for member in guild.members:
                # Check if member is a booster
                if not member.premium_since:
                    continue
                
                # Find their custom role (only one member, not @everyone)
                personal_roles = [
                    role for role in member.roles 
                    if not role.is_default() 
                    and len(role.members) == 1
                ]
                
                if not personal_roles:
                    continue
                
                # Use the highest personal role by position
                role = max(personal_roles, key=lambda r: r.position)
                roles_found += 1
                
                try:
                    # Prepare role data
                    color_hex = f"#{role.color.value:06x}"
                    secondary_color_hex = f"#{role.secondary_color.value:06x}" if role.secondary_color else None
                    tertiary_color_hex = f"#{role.tertiary_color.value:06x}" if role.tertiary_color else None
                    icon_hash = role.icon.key if role.icon else None
                    icon_data = None
                    
                    # Try to get existing color type from database, default to 'solid'
                    existing_role = db.get_booster_role(member.id, guild.id)
                    color_type = existing_role['color_type'] if existing_role else 'solid'
                    
                    # Download icon data if it exists
                    if role.icon:
                        try:
                            icon_data = await role.icon.read()
                        except Exception as e:
                            logger.error(f"Could not read icon for {member.display_name}: {e}")
                    
                    # Save to database (preserve existing color_type or default to 'solid')
                    db.store_booster_role(
                        user_id=member.id,
                        guild_id=guild.id,
                        role_id=role.id,
                        role_name=role.name,
                        color_hex=color_hex,
                        color_type=color_type,
                        icon_hash=icon_hash,
                        icon_data=icon_data,
                        secondary_color_hex=secondary_color_hex,
                        tertiary_color_hex=tertiary_color_hex
                    )
                    
                    roles_saved += 1
                    icon_status = " (with icon)" if icon_data else ""
                    report_lines.append(f"✅ {member.display_name}: `{role.name}`{icon_status}")
                    
                except Exception as e:
                    errors += 1
                    report_lines.append(f"❌ {member.display_name}: Error - {str(e)[:50]}")
                    logger.error(f"Error saving role for {member.display_name}: {e}")
            
            # Build summary message
            summary = f"**Booster Roles Scan Complete**\n\n"
            summary += f"📊 **Summary:**\n"
            summary += f"• Found: {roles_found} role(s)\n"
            summary += f"• Saved: {roles_saved} role(s)\n"
            summary += f"• Errors: {errors}\n\n"
            
            if report_lines:
                summary += "**Details:**\n" + "\n".join(report_lines[:20])  # Limit to 20 entries to avoid message length issues
                if len(report_lines) > 20:
                    summary += f"\n... and {len(report_lines) - 20} more"
            else:
                summary += "ℹ️ No custom booster roles found in this server."
            
            await interaction.followup.send(summary, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error loading booster roles: {e}")
            await interaction.followup.send(
                f"❌ An error occurred while loading booster roles: {str(e)[:100]}",
                ephemeral=True
            )
    
    @app_commands.command(name="saveboosterrole", description="Manually save a booster role to the database")
    @app_commands.describe(
        role="The role to save",
        user="The user who owns the role (select from dropdown)",
        user_id="Alternative: Manually enter user ID (for users not in server)"
    )
    @app_commands.default_permissions(administrator=True)
    async def save_booster_role(self, interaction: discord.Interaction, role: discord.Role, user: discord.User = None, user_id: str = None):
        """Manually save a specific booster role to the database (requires administrator permission)"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        # Require either user or user_id
        if not user and not user_id:
            await interaction.response.send_message("❌ Please provide either a user (from dropdown) or a user_id.", ephemeral=True)
            return
        
        # Defer response
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Determine which user ID to use
            if user:
                uid = user.id
            else:
                # Convert user_id string to int
                try:
                    uid = int(user_id)
                except ValueError:
                    await interaction.followup.send(
                        f"❌ Invalid user ID format. Please provide a numeric user ID.",
                        ephemeral=True
                    )
                    return
            
            # Try to get member info (optional - just for booster status warning)
            member = interaction.guild.get_member(uid)
            booster_warning = ""
            if member and not member.premium_since:
                booster_warning = f"\n⚠️ Note: <@{uid}> is not currently a server booster."
            elif not member:
                booster_warning = f"\n⚠️ Note: User is not currently in the server."
            
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Prepare role data
            color_hex = f"#{role.color.value:06x}"
            secondary_color_hex = f"#{role.secondary_color.value:06x}" if role.secondary_color else None
            tertiary_color_hex = f"#{role.tertiary_color.value:06x}" if role.tertiary_color else None
            icon_hash = role.icon.key if role.icon else None
            icon_data = None
            
            # Auto-detect color type based on colors present
            if tertiary_color_hex:
                color_type = "holographic"
            elif secondary_color_hex:
                color_type = "gradient"
            else:
                color_type = "solid"
            
            # Download icon data if it exists
            if role.icon:
                try:
                    icon_data = await role.icon.read()
                except Exception as e:
                    logger.error(f"Could not read icon for role {role.name}: {e}")
            
            # Save to database
            db.store_booster_role(
                user_id=uid,
                guild_id=interaction.guild.id,
                role_id=role.id,
                role_name=role.name,
                color_hex=color_hex,
                color_type=color_type,
                icon_hash=icon_hash,
                icon_data=icon_data,
                secondary_color_hex=secondary_color_hex,
                tertiary_color_hex=tertiary_color_hex
            )
            
            icon_status = " with icon" if icon_data else ""
            color_info = color_hex
            if secondary_color_hex:
                color_info += f", {secondary_color_hex}"
            if tertiary_color_hex:
                color_info += f", {tertiary_color_hex}"
            
            await interaction.followup.send(
                f"✅ Saved booster role for <@{uid}>\n"
                f"• Role: `{role.name}`\n"
                f"• Colors: {color_info} ({color_type}){icon_status}{booster_warning}",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Error saving booster role: {e}")
            await interaction.followup.send(
                f"❌ An error occurred while saving the booster role: {str(e)[:100]}",
                ephemeral=True
            )

    @app_commands.command(name="shiftrole", description="Move a role up or down by one position")
    @app_commands.describe(
        role="The role to move",
        direction="Move the role one step up or down"
    )
    @app_commands.choices(direction=[
        app_commands.Choice(name="Up", value="up"),
        app_commands.Choice(name="Down", value="down"),
    ])
    @app_commands.checks.has_permissions(manage_roles=True)
    async def shift_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        direction: app_commands.Choice[str]
    ):
        """Move a role by exactly one position in the role hierarchy."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            guild = interaction.guild
            bot_member = guild.me

            if role.is_default():
                await interaction.followup.send("❌ You can't move @everyone.", ephemeral=True)
                return

            if role.managed:
                await interaction.followup.send("❌ That role is managed by an integration/bot and cannot be moved.", ephemeral=True)
                return

            if not bot_member.guild_permissions.manage_roles:
                await interaction.followup.send("❌ I need the Manage Roles permission to do that.", ephemeral=True)
                return

            if bot_member.top_role <= role:
                await interaction.followup.send("❌ I can't manage that role because it is above my highest role.", ephemeral=True)
                return

            if interaction.user.top_role <= role and not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ You can't manage a role higher than or equal to your top role.", ephemeral=True)
                return

            current_pos = role.position
            if direction.value == "up":
                target_pos = current_pos + 1
                max_pos = bot_member.top_role.position - 1
                if target_pos > max_pos:
                    await interaction.followup.send(
                        f"❌ Can't move {role.mention} higher because it would be at/above my top role.",
                        ephemeral=True
                    )
                    return
            else:
                target_pos = current_pos - 1
                if target_pos < 1:
                    await interaction.followup.send(
                        f"❌ Can't move {role.mention} lower; it's already at the bottom.",
                        ephemeral=True
                    )
                    return

            await guild.edit_role_positions(
                positions={role: target_pos},
                reason=f"Role shifted {direction.value} by {interaction.user}",
            )

            await interaction.followup.send(
                f"✅ Shifted {role.mention} **{direction.value}** from `{current_pos}` to `{target_pos}`.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to shift role: {e}", ephemeral=True)

    @app_commands.command(name="autorole", description="Configure automatic role assignment rules")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        action="What to do with the role rule",
        rule_name="Unique name for this rule (e.g., 'verified_roles')",
        trigger_role="Role that triggers this rule when added to a member",
        roles_to_add="Roles to add (comma-separated role mentions or IDs)",
        roles_to_remove="Roles to remove (comma-separated role mentions or IDs)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="add - Create/update a role rule", value="add"),
        app_commands.Choice(name="remove - Delete a role rule", value="remove"),
        app_commands.Choice(name="list - Show all role rules", value="list"),
        app_commands.Choice(name="check-all - Check all members for compliance", value="check-all")
    ])
    async def autorole(
        self, 
        interaction: discord.Interaction, 
        action: app_commands.Choice[str],
        rule_name: str = None,
        trigger_role: discord.Role = None,
        roles_to_add: str = None,
        roles_to_remove: str = None
    ):
        """Configure automatic role assignment when members gain specific roles"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            if not db.connection_pool:
                db.init_pool()
            
            # Ensure table exists
            
            if action.value == "list":
                rules = db.get_role_rules(interaction.guild.id)
                
                if not rules:
                    await interaction.followup.send("📋 No role rules configured for this server.", ephemeral=True)
                    return
                
                embed = discord.Embed(
                    title="⚙️ Automatic Role Assignment Rules",
                    description=f"Found {len(rules)} rule(s)",
                    color=discord.Color.blue()
                )
                
                for rule in rules:
                    trigger = interaction.guild.get_role(rule['trigger_role_id'])
                    trigger_name = trigger.mention if trigger else f"<@&{rule['trigger_role_id']}> (deleted)"
                    
                    add_roles = []
                    for role_id in rule['roles_to_add']:
                        r = interaction.guild.get_role(role_id)
                        add_roles.append(r.mention if r else f"<@&{role_id}> (deleted)")
                    
                    remove_roles = []
                    for role_id in rule['roles_to_remove']:
                        r = interaction.guild.get_role(role_id)
                        remove_roles.append(r.mention if r else f"<@&{role_id}> (deleted)")
                    
                    value_parts = [f"**Trigger:** {trigger_name}"]
                    if add_roles:
                        value_parts.append(f"**Add:** {', '.join(add_roles)}")
                    if remove_roles:
                        value_parts.append(f"**Remove:** {', '.join(remove_roles)}")
                    
                    embed.add_field(
                        name=f"📌 {rule['rule_name']}",
                        value="\n".join(value_parts),
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            elif action.value == "remove":
                if not rule_name:
                    await interaction.followup.send("❌ Please provide a rule name to remove.", ephemeral=True)
                    return
                
                # Check if rule exists
                rule = db.get_role_rule(interaction.guild.id, rule_name)
                if not rule:
                    await interaction.followup.send(f"❌ No rule named `{rule_name}` found.", ephemeral=True)
                    return
                
                db.remove_role_rule(interaction.guild.id, rule_name)
                await interaction.followup.send(f"✅ Removed role rule `{rule_name}`", ephemeral=True)
                return
            
            elif action.value == "add":
                if not all([rule_name, trigger_role]):
                    await interaction.followup.send(
                        "❌ Please provide a rule name and trigger role.\n"
                        "Example: `/admin tools autorole add rule_name:verified_roles trigger_role:@Verified roles_to_add:@lvl 0 roles_to_remove:@Unverified`",
                        ephemeral=True
                    )
                    return
                
                if not roles_to_add and not roles_to_remove:
                    await interaction.followup.send(
                        "❌ Please provide at least one role to add or remove.",
                        ephemeral=True
                    )
                    return
                
                # Parse role mentions/IDs from comma-separated strings
                def parse_roles(role_str: str) -> list[int]:
                    if not role_str:
                        return []
                    
                    role_ids = []
                    parts = [p.strip() for p in role_str.split(',')]
                    
                    for part in parts:
                        # Try to extract role ID from mention format <@&123456>
                        if part.startswith('<@&') and part.endswith('>'):
                            role_id = int(part[3:-1])
                            role_ids.append(role_id)
                        # Try to parse as raw ID
                        elif part.isdigit():
                            role_ids.append(int(part))
                        # Try to find by name
                        else:
                            role = discord.utils.get(interaction.guild.roles, name=part)
                            if role:
                                role_ids.append(role.id)
                    
                    return role_ids
                
                add_ids = parse_roles(roles_to_add)
                remove_ids = parse_roles(roles_to_remove)
                
                # Save the rule
                db.add_role_rule(
                    interaction.guild.id,
                    rule_name,
                    trigger_role.id,
                    add_ids,
                    remove_ids
                )
                
                # Build response
                response_parts = [f"✅ Created/updated role rule `{rule_name}`"]
                response_parts.append(f"**Trigger:** {trigger_role.mention}")
                
                if add_ids:
                    add_mentions = [f"<@&{rid}>" for rid in add_ids]
                    response_parts.append(f"**Add:** {', '.join(add_mentions)}")
                
                if remove_ids:
                    remove_mentions = [f"<@&{rid}>" for rid in remove_ids]
                    response_parts.append(f"**Remove:** {', '.join(remove_mentions)}")
                
                await interaction.followup.send("\n".join(response_parts), ephemeral=True)
                return
            
            elif action.value == "check-all":
                # Scan all members and ensure role rules are properly applied
                await interaction.followup.send("🔍 Checking all members for role rule compliance...", ephemeral=True)
                
                rules = db.get_role_rules(interaction.guild.id)
                if not rules:
                    await interaction.followup.send("📋 No role rules configured.", ephemeral=True)
                    return
                
                results = {'fixed': [], 'issues': [], 'errors': []}
                
                for member in interaction.guild.members:
                    if member.bot:
                        continue
                    
                    member_role_ids = {r.id for r in member.roles}
                    
                    for rule in rules:
                        trigger_role_id = rule['trigger_role_id']
                        roles_to_add = rule['roles_to_add']
                        roles_to_remove = rule['roles_to_remove']
                        
                        # If user has trigger role, check if roles_to_add and roles_to_remove are correct
                        if trigger_role_id in member_role_ids:
                            # Check roles that should be added
                            for add_role_id in roles_to_add:
                                if add_role_id not in member_role_ids:
                                    add_role = interaction.guild.get_role(add_role_id)
                                    if add_role:
                                        results['issues'].append(f"{member.mention} missing {add_role.mention} (trigger: <@&{trigger_role_id}>)")
                            
                            # Check roles that should be removed
                            for remove_role_id in roles_to_remove:
                                if remove_role_id in member_role_ids:
                                    remove_role = interaction.guild.get_role(remove_role_id)
                                    if remove_role:
                                        results['issues'].append(f"{member.mention} still has {remove_role.mention} (should be removed by trigger: <@&{trigger_role_id}>)")
                
                # Build response
                embed = discord.Embed(
                    title="🔍 Role Rule Compliance Check",
                    color=discord.Color.blue()
                )
                
                if results['issues']:
                    embed.add_field(
                        name=f"⚠️ Issues Found ({len(results['issues'])})",
                        value="\n".join(results['issues'][:20]),
                        inline=False
                    )
                    if len(results['issues']) > 20:
                        embed.add_field(name="...", value=f"and {len(results['issues']) - 20} more", inline=False)
                else:
                    embed.add_field(name="✅ All Clear", value="No compliance issues found!", inline=False)
                
                if results['errors']:
                    embed.add_field(
                        name=f"❌ Errors ({len(results['errors'])})",
                        value="\n".join(results['errors'][:10]),
                        inline=False
                    )
                
                embed.set_footer(text="Note: This is a read-only check. Issues are not automatically fixed.")
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
        
        except Exception as e:
            logger.error(f"Error in autorole command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="channelrestriction", description="Configure channel access restrictions based on roles")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        action="What action to perform",
        channel="The channel to restrict access to (text/voice/forum/stage/category)",
        blocking_role="Role that blocks access to the channel",
        mode="How to apply the role: block users with it, or require it"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="add - Block role from viewing channel", value="add"),
        app_commands.Choice(name="remove - Remove channel restriction", value="remove"),
        app_commands.Choice(name="list - Show all channel restrictions", value="list"),
        app_commands.Choice(name="apply-all - Apply restrictions to all current members", value="apply-all")
    ])
    @app_commands.choices(mode=[
        app_commands.Choice(name="Block (users WITH the role are blocked)", value="block"),
        app_commands.Choice(name="Require (users WITHOUT the role are blocked)", value="require"),
    ])
    async def channel_restriction(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        channel: discord.abc.GuildChannel = None,
        blocking_role: discord.Role = None,
        mode: app_commands.Choice[str] = None
    ):
        """Configure automatic channel permission overwrites when members have specific roles"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            if not db.connection_pool:
                db.init_pool()
            
            # Ensure table exists

            mode_value = mode.value if mode else None
            
            if action.value == "list":
                embed = self._build_channel_restrictions_embed(interaction.guild)
                view = ChannelRestrictionListView(interaction.guild, self)
                await interaction.followup.send(embed=embed, view=view)
                return
            
            elif action.value == "remove":
                if not channel or not blocking_role:
                    await interaction.followup.send("❌ Please specify both channel and blocking_role for remove action.", ephemeral=True)
                    return

                if mode_value:
                    db.remove_channel_restriction(interaction.guild.id, channel.id, blocking_role.id, mode_value)
                    mode_text = mode_value
                else:
                    # Remove both modes if unspecified
                    db.remove_channel_restriction(interaction.guild.id, channel.id, blocking_role.id, "block")
                    db.remove_channel_restriction(interaction.guild.id, channel.id, blocking_role.id, "require")
                    mode_text = "block & require"

                await interaction.followup.send(
                    f"✅ Removed channel restriction\n"
                    f"• Channel: {channel.mention}\n"
                    f"• Role: {blocking_role.mention}\n"
                    f"• Mode: {mode_text}",
                    ephemeral=True
                )
                return
            
            elif action.value == "add":
                if not channel or not blocking_role:
                    await interaction.followup.send("❌ Please specify both channel and blocking_role for add action.", ephemeral=True)
                    return
                
                mode_to_save = mode_value or "block"

                # Save to database
                db.add_channel_restriction(interaction.guild.id, channel.id, blocking_role.id, mode_to_save)
                
                await interaction.followup.send(
                    f"✅ Added channel restriction\n"
                    f"• Channel: {channel.mention}\n"
                    f"• Role: {blocking_role.mention}\n"
                    f"• Mode: {mode_to_save}\n\n"
                    f"{'Members with' if mode_to_save == 'block' else 'Members without'} {blocking_role.mention} will be blocked from viewing {channel.mention}.\n"
                    f"Use `apply-all` to apply this to existing members.",
                    ephemeral=True
                )
                return
            
            elif action.value == "apply-all":
                # Apply all channel restrictions to current members
                await interaction.followup.send("🔄 Applying channel restrictions to all members...", ephemeral=True)
                
                restrictions = db.get_channel_restrictions(interaction.guild.id)
                if not restrictions:
                    await interaction.followup.send("❌ No channel restrictions configured.", ephemeral=True)
                    return
                
                results = {'blocked': 0, 'unblocked': 0, 'errors': []}
                
                # Group restrictions by channel for efficiency
                from collections import defaultdict
                by_channel = defaultdict(list)
                for r in restrictions:
                    by_channel[r['channel_id']].append({'role_id': r['blocking_role_id'], 'mode': r.get('mode', 'block')})
                
                # Process each channel
                for channel_id, channel_restrictions in by_channel.items():
                    channel_obj = interaction.guild.get_channel(channel_id)
                    if not channel_obj:
                        results['errors'].append(f"Channel {channel_id} not found")
                        continue
                    
                    # Check each member
                    for member in interaction.guild.members:
                        if member.bot:
                            continue
                        
                        member_role_ids = {r.id for r in member.roles}
                        should_block = False
                        for entry in channel_restrictions:
                            role_id = entry['role_id']
                            mode_entry = entry.get('mode', 'block')
                            has_role = role_id in member_role_ids
                            if mode_entry == 'block' and has_role:
                                should_block = True
                                break
                            if mode_entry == 'require' and not has_role:
                                should_block = True
                                break
                        
                        try:
                            if should_block:
                                # Block access
                                await channel_obj.set_permissions(
                                    member,
                                    view_channel=False,
                                    reason="Channel restriction enforcement"
                                )
                                results['blocked'] += 1
                            else:
                                # Check if they have an overwrite and remove it
                                overwrite = channel_obj.overwrites_for(member)
                                if overwrite.view_channel is False:
                                    await channel_obj.set_permissions(
                                        member,
                                        overwrite=None,
                                        reason="Removing channel restriction"
                                    )
                                    results['unblocked'] += 1
                        except Exception as e:
                            results['errors'].append(f"{member.display_name}: {str(e)[:50]}")
                
                # Build response
                embed = discord.Embed(
                    title="✅ Channel Restrictions Applied",
                    color=discord.Color.green()
                )
                
                embed.add_field(
                    name="📊 Results",
                    value=f"Blocked: {results['blocked']}\nUnblocked: {results['unblocked']}",
                    inline=False
                )
                
                if results['errors']:
                    error_text = "\n".join(results['errors'][:5])
                    if len(results['errors']) > 5:
                        error_text += f"\n... and {len(results['errors']) - 5} more"
                    embed.add_field(name="⚠️ Errors", value=error_text, inline=False)
                
                await interaction.followup.send(embed=embed, view=ChannelRestrictionListView(interaction.guild, self))
                return
        
        except Exception as e:
            logger.error(f"Error in channelrestriction command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="globalmute_role", description="Create or configure a role that mutes users in all channels")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        role="Existing role to use as the global mute role (optional)",
        name="Name for a new mute role (if role not provided)",
        apply_to_all_channels="Apply deny send/add_react/speak overwrites to all channels now"
    )
    async def global_mute_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role | None = None,
        name: str = "Muted",
        apply_to_all_channels: bool = True,
        disable: bool = False
    ):
        """Create or reuse a mute role and apply deny overwrites to all channels."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            guild = interaction.guild

            if disable:
                db.set_guild_setting(guild.id, "global_mute_role_id", "")
                await interaction.followup.send("🛑 Global mute role disabled; config cleared.", ephemeral=True)
                return

            mute_role = role
            if not mute_role:
                # Create role with no permissions; we rely on overwrites per-channel
                mute_role = await guild.create_role(name=name, reason="Create global mute role")

            # Persist the role for member-update automation
            db.set_guild_setting(guild.id, "global_mute_role_id", str(mute_role.id))

            updated_channels = 0
            skipped_tickets = 0
            errors = []

            if apply_to_all_channels:
                for channel in guild.channels:
                    try:
                        if isinstance(channel, discord.TextChannel) and channel.name.startswith("ticket-"):
                            skipped_tickets += 1
                            continue
                        # Text/voice/threads all share send messages/add reactions/speak
                        await channel.set_permissions(
                            mute_role,
                            send_messages=False,
                            add_reactions=False,
                            speak=False,
                            send_messages_in_threads=False,
                            create_public_threads=False,
                            create_private_threads=False,
                            send_tts_messages=False,
                            use_application_commands=False,
                            stream=False,
                            embed_links=False,
                            attach_files=False,
                            reason="Apply global mute role permissions"
                        )
                        updated_channels += 1
                    except Exception as e:
                        errors.append(f"{getattr(channel, 'name', str(channel.id))}: {str(e)[:80]}")

            summary = [
                f"✅ Global mute role ready: {mute_role.mention}",
                f"Applied overwrites to {updated_channels} channel(s)." if apply_to_all_channels else "Skipped channel overwrites."
            ]
            if skipped_tickets:
                summary.append(f"Skipped {skipped_tickets} ticket channel(s).")
            if errors:
                summary.append(f"⚠️ Errors on {len(errors)} channel(s): " + "; ".join(errors[:3]))
            await interaction.followup.send("\n".join(summary), ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating/applying mute role: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="schedule_role", description="Schedule role add/remove for a member at a specific time")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        user="User to modify",
        add_roles="Roles to add at the scheduled time (mentions, names, or IDs, comma-separated)",
        remove_roles="Roles to remove at the scheduled time (mentions, names, or IDs, comma-separated)",
        run_at="When to apply (ISO timestamp, e.g., 2024-12-31T23:59:00Z)",
        delete_id="ID of a scheduled change to delete",
        list_only="If true, just list scheduled changes"
    )
    async def schedule_role(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None,
        add_roles: str = "",
        remove_roles: str = "",
        run_at: str = "",
        delete_id: str = "",
        list_only: bool = False
    ):
        """Create/list/delete scheduled role changes."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        if not db.connection_pool:
            db.init_pool()

        # List
        if list_only:
            entries = db.list_scheduled_role_changes(interaction.guild.id)
            if not entries:
                await interaction.followup.send("📋 No scheduled role changes.", ephemeral=True)
                return
            lines = []
            for e in entries[:20]:
                add_mentions = [interaction.guild.get_role(rid).mention for rid in e["add_ids"] if interaction.guild.get_role(rid)]
                rem_mentions = [interaction.guild.get_role(rid).mention for rid in e["remove_ids"] if interaction.guild.get_role(rid)]
                user_obj = interaction.guild.get_member(e["user_id"])
                creator = interaction.guild.get_member(e["created_by"]) if e.get("created_by") else None
                lines.append(
                    f"ID `{e['id']}` • User: {user_obj.mention if user_obj else e['user_id']} • "
                    f"Adds: {', '.join(add_mentions) if add_mentions else 'None'} • "
                    f"Removes: {', '.join(rem_mentions) if rem_mentions else 'None'} • "
                    f"Run at: <t:{int(e['run_at'].timestamp())}:F> • Status: {e['status']}"
                    + (f" • Error: {e['last_error']}" if e.get("last_error") else "")
                )
            await interaction.followup.send("\n".join(lines), ephemeral=True)
            return

        # Delete
        if delete_id:
            try:
                delete_int = int(delete_id)
            except ValueError:
                await interaction.followup.send("❌ delete_id must be an integer ID from the list.", ephemeral=True)
                return
            db.delete_scheduled_role_change(delete_int, interaction.guild.id)
            await interaction.followup.send(f"🗑️ Deleted scheduled role change `{delete_int}`.", ephemeral=True)
            return

        # Create
        if not user:
            await interaction.followup.send("❌ Please specify a user.", ephemeral=True)
            return
        if not run_at:
            await interaction.followup.send("❌ Please provide run_at (ISO time, e.g., 2024-12-31T23:59:00Z).", ephemeral=True)
            return

        # Parse roles
        def parse_roles(raw: str) -> list[int]:
            ids = []
            for part in [p.strip() for p in raw.split(",") if p.strip()]:
                if part.startswith("<@&") and part.endswith(">"):
                    part = part[3:-1]
                if part.isdigit():
                    ids.append(int(part))
                else:
                    found = discord.utils.get(interaction.guild.roles, name=part)
                    if found:
                        ids.append(found.id)
            return ids

        add_ids = parse_roles(add_roles)
        rem_ids = parse_roles(remove_roles)

        try:
            run_dt = dt.datetime.fromisoformat(run_at.replace("Z", "+00:00"))
        except Exception:
            await interaction.followup.send("❌ Invalid run_at format. Use ISO like 2024-12-31T23:59:00Z.", ephemeral=True)
            return

        sched_id = db.create_scheduled_role_change(interaction.guild.id, user.id, add_ids, rem_ids, run_dt, interaction.user.id)
        add_text = ", ".join(f"<@&{rid}>" for rid in add_ids) if add_ids else "None"
        rem_text = ", ".join(f"<@&{rid}>" for rid in rem_ids) if rem_ids else "None"

        await interaction.followup.send(
            f"✅ Scheduled role change `{sched_id}` for {user.mention}\n"
            f"• Add: {add_text}\n"
            f"• Remove: {rem_text}\n"
            f"• At: <t:{int(run_dt.timestamp())}:F>",
            ephemeral=True
        )

    @app_commands.command(name="kick_inactive_level", description="Kick members with a level role who haven't chatted in N days")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        role="Level role to check (e.g., @lvl 5)",
        days="Kick if last message older than this many days (or never)",
        dry_run="If true, report only without kicking"
    )
    async def kick_inactive_level(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        days: int,
        dry_run: bool = True
    ):
        """Kick members with the specified level role and no recent messages."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        if days < 1:
            await interaction.response.send_message("❌ Days must be at least 1.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        if not db.connection_pool:
            db.init_pool()

        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        candidates = []
        errors = []

        for member in interaction.guild.members:
            if member.bot:
                continue
            if role not in member.roles:
                continue
            last_seen = db.get_member_last_activity(interaction.guild.id, member.id)
            if not last_seen or last_seen < cutoff:
                candidates.append((member, last_seen))

        kicked = 0
        if not dry_run:
            for member, _ in candidates:
                try:
                    await member.kick(reason=f"Inactive {days}d with role {role.name}")
                    kicked += 1
                except Exception as e:
                    errors.append(f"{member.display_name}: {str(e)[:80]}")

        lines = [
            f"🔍 Found {len(candidates)} member(s) with {role.mention} inactive ≥ {days}d.",
            "Dry run; no kicks performed." if dry_run else f"Kicked {kicked} member(s)."
        ]
        if errors:
            lines.append(f"⚠️ Errors on {len(errors)} member(s): " + "; ".join(errors[:3]))

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name="messagemirror", description="Configure message mirroring between channels")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        action="What action to perform",
        source_channel="The channel to mirror messages from",
        target_channel="The channel to mirror messages to",
        message_link="Optional: Discord message link to mirror a specific message",
        limit="Optional: Number of existing messages to copy (default: 100, max: 1000)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="add - Mirror messages from source to target", value="add"),
        app_commands.Choice(name="remove - Stop mirroring to target", value="remove"),
        app_commands.Choice(name="list - Show all mirror configurations", value="list"),
        app_commands.Choice(name="mirror-one - Mirror a specific message", value="mirror-one"),
        app_commands.Choice(name="copy-existing - Copy existing messages from source", value="copy-existing")
    ])
    async def message_mirror(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        source_channel: discord.TextChannel = None,
        target_channel: discord.TextChannel = None,
        message_link: str = None,
        limit: int = 100
    ):
        """Configure automatic message mirroring between channels"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            if not db.connection_pool:
                db.init_pool()
            
            # Ensure tables exist
            
            if action.value == "list":
                mirrors = db.get_message_mirrors(interaction.guild.id)
                
                if not mirrors:
                    await interaction.followup.send("📋 No message mirrors configured for this server.", ephemeral=True)
                    return
                
                embed = discord.Embed(
                    title="🪞 Message Mirror Configurations",
                    description=f"Found {len(mirrors)} mirror(s)",
                    color=discord.Color.blue()
                )
                
                # Group by source channel
                from collections import defaultdict
                by_source = defaultdict(list)
                for m in mirrors:
                    by_source[m['source_channel_id']].append(m)
                
                for source_id, source_mirrors in by_source.items():
                    source_ch = interaction.guild.get_channel(source_id)
                    source_name = source_ch.mention if source_ch else f"<#{source_id}> (deleted)"
                    
                    targets = []
                    for m in source_mirrors:
                        target_ch = interaction.guild.get_channel(m['target_channel_id'])
                        target_name = target_ch.mention if target_ch else f"<#{m['target_channel_id']}> (deleted)"
                        targets.append(target_name)
                    
                    embed.add_field(
                        name=f"📤 Source: {source_name}",
                        value=f"**Mirrors to:**\n" + "\n".join(f"• {t}" for t in targets),
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            elif action.value == "remove":
                if not source_channel or not target_channel:
                    await interaction.followup.send("❌ Please specify both source and target channels.", ephemeral=True)
                    return
                
                db.remove_message_mirror(interaction.guild.id, source_channel.id, target_channel.id)
                await interaction.followup.send(
                    f"✅ Removed message mirror\n"
                    f"• Source: {source_channel.mention}\n"
                    f"• Target: {target_channel.mention}",
                    ephemeral=True
                )
                return
            
            elif action.value == "mirror-one":
                if not message_link:
                    await interaction.followup.send("❌ Please provide a message link to mirror.", ephemeral=True)
                    return
                
                if not target_channel:
                    await interaction.followup.send("❌ Please specify a target channel.", ephemeral=True)
                    return
                
                # Parse message link
                # Format: https://discord.com/channels/{guild_id}/{channel_id}/{message_id}
                import re
                link_match = re.match(r'https://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)', message_link)
                
                if not link_match:
                    await interaction.followup.send("❌ Invalid message link format.", ephemeral=True)
                    return
                
                link_guild_id = int(link_match.group(1))
                link_channel_id = int(link_match.group(2))
                link_message_id = int(link_match.group(3))
                
                # Verify it's from this guild
                if link_guild_id != interaction.guild.id:
                    await interaction.followup.send("❌ Message must be from this server.", ephemeral=True)
                    return
                
                # Get the source channel and message
                msg_channel = interaction.guild.get_channel(link_channel_id)
                if not msg_channel:
                    await interaction.followup.send("❌ Source channel not found.", ephemeral=True)
                    return
                
                try:
                    original_msg = await msg_channel.fetch_message(link_message_id)
                except discord.NotFound:
                    await interaction.followup.send("❌ Message not found.", ephemeral=True)
                    return
                except discord.Forbidden:
                    await interaction.followup.send("❌ I don't have permission to read messages in that channel.", ephemeral=True)
                    return
                
                # Check target channel permissions
                bot_member = interaction.guild.get_member(interaction.client.user.id)
                target_perms = target_channel.permissions_for(bot_member)
                if not target_perms.send_messages or not target_perms.embed_links:
                    await interaction.followup.send(
                        f"❌ I don't have permission to send messages in {target_channel.mention}.",
                        ephemeral=True
                    )
                    return
                
                # Mirror the message
                content = original_msg.content or ""
                
                embed = discord.Embed(
                    description=content if content else "*[No text content]*",
                    color=original_msg.author.color if original_msg.author.color != discord.Color.default() else discord.Color.blue(),
                    timestamp=original_msg.created_at
                )
                
                embed.set_author(
                    name=original_msg.author.display_name,
                    icon_url=original_msg.author.display_avatar.url
                )
                
                embed.set_footer(text=f"Mirrored from #{msg_channel.name}")
                
                # Handle attachments
                if original_msg.attachments:
                    attachment_text = "\n\n**Attachments:**\n" + "\n".join(
                        f"[{att.filename}]({att.url})" for att in original_msg.attachments
                    )
                    
                    if len(embed.description + attachment_text) <= 4096:
                        embed.description += attachment_text
                    else:
                        embed.add_field(
                            name="📎 Attachments",
                            value="\n".join(f"[{att.filename}]({att.url})" for att in original_msg.attachments[:10]),
                            inline=False
                        )
                
                # Handle embeds
                embeds_to_send = [embed]
                if original_msg.embeds:
                    for orig_embed in original_msg.embeds[:9]:
                        embeds_to_send.append(orig_embed)
                
                try:
                    mirror_msg = await target_channel.send(embeds=embeds_to_send)
                    
                    # Track the mirrored message
                    db.track_mirrored_message(
                        original_msg.id,
                        msg_channel.id,
                        mirror_msg.id,
                        target_channel.id,
                        interaction.guild.id
                    )
                    
                    await interaction.followup.send(
                        f"✅ Mirrored message to {target_channel.mention}\n"
                        f"[Jump to mirror]({mirror_msg.jump_url})\n\n"
                        f"The mirror will automatically update if the original message is edited or deleted.",
                        ephemeral=True
                    )
                except Exception as e:
                    await interaction.followup.send(f"❌ Error mirroring message: {str(e)[:200]}", ephemeral=True)
                
                return
            
            elif action.value == "copy-existing":
                if not source_channel or not target_channel:
                    await interaction.followup.send("❌ Please specify both source and target channels.", ephemeral=True)
                    return
                
                # Validate limit
                if limit < 1 or limit > 1000:
                    await interaction.followup.send("❌ Limit must be between 1 and 1000.", ephemeral=True)
                    return
                
                # Check bot permissions
                bot_member = interaction.guild.get_member(interaction.client.user.id)
                
                source_perms = source_channel.permissions_for(bot_member)
                if not source_perms.read_messages or not source_perms.read_message_history:
                    await interaction.followup.send(
                        f"❌ I don't have permission to read messages in {source_channel.mention}.",
                        ephemeral=True
                    )
                    return
                
                target_perms = target_channel.permissions_for(bot_member)
                if not target_perms.send_messages or not target_perms.embed_links:
                    await interaction.followup.send(
                        f"❌ I don't have permission to send messages in {target_channel.mention}.",
                        ephemeral=True
                    )
                    return
                
                # Import mirror helper
                from core.message_mirroring import create_mirror_embed
                
                # Fetch messages from source channel
                try:
                    messages = []
                    async for msg in source_channel.history(limit=limit, oldest_first=True):
                        if not msg.author.bot:  # Skip bot messages
                            messages.append(msg)
                    
                    if not messages:
                        await interaction.followup.send(
                            f"📋 No messages found in {source_channel.mention} to copy.",
                            ephemeral=True
                        )
                        return
                    
                    # Send a status update
                    await interaction.followup.send(
                        f"⏳ Copying {len(messages)} message(s) from {source_channel.mention} to {target_channel.mention}...\n"
                        f"This may take a moment.",
                        ephemeral=True
                    )
                    
                    # Copy each message
                    copied_count = 0
                    errors = 0
                    
                    for msg in messages:
                        try:
                            # Create mirror embed
                            embed = create_mirror_embed(msg)
                            
                            # Handle original embeds
                            embeds_to_send = [embed]
                            if msg.embeds:
                                for orig_embed in msg.embeds[:9]:
                                    embeds_to_send.append(orig_embed)
                            
                            # Send mirrored message
                            mirror_msg = await target_channel.send(embeds=embeds_to_send)
                            
                            # Track the mirrored message
                            db.track_mirrored_message(
                                msg.id,
                                msg.channel.id,
                                mirror_msg.id,
                                target_channel.id,
                                msg.guild.id
                            )
                            logger.info(f"Tracked mirror: original={msg.id} -> mirror={mirror_msg.id} in channel={target_channel.id}")
                            
                            copied_count += 1
                            
                        except Exception as e:
                            logger.error(f"Error copying message {msg.id}: {e}")
                            errors += 1
                    
                    # Send completion message
                    result_msg = f"✅ Successfully copied {copied_count} message(s) from {source_channel.mention} to {target_channel.mention}."
                    if errors > 0:
                        result_msg += f"\n⚠️ Failed to copy {errors} message(s)."
                    result_msg += "\n\nThese messages will now auto-sync on edits and deletes."
                    
                    await interaction.channel.send(result_msg)
                    
                except discord.Forbidden:
                    await interaction.channel.send(
                        "❌ I don't have permission to access one of the channels.",
                    )
                except Exception as e:
                    logger.error(f"Error in copy-existing: {e}")
                    await interaction.channel.send(
                        f"❌ Error copying messages: {str(e)[:200]}",
                    )
                return
            
            elif action.value == "add":
                if not source_channel or not target_channel:
                    await interaction.followup.send("❌ Please specify both source and target channels.", ephemeral=True)
                    return
                
                if source_channel.id == target_channel.id:
                    await interaction.followup.send("❌ Source and target channels cannot be the same.", ephemeral=True)
                    return
                
                # Check bot permissions in both channels
                bot_member = interaction.guild.get_member(interaction.client.user.id)
                
                source_perms = source_channel.permissions_for(bot_member)
                if not source_perms.read_messages or not source_perms.read_message_history:
                    await interaction.followup.send(
                        f"❌ I don't have permission to read messages in {source_channel.mention}.\n"
                        f"Please grant me `Read Messages` and `Read Message History` permissions.",
                        ephemeral=True
                    )
                    return
                
                target_perms = target_channel.permissions_for(bot_member)
                if not target_perms.send_messages or not target_perms.embed_links:
                    await interaction.followup.send(
                        f"❌ I don't have permission to send messages in {target_channel.mention}.\n"
                        f"Please grant me `Send Messages` and `Embed Links` permissions.",
                        ephemeral=True
                    )
                    return
                
                # Save to database
                db.add_message_mirror(interaction.guild.id, source_channel.id, target_channel.id)
                
                await interaction.followup.send(
                    f"✅ Added message mirror\n"
                    f"• Source: {source_channel.mention}\n"
                    f"• Target: {target_channel.mention}\n\n"
                    f"Messages sent in {source_channel.mention} will now be copied to {target_channel.mention}.\n"
                    f"When the original message is edited or deleted, all mirrors will update automatically.",
                    ephemeral=True
                )
                return
        
        except Exception as e:
            logger.error(f"Error in messagemirror command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="conditionalrole", description="Manage conditional role assignments with blocking roles")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        action="What action to perform",
        role="The role to configure or assign",
        blocking_roles="Roles that prevent assignment (comma-separated)",
        deferral_roles="Roles that defer assignment - mark eligible but don't assign (comma-separated)",
        user="The user to mark/check/assign (for mark/unmark/check/assign actions)",
        dry_run="If True, show what would happen without making changes (for check-all)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="configure - Set up a conditional role", value="configure"),
        app_commands.Choice(name="remove-config - Remove role configuration", value="remove_config"),
        app_commands.Choice(name="list-configs - Show all configured roles", value="list_configs"),
        app_commands.Choice(name="mark - Mark user as eligible", value="mark"),
        app_commands.Choice(name="unmark - Remove user eligibility", value="unmark"),
        app_commands.Choice(name="check - Check user eligibility", value="check"),
        app_commands.Choice(name="assign - Assign role if eligible", value="assign"),
        app_commands.Choice(name="override-enable - Bypass blocking/deferral for a user", value="override_enable"),
        app_commands.Choice(name="override-disable - Remove override for a user", value="override_disable"),
        app_commands.Choice(name="override-check - Check override status", value="override_check"),
        app_commands.Choice(name="override-list - List active overrides", value="override_list"),
        app_commands.Choice(name="list-eligible - Show eligible users", value="list_eligible"),
        app_commands.Choice(name="check-all - Run all conditional role checks", value="check_all")
    ])
    async def conditional_role(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        role: discord.Role = None,
        blocking_roles: str = None,
        deferral_roles: str = None,
        user: discord.Member = None,
        dry_run: bool = False
    ):
        """Manage conditional role assignments with eligibility tracking and blocking roles"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        action_value = action.value
        
        # Actions that require a user parameter
        user_required_actions = [
            "mark",
            "unmark",
            "check",
            "assign",
            "override_enable",
            "override_disable",
            "override_check"
        ]
        if action_value in user_required_actions and not user:
            await interaction.followup.send(f"❌ Please specify a user for the {action_value} action.", ephemeral=True)
            return
        
        try:
            if not db.connection_pool:
                db.init_pool()
            
            # Ensure tables exist
            
            # ================================================================
            # CONFIGURATION ACTIONS
            # ================================================================
            
            if action_value == "list_configs":
                embed = self._build_conditional_role_configs_embed(interaction.guild)
                view = ConditionalRoleListView(interaction.guild, self)
                await interaction.followup.send(embed=embed, view=view)
                return
            
            elif action_value == "configure":
                if not role:
                    await interaction.followup.send("❌ Please specify a role to configure.", ephemeral=True)
                    return
                
                # Parse blocking roles
                blocking_role_ids = []
                if blocking_roles:
                    parts = [p.strip() for p in blocking_roles.split(',')]
                    for part in parts:
                        # Try to extract role ID from mention
                        if part.startswith('<@&') and part.endswith('>'):
                            blocking_role_ids.append(int(part[3:-1]))
                        # Try to parse as raw ID
                        elif part.isdigit():
                            blocking_role_ids.append(int(part))
                        # Try to find by name
                        else:
                            found_role = discord.utils.get(interaction.guild.roles, name=part)
                            if found_role:
                                blocking_role_ids.append(found_role.id)
                
                # Parse deferral roles
                deferral_role_ids = []
                if deferral_roles:
                    parts = [p.strip() for p in deferral_roles.split(',')]
                    for part in parts:
                        # Try to extract role ID from mention
                        if part.startswith('<@&') and part.endswith('>'):
                            deferral_role_ids.append(int(part[3:-1]))
                        # Try to parse as raw ID
                        elif part.isdigit():
                            deferral_role_ids.append(int(part))
                        # Try to find by name
                        else:
                            found_role = discord.utils.get(interaction.guild.roles, name=part)
                            if found_role:
                                deferral_role_ids.append(found_role.id)
                
                db.add_conditional_role_config(
                    interaction.guild.id,
                    role.id,
                    role.name,
                    blocking_role_ids,
                    deferral_role_ids
                )
                
                response_parts = [f"✅ Configured conditional role: {role.mention}"]
                if blocking_role_ids:
                    blocking_mentions = [f"<@&{rid}>" for rid in blocking_role_ids]
                    response_parts.append(f"**Blocking Roles:** {', '.join(blocking_mentions)}")
                else:
                    response_parts.append("**Blocking Roles:** None")
                
                if deferral_role_ids:
                    deferral_mentions = [f"<@&{rid}>" for rid in deferral_role_ids]
                    response_parts.append(f"**Deferral Roles:** {', '.join(deferral_mentions)} (mark eligible but don't assign)")
                else:
                    response_parts.append("**Deferral Roles:** None")
                
                await interaction.followup.send("\n".join(response_parts), ephemeral=True)
                return
            
            elif action_value == "remove_config":
                if not role:
                    await interaction.followup.send("❌ Please specify a role to remove configuration for.", ephemeral=True)
                    return
                
                config = db.get_conditional_role_config(interaction.guild.id, role.id)
                if not config:
                    await interaction.followup.send(f"❌ {role.mention} is not configured as a conditional role.", ephemeral=True)
                    return
                
                db.remove_conditional_role_config(interaction.guild.id, role.id)
                await interaction.followup.send(f"✅ Removed conditional role configuration for {role.mention}", ephemeral=True)
                return
            
            # ================================================================
            # ELIGIBILITY ACTIONS
            # ================================================================
            
            elif action_value == "list_eligible":
                if not role:
                    await interaction.followup.send("❌ Please specify a role to list eligible users for.", ephemeral=True)
                    return
                
                # Check if role is configured
                config = db.get_conditional_role_config(interaction.guild.id, role.id)
                if not config:
                    await interaction.followup.send(
                        f"❌ {role.mention} is not configured as a conditional role.\n"
                        f"Use `/admin tools conditionalrole configure role:{role.mention}` first.",
                        ephemeral=True
                    )
                    return
                
                eligible_users = db.get_conditional_role_eligible_users(interaction.guild.id, role.id)
                
                if not eligible_users:
                    await interaction.followup.send(f"📋 No users currently marked as eligible for {role.mention}.", ephemeral=True)
                    return
                
                embed = discord.Embed(
                    title=f"🔓 Eligible Users for {role.name}",
                    description=f"Found {len(eligible_users)} eligible user(s)",
                    color=discord.Color.green()
                )
                
                for user_data in eligible_users[:25]:
                    member = interaction.guild.get_member(user_data['user_id'])
                    member_name = member.display_name if member else f"Unknown User"
                    
                    marked_by = ""
                    if user_data['marked_by_user_id']:
                        marker = interaction.guild.get_member(user_data['marked_by_user_id'])
                        marked_by = f"\nMarked by: {marker.mention if marker else 'Unknown'}"
                    
                    notes = f"\nNotes: {user_data['notes']}" if user_data['notes'] else ""
                    
                    embed.add_field(
                        name=f"✅ {member_name}",
                        value=f"<@{user_data['user_id']}> • {user_data['marked_at'].strftime('%Y-%m-%d')}{marked_by}{notes}",
                        inline=False
                    )
                
                if len(eligible_users) > 25:
                    embed.set_footer(text=f"Showing 25 of {len(eligible_users)} eligible users")
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            elif action_value == "override_list":
                overrides = db.get_conditional_role_overrides(
                    interaction.guild.id,
                    role.id if role else None
                )

                if not overrides:
                    if role:
                        await interaction.followup.send(
                            f"📋 No active overrides found for {role.mention}.",
                            ephemeral=True
                        )
                    else:
                        await interaction.followup.send("📋 No active conditional-role overrides found.", ephemeral=True)
                    return

                title = "🛡️ Active Conditional-Role Overrides"
                if role:
                    title = f"🛡️ Active Overrides for {role.name}"

                embed = discord.Embed(
                    title=title,
                    description=f"Found {len(overrides)} override(s)",
                    color=discord.Color.blue()
                )

                for entry in overrides[:25]:
                    member = interaction.guild.get_member(entry['user_id'])
                    role_obj = interaction.guild.get_role(entry['role_id'])

                    user_text = member.mention if member else f"<@{entry['user_id']}>"
                    role_text = role_obj.mention if role_obj else f"<@&{entry['role_id']}>"
                    when_text = entry['updated_at'].strftime('%Y-%m-%d %H:%M UTC') if entry.get('updated_at') else "Unknown"

                    embed.add_field(
                        name=f"User: {user_text}",
                        value=f"Role: {role_text}\nUpdated: {when_text}",
                        inline=False
                    )

                if len(overrides) > 25:
                    embed.set_footer(text=f"Showing 25 of {len(overrides)} overrides")

                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # check-all action - run all conditional role checks
            elif action_value == "check_all":
                # Get all guild members and configs
                configs = db.get_all_conditional_role_configs(interaction.guild.id)
                if not configs:
                    await interaction.followup.send("❌ No conditional roles configured for this server.", ephemeral=True)
                    return
                
                results = {
                    'removed': [],
                    'granted': [],
                    'errors': []
                }
                
                # Check each member in the guild
                async for member in interaction.guild.fetch_members(limit=None):
                    if member.bot:
                        continue  # Skip bots
                    
                    try:
                        for config in configs:
                            conditional_role_id = config['role_id']
                            blocking_role_ids = config.get('blocking_role_ids', [])
                            deferral_role_ids = config.get('deferral_role_ids', [])
                            
                            member_role_ids = {r.id for r in member.roles}
                            has_conditional_role = conditional_role_id in member_role_ids
                            has_blocking_role = any(br_id in member_role_ids for br_id in blocking_role_ids)
                            has_deferral_role = any(dr_id in member_role_ids for dr_id in deferral_role_ids)
                            has_override = db.has_conditional_role_override(
                                interaction.guild.id,
                                member.id,
                                conditional_role_id
                            )
                            
                            # Check eligibility
                            eligibility = db.get_conditional_role_eligibility(
                                interaction.guild.id,
                                member.id,
                                conditional_role_id
                            )
                            is_deferred = bool(eligibility)  # If in table, they're deferred
                            
                            conditional_role = interaction.guild.get_role(conditional_role_id)
                            role_name = conditional_role.name if conditional_role else f"Role {conditional_role_id}"

                            # Logic -1: Explicit override always wins and force-grants if missing
                            if has_override:
                                if not has_conditional_role:
                                    action_desc = f"Grant {role_name} to {member.mention} (override enabled)"
                                    results['granted'].append(action_desc)
                                    if not dry_run and conditional_role:
                                        try:
                                            await member.add_roles(conditional_role, reason="Conditional role override enabled")
                                            db.unmark_conditional_role_eligible(interaction.guild.id, member.id, conditional_role_id)
                                        except Exception as e:
                                            results['errors'].append(f"Failed to grant {role_name} to {member.mention}: {e}")
                                continue
                            
                            # Logic 0: User has conditional role but also has blocking roles - REMOVE IT
                            if has_conditional_role and has_blocking_role:
                                blocking_roles_found = [
                                    interaction.guild.get_role(rid) 
                                    for rid in blocking_role_ids 
                                    if rid in member_role_ids
                                ]
                                blocking_mentions = [r.mention for r in blocking_roles_found if r]
                                action_desc = f"Remove {role_name} from {member.mention} (has blocking roles: {', '.join(blocking_mentions) if blocking_mentions else 'blocking role'})"
                                results['removed'].append(action_desc)
                                
                                if not dry_run and conditional_role:
                                    try:
                                        await member.remove_roles(conditional_role, reason="Conditional role check: user has blocking roles")
                                        db.unmark_conditional_role_eligible(interaction.guild.id, member.id, conditional_role_id)
                                    except Exception as e:
                                        results['errors'].append(f"Failed to remove {role_name} from {member.mention}: {e}")
                                continue

                            # Logic 1: User has conditional role but has deferral roles - REMOVE IT
                            if has_conditional_role and has_deferral_role and deferral_role_ids:
                                action_desc = f"Remove {role_name} from {member.mention} (has deferral roles)"
                                results['removed'].append(action_desc)
                                
                                if not dry_run and conditional_role:
                                    try:
                                        await member.remove_roles(conditional_role, reason="Conditional role check: user has deferral roles")
                                    except Exception as e:
                                        results['errors'].append(f"Failed to remove {role_name} from {member.mention}: {e}")
                            
                            # Logic 2: User is deferred, has no deferral roles, and doesn't have conditional role - GRANT IT
                            elif is_deferred and not has_deferral_role and not has_conditional_role and not has_blocking_role and deferral_role_ids:
                                action_desc = f"Grant {role_name} to {member.mention} (eligible, deferral criteria met)"
                                results['granted'].append(action_desc)
                                
                                if not dry_run and conditional_role:
                                    try:
                                        await member.add_roles(conditional_role, reason="Conditional role check: criteria met")
                                        # Remove from eligibility now that they have the role
                                        db.unmark_conditional_role_eligible(interaction.guild.id, member.id, conditional_role_id)
                                    except Exception as e:
                                        results['errors'].append(f"Failed to grant {role_name} to {member.mention}: {e}")
                    
                    except Exception as e:
                        results['errors'].append(f"Error checking member {member.mention}: {e}")
                
                # Build response
                mode_text = "📋 DRY RUN" if dry_run else "✅ EXECUTED"
                embed = discord.Embed(
                    title=f"{mode_text} - Conditional Role Check",
                    color=discord.Color.blue() if dry_run else discord.Color.green()
                )
                
                if results['removed']:
                    embed.add_field(
                        name=f"🗑️ To Remove ({len(results['removed'])})",
                        value="\n".join(results['removed'][:10]),
                        inline=False
                    )
                    if len(results['removed']) > 10:
                        embed.add_field(name="...", value=f"and {len(results['removed']) - 10} more", inline=False)
                
                if results['granted']:
                    embed.add_field(
                        name=f"✨ To Grant ({len(results['granted'])})",
                        value="\n".join(results['granted'][:10]),
                        inline=False
                    )
                    if len(results['granted']) > 10:
                        embed.add_field(name="...", value=f"and {len(results['granted']) - 10} more", inline=False)
                
                if results['errors']:
                    embed.add_field(
                        name=f"⚠️ Errors ({len(results['errors'])})",
                        value="\n".join(results['errors'][:5]),
                        inline=False
                    )
                    if len(results['errors']) > 5:
                        embed.add_field(name="...", value=f"and {len(results['errors']) - 5} more", inline=False)
                
                if not results['removed'] and not results['granted'] and not results['errors']:
                    embed.description = "✅ All conditional roles are correctly assigned!"
                elif dry_run:
                    embed.set_footer(text="Use dry_run: false to apply these changes")
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # All remaining actions require both role and user
            if not role:
                await interaction.followup.send(f"❌ Please specify a role for the `{action.name}` action.", ephemeral=True)
                return
            
            if not user:
                await interaction.followup.send(f"❌ Please specify a user for the `{action.name}` action.", ephemeral=True)
                return
            
            # Check if role is configured
            config = db.get_conditional_role_config(interaction.guild.id, role.id)
            if not config:
                await interaction.followup.send(
                    f"❌ {role.mention} is not configured as a conditional role.\n"
                    f"Use `/admin tools conditionalrole configure role:{role.mention}` first.",
                    ephemeral=True
                )
                return
            
            if action_value == "mark":
                db.mark_conditional_role_eligible(interaction.guild.id, user.id, role.id, interaction.user.id)
                await interaction.followup.send(f"✅ Marked {user.mention} as eligible for {role.mention}.", ephemeral=True)
                return
            
            elif action_value == "unmark":
                db.unmark_conditional_role_eligible(interaction.guild.id, user.id, role.id)
                await interaction.followup.send(f"✅ Removed eligibility for {user.mention} to receive {role.mention}.", ephemeral=True)
                return
            
            elif action_value == "check":
                is_eligible = db.is_conditional_role_eligible(interaction.guild.id, user.id, role.id)
                has_override = db.has_conditional_role_override(interaction.guild.id, user.id, role.id)
                
                if is_eligible:
                    status = f"✅ {user.mention} is eligible for {role.mention}."
                else:
                    status = f"❌ {user.mention} is NOT eligible for {role.mention}."

                if has_override:
                    status += "\n🛡️ Override is enabled (blocking/deferral checks are bypassed)."

                await interaction.followup.send(status, ephemeral=True)
                return

            elif action_value == "override_enable":
                db.set_conditional_role_override(interaction.guild.id, user.id, role.id, True)

                assigned_now = False
                if role not in user.roles:
                    try:
                        await user.add_roles(role, reason=f"Conditional role override enabled by {interaction.user.display_name}")
                        assigned_now = True
                    except discord.Forbidden:
                        await interaction.followup.send(
                            f"🛡️ Override enabled for {user.mention} on {role.mention}, but I couldn't assign the role due to permissions.",
                            ephemeral=True
                        )
                        return
                    except Exception as e:
                        await interaction.followup.send(
                            f"🛡️ Override enabled for {user.mention} on {role.mention}, but role assignment failed: {str(e)[:200]}",
                            ephemeral=True
                        )
                        return

                db.unmark_conditional_role_eligible(interaction.guild.id, user.id, role.id)
                result = f"🛡️ Override enabled for {user.mention} on {role.mention}."
                if assigned_now:
                    result += "\n✅ Role assigned immediately."
                else:
                    result += "\nℹ️ User already has the role."
                await interaction.followup.send(result, ephemeral=True)
                return

            elif action_value == "override_disable":
                db.set_conditional_role_override(interaction.guild.id, user.id, role.id, False)
                await interaction.followup.send(
                    f"✅ Override disabled for {user.mention} on {role.mention}. Future checks will enforce blocking/deferral rules again.",
                    ephemeral=True
                )
                return

            elif action_value == "override_check":
                has_override = db.has_conditional_role_override(interaction.guild.id, user.id, role.id)
                status = "enabled" if has_override else "disabled"
                await interaction.followup.send(
                    f"🛡️ Override for {user.mention} on {role.mention}: **{status}**",
                    ephemeral=True
                )
                return
            
            elif action_value == "assign":
                # Check eligibility
                is_eligible = db.is_conditional_role_eligible(interaction.guild.id, user.id, role.id)
                
                if not is_eligible:
                    await interaction.followup.send(
                        f"❌ {user.mention} has not been marked as eligible for {role.mention}.\n"
                        f"Use `/admin tools conditionalrole mark role:{role.mention} user:{user.mention}` first.",
                        ephemeral=True
                    )
                    return

                has_override = db.has_conditional_role_override(interaction.guild.id, user.id, role.id)

                if has_override:
                    try:
                        await user.add_roles(role, reason=f"Conditional role override assignment by {interaction.user.display_name}")
                        db.unmark_conditional_role_eligible(interaction.guild.id, user.id, role.id)
                        await interaction.followup.send(
                            f"🛡️ Override active: assigned {role.mention} to {user.mention} (blocking/deferral ignored).",
                            ephemeral=True
                        )
                    except discord.Forbidden:
                        await interaction.followup.send(
                            f"❌ I don't have permission to assign roles.\n"
                            f"Make sure my role is higher than {role.mention}.",
                            ephemeral=True
                        )
                    except Exception as e:
                        await interaction.followup.send(f"❌ Error assigning role: {str(e)[:200]}", ephemeral=True)
                    return
                
                # Check for blocking roles
                blocking_role_ids = config['blocking_role_ids']
                user_role_ids = {r.id for r in user.roles}
                
                has_blocking_role = any(rid in user_role_ids for rid in blocking_role_ids)
                
                if has_blocking_role:
                    blocking_roles_found = [
                        interaction.guild.get_role(rid) 
                        for rid in blocking_role_ids 
                        if rid in user_role_ids
                    ]
                    blocking_mentions = [r.mention for r in blocking_roles_found if r]
                    
                    await interaction.followup.send(
                        f"❌ Cannot assign {role.mention} to {user.mention}.\n"
                        f"They have one or more blocking roles: {', '.join(blocking_mentions)}\n\n"
                        f"Remove these roles first before assigning {role.mention}.",
                        ephemeral=True
                    )
                    return
                
                # Check if they already have the role
                if role in user.roles:
                    await interaction.followup.send(
                        f"ℹ️ {user.mention} already has {role.mention}.",
                        ephemeral=True
                    )
                    return
                
                # Check if assignment should be deferred based on config
                should_defer = self._should_defer_assignment(user, config)
                
                if should_defer:
                    # Get deferral role names for message
                    deferral_role_names = []
                    for deferral_id in config.get('deferral_role_ids', []):
                        deferral_role = interaction.guild.get_role(deferral_id)
                        if deferral_role:
                            deferral_role_names.append(deferral_role.name)
                    
                    # Mark eligible but don't assign yet
                    db.mark_conditional_role_eligible(
                        interaction.guild.id, 
                        user.id, 
                        role.id, 
                        interaction.user.id,
                        notes=f"Deferred: has deferral role(s): {', '.join(deferral_role_names)}"
                    )
                    await interaction.followup.send(
                        f"⏳ {user.mention} has been marked as eligible for {role.mention}.\n"
                        f"**Assignment deferred:** They currently have one or more deferral roles: {', '.join(deferral_role_names)}\n"
                        f"The role will be assignable once these roles are removed.",
                        ephemeral=True
                    )
                    return
                
                # Assign the role normally
                try:
                    await user.add_roles(role, reason=f"Conditional role assigned by {interaction.user.display_name}")
                    
                    # Log eligibility in database
                    db.mark_conditional_role_eligible(
                        interaction.guild.id,
                        user.id,
                        role.id,
                        interaction.user.id,
                        notes="Assigned directly by admin"
                    )
                    
                    await interaction.followup.send(
                        f"✅ Successfully assigned {role.mention} to {user.mention}!",
                        ephemeral=True
                    )
                except discord.Forbidden:
                    await interaction.followup.send(
                        f"❌ I don't have permission to assign roles.\n"
                        f"Make sure my role is higher than {role.mention}.",
                        ephemeral=True
                    )
                except Exception as e:
                    await interaction.followup.send(f"❌ Error assigning role: {str(e)[:200]}", ephemeral=True)
                return
            
            # check-all action - run all conditional role checks
        
        except Exception as e:
            logger.error(f"Error in conditionalrole command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)


class AdminMaintenanceGroup(app_commands.Group):
    """Server maintenance and moderation tools"""
    
    def __init__(self):
        super().__init__(name="maintenance", description="Server maintenance and moderation tools")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _enforce_default_permissions(interaction)

    def _parse_duration_seconds(self, duration: str) -> int | None:
        """Parse shorthand duration strings like 10m/2h/1d into seconds."""
        if not duration:
            return None
        duration = duration.strip().lower()
        match = re.fullmatch(r"(\d+)([smhd])", duration)
        if not match:
            return None
        value = int(match.group(1))
        unit = match.group(2)
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return value * multipliers.get(unit, 0)

    @app_commands.command(name="assignlvl0", description="Assign lvl 0 to all verified members without a level role")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def assign_lvl0(self, interaction: discord.Interaction):
        """Assign lvl 0 role to verified members who don't have any level role"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            if not db.connection_pool:
                db.init_pool()
            # Load configurable names/prefix
            verified_name = db.get_guild_setting(interaction.guild.id, "verified_role_name", "verified")
            prefix = db.get_guild_setting(interaction.guild.id, "level_role_prefix", "lvl ")
            lvl0_name = f"{prefix}0"

            # Get role objects
            verified_role = discord.utils.get(interaction.guild.roles, name=verified_name)
            lvl0_role = discord.utils.get(interaction.guild.roles, name=lvl0_name)
            
            if not verified_role:
                await interaction.followup.send(f"❌ No '{verified_name}' role found in this server.", ephemeral=True)
                return
            
            if not lvl0_role:
                await interaction.followup.send(f"❌ No '{lvl0_name}' role found in this server.", ephemeral=True)
                return
            
            # Find members who need lvl 0
            assigned_count = 0
            errors = []
            
            for member in interaction.guild.members:
                # Skip bots
                if member.bot:
                    continue
                
                # Check if they have verified role
                if verified_role in member.roles:
                    # Check if they have any lvl role
                    has_lvl_role = any(role.name.lower().startswith(prefix.lower()) for role in member.roles)
                    
                    if not has_lvl_role:
                        # They need lvl 0
                        try:
                            await member.add_roles(lvl0_role, reason=f"Manual lvl 0 assignment by {interaction.user}")
                            assigned_count += 1
                            logger.info(f"Assigned lvl 0 to {member.display_name}")
                        except Exception as e:
                            error_msg = f"{member.display_name}: {str(e)[:50]}"
                            errors.append(error_msg)
                            logger.error(f"Error assigning lvl 0 to {member.display_name}: {e}")
            
            # Build response
            response = f"✅ Assigned lvl 0 to **{assigned_count}** member(s)"
            
            if errors:
                response += f"\n\n⚠️ Failed to assign {len(errors)} member(s):"
                for error in errors[:5]:  # Show first 5 errors
                    response += f"\n- {error}"
                if len(errors) > 5:
                    response += f"\n... and {len(errors) - 5} more"
            
            await interaction.followup.send(response, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in assign_lvl0 command: {e}")
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)[:200]}",
                ephemeral=True
            )
    
    @app_commands.command(name="kickunverified", description="Kick unverified users who have been in the server for 30+ days")
    @app_commands.describe(dry_run="Preview who would be kicked without actually kicking them")
    @app_commands.default_permissions(kick_members=True)
    async def kick_unverified(self, interaction: discord.Interaction, dry_run: bool = False):
        """Kick unverified users who have been members for 30+ days and are not in a verification ticket"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            if not db.connection_pool:
                db.init_pool()
            unverified_name = db.get_guild_setting(interaction.guild.id, "unverified_role_name", "unverified")

            # Get role objects
            unverified_role = discord.utils.get(interaction.guild.roles, name=unverified_name)
            
            if not unverified_role:
                await interaction.followup.send(f"❌ No '{unverified_name}' role found in this server.", ephemeral=True)
                return
            
            # Find the verification category
            verification_category = discord.utils.get(interaction.guild.categories, name="verification")
            
            # Count eligible members to kick
            now = dt.datetime.now(dt.timezone.utc)
            kicked_count = 0
            skipped_count = 0
            errors = []
            kick_list = []
            
            for member in interaction.guild.members:
                # Skip bots
                if member.bot:
                    continue
                
                # Check if they have unverified role
                if unverified_role in member.roles and member.joined_at:
                    days_since_join = (now - member.joined_at).days
                    
                    if days_since_join >= 30:
                        # Check if they're in a verification ticket
                        in_verification_ticket = False
                        
                        if verification_category:
                            for channel in verification_category.channels:
                                if isinstance(channel, discord.TextChannel) and channel.name.startswith("ticket-"):
                                    permissions = channel.permissions_for(member)
                                    if permissions.read_messages:
                                        in_verification_ticket = True
                                        break
                        
                        if in_verification_ticket:
                            skipped_count += 1
                            logger.info(f"Skipped {member.display_name} (in verification ticket)")
                        else:
                            # Kick the member (or add to dry run list)
                            if dry_run:
                                kick_list.append(f"{member.display_name} ({member.mention}) - {days_since_join} days")
                                kicked_count += 1
                            else:
                                try:
                                    await member.kick(reason=f"Kicked by {interaction.user}: Unverified for {days_since_join} days with no active verification ticket")
                                    kicked_count += 1
                                    logger.info(f"Kicked {member.display_name} (unverified for {days_since_join} days)")
                                except Exception as e:
                                    error_msg = f"{member.display_name}: {str(e)[:50]}"
                                    errors.append(error_msg)
                                    logger.error(f"Error kicking {member.display_name}: {e}")
            
            # Build response
            if dry_run:
                response = f"🔍 **DRY RUN** - Preview of members who would be kicked:\n\n"
                if kicked_count > 0:
                    response += f"Would kick **{kicked_count}** member(s):\n"
                    for member_info in kick_list[:10]:
                        response += f"- {member_info}\n"
                    if len(kick_list) > 10:
                        response += f"\n... and {len(kick_list) - 10} more"
                else:
                    response += "✅ No members would be kicked"
            else:
                response = f"✅ Kicked **{kicked_count}** unverified member(s) who have been in the server for 30+ days"
            
            if skipped_count > 0:
                response += f"\n🎫 {'Would skip' if dry_run else 'Skipped'} **{skipped_count}** member(s) with active verification tickets"
            
            if errors:
                response += f"\n\n⚠️ Failed to kick {len(errors)} member(s):"
                for error in errors[:5]:
                    response += f"\n- {error}"
                if len(errors) > 5:
                    response += f"\n... and {len(errors) - 5} more"
            
            await interaction.followup.send(response, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in kick_unverified command: {e}")
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)[:200]}",
                ephemeral=True
            )

    @app_commands.command(name="setrole", description="Add or remove a role from a specific member")
    @app_commands.describe(
        user="The member to modify",
        role="The role to add or remove",
        action="Choose whether to add or remove the role"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Remove", value="remove"),
    ])
    @app_commands.checks.has_permissions(manage_roles=True)
    async def set_role(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        role: discord.Role,
        action: app_commands.Choice[str]
    ):
        """Allow admins to add or remove a role from a member."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Bot permission/position checks
            bot_member = interaction.guild.me
            if not bot_member.guild_permissions.manage_roles:
                await interaction.followup.send("❌ I need the Manage Roles permission to do that.", ephemeral=True)
                return
            if bot_member.top_role <= role:
                await interaction.followup.send("❌ I can't manage that role because it is above my highest role.", ephemeral=True)
                return
            if interaction.user.top_role <= role and not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ You can't manage a role higher than or equal to your top role.", ephemeral=True)
                return

            if action.value == "add":
                if role in user.roles:
                    await interaction.followup.send(f"ℹ️ {user.mention} already has {role.mention}.", ephemeral=True)
                    return
                await user.add_roles(role, reason=f"Set by {interaction.user}")
                await interaction.followup.send(f"✅ Added {role.mention} to {user.mention}.", ephemeral=True)
            else:
                if role not in user.roles:
                    await interaction.followup.send(f"ℹ️ {user.mention} does not have {role.mention}.", ephemeral=True)
                    return
                await user.remove_roles(role, reason=f"Removed by {interaction.user}")
                await interaction.followup.send(f"✅ Removed {role.mention} from {user.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to update role: {e}", ephemeral=True)

    @app_commands.command(name="temporole", description="Add a role to a member for a limited duration (auto-removes after)")
    @app_commands.describe(
        user="The member to modify",
        role="The role to add temporarily",
        duration="How long to keep it (e.g., 30m, 2h, 1d)"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def temporary_role(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        role: discord.Role,
        duration: str
    ):
        """Add a role, then schedule its removal using the scheduled role runner."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        seconds = self._parse_duration_seconds(duration)
        max_seconds = 60 * 60 * 24 * 30  # Cap at 30 days
        if not seconds or seconds <= 0:
            await interaction.response.send_message(
                "❌ Invalid duration. Use formats like `30m`, `2h`, or `1d`.",
                ephemeral=True
            )
            return
        if seconds > max_seconds:
            await interaction.response.send_message(
                "❌ Duration too long. Please choose 30 days or less.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            bot_member = interaction.guild.me
            if not bot_member.guild_permissions.manage_roles:
                await interaction.followup.send("❌ I need the Manage Roles permission to do that.", ephemeral=True)
                return
            if bot_member.top_role <= role:
                await interaction.followup.send("❌ I can't manage that role because it is above my highest role.", ephemeral=True)
                return
            if interaction.user.top_role <= role and not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ You can't manage a role higher than or equal to your top role.", ephemeral=True)
                return

            added_now = False
            if role not in user.roles:
                await user.add_roles(role, reason=f"Temporary role until {duration} (set by {interaction.user})")
                added_now = True

            expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)
            if not db.connection_pool:
                db.init_pool()

            sched_id = db.create_scheduled_role_change(
                interaction.guild.id,
                user.id,
                [],
                [role.id],
                expires_at,
                interaction.user.id
            )

            await interaction.followup.send(
                f"✅ {role.mention} {'added to' if added_now else 'already on'} {user.mention}.\n"
                f"⏳ Will be removed at <t:{int(expires_at.timestamp())}:F> (<t:{int(expires_at.timestamp())}:R>)\n"
                f"🪪 Scheduled job ID: `{sched_id}` (managed by scheduled role runner)",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to set temporary role: {e}", ephemeral=True)

    @app_commands.command(name="restore_booster_roles", description="Restore all saved booster roles (icons/colors) for boosters in this server")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        role="Optional: filter to saved entries for this role",
        user="Optional: restore only this user"
    )
    async def restore_booster_roles(self, interaction: discord.Interaction, role: discord.Role = None, user: discord.Member = None):
        """Admin tool: restore booster roles for all boosters with saved data."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            if role:
                bot_member = interaction.guild.me
                if bot_member.top_role <= role:
                    await interaction.followup.send("❌ I can't manage the provided role; it's above my highest role.", ephemeral=True)
                    return
            if not db.connection_pool:
                db.init_pool()
            saved = db.get_all_booster_roles(interaction.guild.id)
            if not saved:
                await interaction.followup.send("ℹ️ No saved booster roles found for this server.", ephemeral=True)
                return

            # Apply filters if provided
            if user:
                saved = [s for s in saved if s["user_id"] == user.id]
            elif role:
                saved = [s for s in saved if s["role_id"] == role.id]

            if not saved:
                await interaction.followup.send("ℹ️ No matching saved booster entries for the given filters.", ephemeral=True)
                return

            restored = 0
            skipped = 0
            missing = 0
            errors = []

            for entry in saved:
                member = interaction.guild.get_member(entry["user_id"])
                if not member:
                    try:
                        member = await interaction.guild.fetch_member(entry["user_id"])
                    except Exception:
                        member = None
                if not member:
                    missing += 1
                    continue
                if not any(r.is_premium_subscriber() for r in member.roles):
                    skipped += 1
                    continue

                role_obj, icon_applied = await restore_member_booster_role(
                    interaction.guild,
                    member,
                    entry,
                    reason="Admin restore booster roles",
                    target_role=None  # apply to their personal role; role arg is only used as a filter
                )
                if role_obj:
                    restored += 1
                    if entry.get("icon_data") and not icon_applied:
                        errors.append(f"{member.display_name} (icon failed)")
                else:
                    errors.append(f"{member.display_name}")

            summary = [
                f"✅ Restored {restored} booster role(s).",
                f"⏭️ Skipped {skipped} (not currently boosters)." if skipped else "",
                f"❔ Missing {missing} user(s)." if missing else "",
                f"⚠️ Errors on: {', '.join(errors[:5])}" if errors else ""
            ]
            await interaction.followup.send("\n".join([s for s in summary if s]), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error restoring booster roles: {e}", ephemeral=True)

    @app_commands.command(name="edit_booster_role_color", description="Admin: Change a user's booster role color")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        user="The booster whose role to edit",
        style="Color style type",
        hex="Primary color (hex code like #FF0000)",
        hex2="Secondary color for gradient/holographic",
        hex3="Tertiary color for holographic only"
    )
    @app_commands.choices(style=[
        app_commands.Choice(name="Solid", value="solid"),
        app_commands.Choice(name="Gradient", value="gradient"),
        app_commands.Choice(name="Holographic", value="holographic")
    ])
    async def edit_booster_role_color(self, interaction: discord.Interaction, user: discord.Member, style: str = "solid", hex: str = None, hex2: str = None, hex3: str = None):
        """Admin tool: Edit a booster's role color."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        # Check if user is a booster
        if not any(role.is_premium_subscriber() for role in user.roles):
            await interaction.response.send_message("❌ That user is not a server booster!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Import here to avoid circular dependency
        from commands.booster_commands import get_or_create_booster_role, save_role_to_db

        # Get user's booster role
        db_role_data = db.get_booster_role(user.id, interaction.guild.id)
        
        # Find personal role
        personal_roles = [
            role for role in user.roles 
            if not role.is_default() 
            and len(role.members) == 1
        ]
        personal_role = max(personal_roles, key=lambda r: r.position) if personal_roles else None
        
        if not personal_role:
            await interaction.followup.send("❌ Could not find that user's booster role.", ephemeral=True)
            return

        # Generate color based on style and hex values
        primary_color = None
        secondary_color = None
        tertiary_color = None
        description = ""
        
        if style == "solid":
            if hex:
                try:
                    primary_color = discord.Color(int(hex.replace('#', ''), 16))
                    description = f"Solid color: {hex}"
                except ValueError:
                    await interaction.followup.send("❌ Invalid hex color format. Use format like #FF0000", ephemeral=True)
                    return
            else:
                primary_color = discord.Color.random()
                description = f"Random solid color: #{primary_color.value:06X}"
        
        elif style == "gradient":
            if hex:
                try:
                    primary_color = discord.Color(int(hex.replace('#', ''), 16))
                except ValueError:
                    await interaction.followup.send("❌ Invalid primary hex color format.", ephemeral=True)
                    return
            else:
                primary_color = discord.Color.random()
            
            if hex2:
                try:
                    secondary_color = discord.Color(int(hex2.replace('#', ''), 16))
                except ValueError:
                    await interaction.followup.send("❌ Invalid secondary hex color format.", ephemeral=True)
                    return
            else:
                secondary_color = discord.Color.random()
            
            description = f"Gradient: #{primary_color.value:06X} → #{secondary_color.value:06X}"
        
        elif style == "holographic":
            if hex and hex2 and hex3:
                try:
                    primary_color = discord.Color(int(hex.replace('#', ''), 16))
                    secondary_color = discord.Color(int(hex2.replace('#', ''), 16))
                    tertiary_color = discord.Color(int(hex3.replace('#', ''), 16))
                    description = f"Holographic: #{primary_color.value:06X}, #{secondary_color.value:06X}, #{tertiary_color.value:06X}"
                except ValueError:
                    await interaction.followup.send("❌ Invalid hex color format.", ephemeral=True)
                    return
            else:
                # Use Discord's default holographic values
                primary_color = discord.Color(11127295)
                secondary_color = discord.Color(16759788)
                tertiary_color = discord.Color(16761760)
                description = f"Holographic (Discord default)"
        
        try:
            await personal_role.edit(
                color=primary_color,
                secondary_color=secondary_color,
                tertiary_color=tertiary_color,
                reason=f"Admin edit by {interaction.user}"
            )
            
            # Save to database
            await save_role_to_db(user.id, interaction.guild.id, personal_role)
            
            await interaction.followup.send(
                f"✅ Updated {user.mention}'s booster role color\n{description}",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to edit that role.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error updating role: {e}", ephemeral=True)

    @app_commands.command(name="edit_booster_role_name", description="Admin: Change a user's booster role name")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        user="The booster whose role to edit",
        name="New name for the role"
    )
    async def edit_booster_role_name(self, interaction: discord.Interaction, user: discord.Member, name: str):
        """Admin tool: Edit a booster's role name."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        # Check if user is a booster
        if not any(role.is_premium_subscriber() for role in user.roles):
            await interaction.response.send_message("❌ That user is not a server booster!", ephemeral=True)
            return

        # Validate name
        if len(name) > 100:
            await interaction.response.send_message("❌ Role name must be 100 characters or less.", ephemeral=True)
            return
        if not name.strip():
            await interaction.response.send_message("❌ Role name cannot be empty.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Import here to avoid circular dependency
        from commands.booster_commands import save_role_to_db

        # Find personal role
        personal_roles = [
            role for role in user.roles 
            if not role.is_default() 
            and len(role.members) == 1
        ]
        personal_role = max(personal_roles, key=lambda r: r.position) if personal_roles else None
        
        if not personal_role:
            await interaction.followup.send("❌ Could not find that user's booster role.", ephemeral=True)
            return

        old_name = personal_role.name
        try:
            await personal_role.edit(name=name, reason=f"Admin edit by {interaction.user}")
            
            # Save to database
            await save_role_to_db(user.id, interaction.guild.id, personal_role)
            
            await interaction.followup.send(
                f"✅ Updated {user.mention}'s booster role name from **{old_name}** to **{name}**",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to edit that role.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error updating role: {e}", ephemeral=True)

    @app_commands.command(name="edit_booster_role_icon", description="Admin: Change a user's booster role icon")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        user="The booster whose role to edit",
        icon_url="Image URL for the role icon"
    )
    async def edit_booster_role_icon(self, interaction: discord.Interaction, user: discord.Member, icon_url: str):
        """Admin tool: Edit a booster's role icon."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        # Check if guild has role icons feature
        if "ROLE_ICONS" not in interaction.guild.features:
            await interaction.response.send_message("❌ This server doesn't support role icons.", ephemeral=True)
            return

        # Check if user is a booster
        if not any(role.is_premium_subscriber() for role in user.roles):
            await interaction.response.send_message("❌ That user is not a server booster!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Import here to avoid circular dependency
        from commands.booster_commands import save_role_to_db
        import aiohttp

        # Find personal role
        personal_roles = [
            role for role in user.roles 
            if not role.is_default() 
            and len(role.members) == 1
        ]
        personal_role = max(personal_roles, key=lambda r: r.position) if personal_roles else None
        
        if not personal_role:
            await interaction.followup.send("❌ Could not find that user's booster role.", ephemeral=True)
            return

        try:
            # Download the image
            async with aiohttp.ClientSession() as session:
                async with session.get(icon_url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send("❌ Could not download the image. Please check the URL.", ephemeral=True)
                        return
                    image_bytes = await resp.read()
            
            await personal_role.edit(display_icon=image_bytes, reason=f"Admin edit by {interaction.user}")
            
            # Save to database
            await save_role_to_db(user.id, interaction.guild.id, personal_role)
            
            await interaction.followup.send(
                f"✅ Updated {user.mention}'s booster role icon",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to edit that role.", ephemeral=True)
        except discord.HTTPException as e:
            if e.code == 50035:
                await interaction.followup.send("❌ Invalid image format. Please use PNG, JPG, or GIF.", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Discord error: {e}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ An unexpected error occurred: {e}", ephemeral=True)

    @app_commands.command(name="delete_role", description="Delete a single role (admin only)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        role="Role mention/ID/name to delete",
        confirm="Type YES to confirm deletion"
    )
    async def delete_role(self, interaction: discord.Interaction, role: str, confirm: str):
        """Delete exactly one role. Requires explicit YES confirmation."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        if confirm.strip().upper() != "YES":
            await interaction.response.send_message("❌ You must confirm deletion by typing YES.", ephemeral=True)
            return

        # Resolve the role
        role_obj = None
        part = role.strip()
        if part.startswith("<@&") and part.endswith(">"):
            try:
                role_id = int(part[3:-1])
                role_obj = interaction.guild.get_role(role_id)
            except Exception:
                pass
        elif part.isdigit():
            role_obj = interaction.guild.get_role(int(part))
        else:
            role_obj = discord.utils.get(interaction.guild.roles, name=part)

        if not role_obj:
            await interaction.response.send_message("❌ No valid role found to delete.", ephemeral=True)
            return

        bot_member = interaction.guild.me
        bot_top_pos = bot_member.top_role.position if bot_member and bot_member.top_role else -1
        if bot_top_pos <= role_obj.position:
            await interaction.response.send_message("❌ I can't delete that role; it's above my highest role.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            await role_obj.delete(reason=f"Deleted by {interaction.user}")
            await interaction.followup.send(f"✅ Deleted role: {role_obj.name}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ Failed to delete role: {e}", ephemeral=True)


class AdminGroup(app_commands.Group):
    """Admin commands for server management"""
    
    def __init__(self):
        super().__init__(
            name="admin",
            description="Admin server management commands",
            default_permissions=discord.Permissions(administrator=True)
        )
        
        # Add subgroups
        self.tools = AdminToolsGroup()
        self.maintenance = AdminMaintenanceGroup()
        
        self.add_command(self.tools)
        self.add_command(self.maintenance)
        # Note: Toggle commands removed - use /admin menu or /admin panel instead

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _enforce_default_permissions(interaction)
    
    @app_commands.command(name="menu", description="Open server settings menu")
    @app_commands.default_permissions(administrator=True)
    async def admin_menu(self, interaction: discord.Interaction):
        """Open interactive admin settings menu"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        try:
            if not db.connection_pool:
                db.init_pool()
            
            view = AdminSettingsView(interaction.guild.id)
            await interaction.response.send_message(
                embed=view.get_embed(),
                view=view,
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error opening admin menu: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while opening the admin menu.",
                ephemeral=True
            )
    
    @app_commands.command(name="panel", description="Create a persistent server settings panel in this channel")
    @app_commands.default_permissions(administrator=True)
    async def admin_panel(self, interaction: discord.Interaction):
        """Create a persistent admin settings panel in the channel"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        try:
            if not db.connection_pool:
                db.init_pool()
            
            custom_prefix = f"admin_panel:{interaction.guild.id}:{int(dt.datetime.now(dt.timezone.utc).timestamp())}"
            view = AdminSettingsView(interaction.guild.id, persistent=True, custom_id_prefix=custom_prefix)
            
            # Send the persistent panel to the channel
            message = await interaction.channel.send(
                embed=view.get_embed(),
                view=view
            )
            interaction.client.add_view(view, message_id=message.id)
            
            # Store panel metadata so it can be restored on restart
            db.save_persistent_panel(
                message_id=message.id,
                guild_id=interaction.guild.id,
                channel_id=interaction.channel.id,
                panel_type='admin_settings',
                metadata={'custom_id_prefix': custom_prefix}
            )
            
            # Confirm to the admin
            await interaction.response.send_message(
                "✅ Persistent admin panel created! Anyone with administrator permissions can use it.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error creating admin panel: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while creating the admin panel.",
                ephemeral=True
            )

    @app_commands.command(name="commands_menu", description="Open command toggles menu")
    @app_commands.default_permissions(administrator=True)
    async def commands_menu(self, interaction: discord.Interaction):
        """Open interactive command toggle menu (echo/TTS)."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        try:
            view = CommandToggleView(interaction.guild.id)
            await interaction.response.send_message(
                embed=view.get_embed(),
                view=view,
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error opening command toggle menu: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while opening the command toggle menu.",
                ephemeral=True
            )

    @app_commands.command(name="commands_panel", description="Create a persistent command toggles panel in this channel")
    @app_commands.default_permissions(administrator=True)
    async def commands_panel(self, interaction: discord.Interaction):
        """Create a persistent panel to toggle echo/TTS commands."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        try:
            await interaction.response.defer(ephemeral=True)

            custom_prefix = f"command_panel:{interaction.guild.id}:{int(dt.datetime.now(dt.timezone.utc).timestamp())}"
            view = CommandToggleView(interaction.guild.id, persistent=True, custom_id_prefix=custom_prefix)
            # Ensure persistence invariants in case decorators change children at runtime
            view.timeout = None
            view._set_persistent_custom_ids()
            view.update_buttons()

            message = await interaction.channel.send(
                embed=view.get_embed(),
                view=view
            )
            interaction.client.add_view(view, message_id=message.id)

            db.save_persistent_panel(
                message_id=message.id,
                guild_id=interaction.guild.id,
                channel_id=interaction.channel.id,
                panel_type='command_settings',
                metadata={'custom_id_prefix': custom_prefix}
            )

            await interaction.followup.send(
                "✅ Persistent command panel created! Administrators can toggle echo/TTS here.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error creating command panel: {e}")
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        f"❌ An error occurred while creating the command panel: {e}",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"❌ An error occurred while creating the command panel: {e}",
                        ephemeral=True
                    )
            except Exception:
                pass

    @app_commands.command(name="counting_config", description="Configure counting channel and penalty role")
    @app_commands.describe(
        channel="Channel to use for counting",
        idiot_role="Role to give users who break the count (24h)",
        start_number="Number to start from (next expected) — leave blank to keep current",
        disable="Disable counting in this server",
        clear_idiot_role="Clear any existing penalty role"
    )
    @app_commands.default_permissions(administrator=True)
    async def counting_config(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        idiot_role: discord.Role | None = None,
        start_number: int | None = None,
        disable: bool = False,
        clear_idiot_role: bool = False
    ):
        """Set or disable the counting channel and penalty role."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        if not db.connection_pool:
            db.init_pool()

        existing = db.get_counting_config(interaction.guild.id)

        if disable:
            db.clear_counting_config(interaction.guild.id)
            await interaction.followup.send("🛑 Counting disabled and configuration cleared.", ephemeral=True)
            return

        if not channel:
            await interaction.followup.send("❌ Please specify a channel for counting.", ephemeral=True)
            return

        # Use provided start_number or preserve existing if available
        if start_number is not None:
            start_number = max(1, start_number)
        elif existing and existing.get("next_number"):
            start_number = existing["next_number"]
        else:
            start_number = 1
        # Role selection: allow explicit clear, override, or reuse
        idiot_role_obj = None
        idiot_role_id = None
        if clear_idiot_role:
            idiot_role_id = None
        elif idiot_role:
            idiot_role_obj = idiot_role
            idiot_role_id = idiot_role.id
        elif existing and existing.get("idiot_role_id"):
            idiot_role_id = existing["idiot_role_id"]
            idiot_role_obj = interaction.guild.get_role(idiot_role_id)

        db.set_counting_config(interaction.guild.id, channel.id, idiot_role_id, start_number)

        if idiot_role_obj:
            role_text = idiot_role_obj.mention
        elif clear_idiot_role:
            role_text = "None (penalty role cleared)"
        else:
            role_text = "None (penalties skipped)"
        await interaction.followup.send(
            f"✅ Counting configured.\n• Channel: {channel.mention}\n"
            f"• Penalty role: {role_text}\n"
            f"• Next number: {start_number}",
            ephemeral=True
        )

    @app_commands.command(name="counting_set_number", description="Set the next expected counting number")
    @app_commands.describe(number="The next number users should post")
    @app_commands.default_permissions(administrator=True)
    async def counting_set_number(self, interaction: discord.Interaction, number: int):
        """Allow admins to set the counter to a specific number."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        config = db.get_counting_config(interaction.guild.id)
        if not config:
            await interaction.followup.send("❌ Counting is not configured. Run `/admin tools counting_config` first.", ephemeral=True)
            return

        number = max(1, number)
        db.set_counting_number(interaction.guild.id, number)
        await interaction.followup.send(f"✅ Counting set. Next expected number is now **{number}**.", ephemeral=True)

    @app_commands.command(name="level_settings", description="Configure level role naming and verified/unverified roles")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        level_prefix="Prefix for level roles (default: 'lvl ')",
        verified_role="Role considered verified (default: 'Verified')",
        unverified_role="Role considered unverified (default: 'Unverified')",
        show="If true, only show current settings"
    )
    async def level_settings(
        self,
        interaction: discord.Interaction,
        level_prefix: str | None = None,
        verified_role: discord.Role | None = None,
        unverified_role: discord.Role | None = None,
        show: bool = False
    ):
        """Configure how level/verified roles are detected (per guild)."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        if not db.connection_pool:
            db.init_pool()

        current_prefix = db.get_guild_setting(interaction.guild.id, "level_role_prefix", "lvl ")
        current_verified = db.get_guild_setting(interaction.guild.id, "verified_role_name", "verified")
        current_unverified = db.get_guild_setting(interaction.guild.id, "unverified_role_name", "unverified")

        if show or (level_prefix is None and verified_role is None and unverified_role is None):
            await interaction.followup.send(
                "📋 Level settings:\n"
                f"• level_role_prefix: `{current_prefix}`\n"
                f"• verified_role_name: `{current_verified}`\n"
                f"• unverified_role_name: `{current_unverified}`",
                ephemeral=True
            )
            return

        if level_prefix is not None:
            db.set_guild_setting(interaction.guild.id, "level_role_prefix", level_prefix)
            current_prefix = level_prefix
        if verified_role is not None:
            db.set_guild_setting(interaction.guild.id, "verified_role_name", verified_role.name)
            current_verified = verified_role.name
        if unverified_role is not None:
            db.set_guild_setting(interaction.guild.id, "unverified_role_name", unverified_role.name)
            current_unverified = unverified_role.name

        await interaction.followup.send(
            "✅ Updated level settings:\n"
            f"• level_role_prefix: `{current_prefix}`\n"
            f"• verified_role_name: `{current_verified}`\n"
            f"• unverified_role_name: `{current_unverified}`",
            ephemeral=True
        )

    @app_commands.command(name="sync", description="Force sync slash commands (bot owner or admin)")
    @app_commands.describe(scope="Sync globally or just this server")
    @app_commands.choices(scope=[
        app_commands.Choice(name="Global (all servers)", value="global"),
        app_commands.Choice(name="This server only", value="guild")
    ])
    @app_commands.default_permissions(administrator=True)
    async def sync_commands(self, interaction: discord.Interaction, scope: app_commands.Choice[str] = None):
        """Allow admins to trigger a slash-command sync without restarting."""
        # Only allow in DMs if scope is global; guild-scoped sync requires context.
        if scope and scope.value == "guild" and not interaction.guild:
            await interaction.response.send_message(
                "❌ Guild-only sync must be run inside the server.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        tree = interaction.client.tree
        try:
            if scope and scope.value == "guild":
                synced = await tree.sync(guild=interaction.guild)
                await interaction.followup.send(
                    f"✅ Synced {len(synced)} command(s) for **{interaction.guild.name}**.",
                    ephemeral=True
                )
            else:
                synced = await tree.sync()
                await interaction.followup.send(
                    f"✅ Globally synced {len(synced)} command(s).",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Failed to sync commands: {e}",
                ephemeral=True
            )

    @app_commands.command(name="command_ban", description="Ban a user from using a command (echo or tts)")
    @app_commands.describe(
        user="User to ban (optional if message_link provided)",
        command="Command to ban",
        reason="Optional reason for the ban",
        message_link="Optional message link; will ban the author of that message"
    )
    @app_commands.choices(command=[
        app_commands.Choice(name="Echo", value="echo"),
        app_commands.Choice(name="TTS", value="tts"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def command_ban(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None,
        command: app_commands.Choice[str] = None,
        reason: str = None,
        message_link: str = None
    ):
        """Prevent a member from using echo or TTS commands in this server."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
        if command is None:
            await interaction.response.send_message("❌ Choose a command to ban (echo or tts).", ephemeral=True)
            return

        target_member = user
        # If a message link is provided, resolve the author of that message
        if message_link:
            try:
                parts = [p for p in message_link.split('/') if p]
                guild_id_str, channel_id_str, message_id_str = parts[-3:]
                link_guild_id = int(guild_id_str)
                channel_id = int(channel_id_str)
                message_id = int(message_id_str)
            except Exception:
                await interaction.response.send_message("❌ Invalid message link format.", ephemeral=True)
                return

            if link_guild_id != interaction.guild.id:
                await interaction.response.send_message("❌ The message link is for a different server.", ephemeral=True)
                return

            channel = interaction.client.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await interaction.client.fetch_channel(channel_id)
                except Exception:
                    channel = None

            if channel is None or getattr(channel, "guild", None) != interaction.guild:
                await interaction.response.send_message("❌ Could not access that channel in this server.", ephemeral=True)
                return

            try:
                message = await channel.fetch_message(message_id)
            except Exception:
                await interaction.response.send_message("❌ Could not fetch that message.", ephemeral=True)
                return

            target_member = interaction.guild.get_member(message.author.id)
            if target_member is None:
                try:
                    target_member = await interaction.guild.fetch_member(message.author.id)
                except Exception:
                    target_member = None

        if target_member is None:
            await interaction.response.send_message("❌ Provide a user or a valid message link to ban the author.", ephemeral=True)
            return

        db.ban_user_for_command(interaction.guild.id, target_member.id, command.value, reason or "", interaction.user.id)
        await interaction.response.send_message(
            f"✅ Banned {target_member.display_name} from using {command.value} in this server.",
            ephemeral=True
        )

    @app_commands.command(name="command_unban", description="Remove a command ban for a user")
    @app_commands.describe(user="User to unban", command="Command to unban")
    @app_commands.choices(command=[
        app_commands.Choice(name="Echo", value="echo"),
        app_commands.Choice(name="TTS", value="tts"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def command_unban(self, interaction: discord.Interaction, user: discord.Member, command: app_commands.Choice[str]):
        """Remove a member's echo or TTS ban in this server."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        db.unban_user_for_command(interaction.guild.id, user.id, command.value)
        await interaction.response.send_message(
            f"✅ Unbanned {user.display_name} for {command.value} in this server.",
            ephemeral=True
        )

    @app_commands.command(name="command_disable", description="Disable a command in this server")
    @app_commands.describe(command="Command to disable")
    @app_commands.choices(command=[
        app_commands.Choice(name="Echo", value="echo"),
        app_commands.Choice(name="TTS", value="tts"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def command_disable(self, interaction: discord.Interaction, command: app_commands.Choice[str]):
        """Disable echo or TTS for everyone in this server."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        db.set_command_enabled(interaction.guild.id, command.value, False)
        await interaction.response.send_message(
            f"✅ Disabled {command.value} in this server.",
            ephemeral=True
        )

    @app_commands.command(name="command_enable", description="Enable a command in this server")
    @app_commands.describe(command="Command to enable")
    @app_commands.choices(command=[
        app_commands.Choice(name="Echo", value="echo"),
        app_commands.Choice(name="TTS", value="tts"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def command_enable(self, interaction: discord.Interaction, command: app_commands.Choice[str]):
        """Enable echo or TTS for everyone in this server."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        db.set_command_enabled(interaction.guild.id, command.value, True)
        await interaction.response.send_message(
            f"✅ Enabled {command.value} in this server.",
            ephemeral=True
        )

    @app_commands.command(name="sql", description="Execute a SQL query (BOT OWNER ONLY)")
    @app_commands.describe(query="The SQL query to execute")
    async def execute_sql(self, interaction: discord.Interaction, query: str):
        """Execute a SQL query on the database (BOT OWNER ONLY)"""
        # Check if user is the bot owner
        app_info = await interaction.client.application_info()
        if interaction.user.id != app_info.owner.id:
            await interaction.response.send_message(
                "❌ This command is restricted to the bot owner only.",
                ephemeral=True
            )
            return
        
        # Defer response since query might take time
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Log the query execution
            logger.info(f"🔍 SQL Query executed by {interaction.user} (ID: {interaction.user.id}):")
            logger.info(f"   Query: {query}")
            
            # Determine if this is a SELECT query or a modification query
            is_select = query.strip().upper().startswith('SELECT')
            
            if is_select:
                # Execute SELECT query and fetch results
                results = db.execute_query(query)
                
                if not results:
                    await interaction.followup.send("✅ Query executed successfully. No results returned.", ephemeral=True)
                    return
                
                # Format results as a table
                response = f"✅ Query returned {len(results)} row(s):\n```\n"
                
                # Limit output to prevent message from being too long
                max_rows = 20
                for i, row in enumerate(results[:max_rows]):
                    response += f"{i+1}. {row}\n"
                
                if len(results) > max_rows:
                    response += f"... and {len(results) - max_rows} more row(s)\n"
                
                response += "```"
                
                # Discord message limit is 2000 characters
                if len(response) > 1900:
                    response = response[:1900] + "\n...\n```\n⚠️ Output truncated due to length"
                
                await interaction.followup.send(response, ephemeral=True)
            else:
                # Execute modification query (INSERT, UPDATE, DELETE, etc.)
                db.execute_query(query, fetch=False)
                await interaction.followup.send("✅ Query executed successfully.", ephemeral=True)
            
            logger.info("   ✅ Query completed successfully")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"   ❌ Query failed: {error_msg}")
            await interaction.followup.send(
                f"❌ Error executing query:\n```\n{error_msg[:1800]}\n```",
                ephemeral=True
            )
    

    @app_commands.command(name="tasklogs", description="View recent automated task execution logs (BOT OWNER ONLY)")
    @app_commands.describe(
        task_name="Filter by task name (optional)",
        limit="Number of logs to show (default: 10)"
    )
    async def view_task_logs(self, interaction: discord.Interaction, task_name: str = None, limit: int = 10):
        """View recent automated task execution logs (BOT OWNER ONLY)"""
        # Check if user is the bot owner
        app_info = await interaction.client.application_info()
        if interaction.user.id != app_info.owner.id:
            await interaction.response.send_message(
                "❌ This command is restricted to the bot owner only.",
                ephemeral=True
            )
            return
        
        # Defer response since query might take time
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Get task logs
            logs = db.get_recent_task_logs(task_name=task_name, limit=min(limit, 50))
            
            if not logs:
                await interaction.followup.send("📋 No task logs found.", ephemeral=True)
                return
            
            # Format logs
            response = f"📋 **Recent Task Logs** ({len(logs)} entries)\n"
            if task_name:
                response += f"Filtered by: `{task_name}`\n"
            response += "\n"
            
            for log in logs:
                status_emoji = "✅" if log['status'] == 'success' else "❌" if log['status'] == 'error' else "⏳"
                duration = ""
                if log['completed_at']:
                    delta = log['completed_at'] - log['started_at']
                    duration = f" ({delta.total_seconds():.1f}s)"
                
                response += f"{status_emoji} **{log['task_name']}**{duration}\n"
                response += f"   Started: <t:{int(log['started_at'].timestamp())}:f>\n"
                
                if log['guild_id']:
                    response += f"   Guild: {log['guild_id']}\n"
                
                if log['details']:
                    details_str = str(log['details'])[:100]
                    response += f"   Details: {details_str}\n"
                
                if log['error_message']:
                    error_str = log['error_message'][:100]
                    response += f"   Error: {error_str}\n"
                
                response += "\n"
                
                # Check message length
                if len(response) > 1800:
                    response += "... (output truncated)"
                    break
            
            await interaction.followup.send(response, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error viewing task logs: {e}")
            await interaction.followup.send(
                f"❌ Error retrieving task logs: {str(e)[:100]}",
                ephemeral=True
            )
    
    @app_commands.command(name="test_booster_role", description="Test booster role creation and positioning (BOT OWNER ONLY)")
    @app_commands.describe(
        user="User to create test role for (defaults to you)",
        cleanup="Automatically delete the test role after 10 seconds"
    )
    async def test_booster_role(self, interaction: discord.Interaction, user: discord.Member = None, cleanup: bool = True):
        """Test booster role creation and positioning without touching the database"""
        # Check if user is the bot owner
        app_info = await interaction.client.application_info()
        if interaction.user.id != app_info.owner.id:
            await interaction.response.send_message(
                "❌ This command is restricted to the bot owner only.",
                ephemeral=True
            )
            return
        
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        target_user = user or interaction.user
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Import positioning function
            from commands.booster_commands import _ensure_role_position
            
            # Create test role
            test_role = await interaction.guild.create_role(
                name=f"🧪 TEST - {target_user.display_name}",
                reason=f"Test booster role positioning (by {interaction.user})"
            )
            
            # Get initial position
            initial_position = test_role.position
            
            # Assign role to user
            try:
                await target_user.add_roles(test_role, reason=f"Test booster role positioning (by {interaction.user})")
                role_assigned = True
            except discord.Forbidden:
                role_assigned = False
                assignment_error = "Bot lacks permission to assign roles"
            except Exception as e:
                role_assigned = False
                assignment_error = str(e)
            
            # Apply positioning logic
            await _ensure_role_position(test_role, interaction.guild.me, target_user)
            
            # Get final position from API to avoid stale cache after bulk role-position edits
            fetched_roles = await interaction.guild.fetch_roles()
            refreshed_test_role = discord.utils.get(fetched_roles, id=test_role.id)
            refreshed_booster_role = discord.utils.get(
                fetched_roles,
                id=interaction.guild.premium_subscriber_role.id
            ) if interaction.guild.premium_subscriber_role else None
            final_position = refreshed_test_role.position if refreshed_test_role else test_role.position
            booster_position = refreshed_booster_role.position if refreshed_booster_role else None
            bot_top_position = interaction.guild.me.top_role.position if interaction.guild.me and interaction.guild.me.top_role else None
            expected_target = booster_position + 1 if booster_position is not None else None
            if expected_target is not None and bot_top_position is not None and expected_target >= bot_top_position:
                expected_target = bot_top_position - 1
            skipped_for_hierarchy = (
                expected_target is not None
                and bot_top_position is not None
                and expected_target >= bot_top_position
            )
            
            # Get user's highest role for comparison
            user_roles = [r for r in target_user.roles if not r.is_default() and r.id != test_role.id]
            highest_user_role = max(user_roles, key=lambda r: r.position) if user_roles else None
            
            # Build response
            response = [
                f"✅ **Booster Role Test Complete**",
                f"",
                f"**Target User:** {target_user.mention}",
                f"**Test Role:** {test_role.mention}",
                f"",
                f"**Role Assignment:**",
                f"• {'✅ Role assigned to user' if role_assigned else f'❌ Failed: {assignment_error}'}",
                f"",
                f"**Position Changes:**",
                f"• Initial: `{initial_position}` (bottom)",
                f"• Final: `{final_position}`",
                f"• Moved: `{final_position - initial_position}` positions",
                f"• Expected target (server booster): `{expected_target if expected_target is not None else 'N/A'}`",
                f"",
            ]

            if skipped_for_hierarchy:
                response.append(
                    f"⚠️ Move likely skipped: server booster target `{expected_target}` is at/above bot top role `{bot_top_position}`."
                )
                response.append("")
            
            if highest_user_role:
                response.append(f"**User's Highest Role:** {highest_user_role.mention} (position `{highest_user_role.position}`)")
                if final_position > highest_user_role.position:
                    response.append(f"✅ Test role is above user's highest role")
                else:
                    response.append(f"⚠️ Test role is NOT above user's highest role")
            else:
                response.append(f"ℹ️ User has no roles to compare against")
            
            response.append(f"")
            response.append(f"**Bot's Top Role:** {interaction.guild.me.top_role.mention} (position `{interaction.guild.me.top_role.position}`)")
            if final_position < interaction.guild.me.top_role.position:
                response.append(f"✅ Test role is below bot's top role")
            else:
                response.append(f"❌ Test role is NOT below bot's top role")
            
            if cleanup:
                response.append(f"")
                response.append(f"🧹 Test role will be deleted in 10 seconds...")
            else:
                response.append(f"")
                response.append(f"⚠️ **Manual cleanup required** - delete {test_role.mention} when done testing")
            
            await interaction.followup.send("\n".join(response), ephemeral=True)
            
            # Cleanup if requested
            if cleanup:
                await asyncio.sleep(10)
                try:
                    await test_role.delete(reason="Test booster role cleanup")
                except Exception as e:
                    logger.warning(f"Could not delete test role: {e}")
            
        except Exception as e:
            logger.error(f"Error testing booster role: {e}")
            await interaction.followup.send(
                f"❌ Error during test: {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="auditlog", description="Query audit log with SQL-like syntax")
    @app_commands.describe(
        query="SQL-like query: SELECT * WHERE action='kick' AND user='@User' LIMIT 10"
    )
    @app_commands.default_permissions(view_audit_log=True)
    async def audit_log_query(self, interaction: discord.Interaction, query: str):
        """Query the audit log using SQL-like syntax"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        if not interaction.user.guild_permissions.view_audit_log:
            await interaction.response.send_message(
                "❌ You need the View Audit Log permission to use this command.",
                ephemeral=True
            )
            return
        
        # Check if bot has view_audit_log permission
        bot_member = interaction.guild.get_member(interaction.client.user.id)
        if not bot_member.guild_permissions.view_audit_log:
            await interaction.response.send_message(
                "❌ I don't have permission to view the audit log. Please grant me the `View Audit Log` permission.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Parse SQL-like query
            parsed = self._parse_audit_query(query)
            
            if "error" in parsed:
                await interaction.followup.send(f"❌ Query error: {parsed['error']}", ephemeral=True)
                return
            
            # Build discord.py audit_logs() parameters
            audit_params = {
                'limit': parsed.get('limit', 100),
            }
            
            # Map action types
            action_map = {
                'kick': discord.AuditLogAction.kick,
                'ban': discord.AuditLogAction.ban,
                'unban': discord.AuditLogAction.unban,
                'member_update': discord.AuditLogAction.member_update,
                'member_role_update': discord.AuditLogAction.member_role_update,
                'channel_create': discord.AuditLogAction.channel_create,
                'channel_delete': discord.AuditLogAction.channel_delete,
                'channel_update': discord.AuditLogAction.channel_update,
                'role_create': discord.AuditLogAction.role_create,
                'role_delete': discord.AuditLogAction.role_delete,
                'role_update': discord.AuditLogAction.role_update,
                'message_delete': discord.AuditLogAction.message_delete,
                'message_bulk_delete': discord.AuditLogAction.message_bulk_delete,
                'message_pin': discord.AuditLogAction.message_pin,
                'message_unpin': discord.AuditLogAction.message_unpin,
            }
            
            if parsed.get('action'):
                action_key = parsed['action'].strip("'\"").lower()
                if action_key in action_map:
                    audit_params['action'] = action_map[action_key]
                else:
                    await interaction.followup.send(
                        f"❌ Unknown action type: `{parsed['action']}`\n"
                        f"Available: {', '.join(action_map.keys())}",
                        ephemeral=True
                    )
                    return
            
            user_obj = None
            if parsed.get('user_id'):
                user_obj = interaction.guild.get_member(parsed['user_id'])
            elif parsed.get('user_raw'):
                # Try name-based resolution
                user_obj = discord.utils.get(interaction.guild.members, name=parsed['user_raw'])
                if not user_obj:
                    user_obj = discord.utils.find(
                        lambda m: m.display_name.lower() == parsed['user_raw'].lower(),
                        interaction.guild.members
                    )
                if user_obj:
                    parsed['user_id'] = user_obj.id

            if user_obj:
                audit_params['user'] = user_obj

            # Resolve target by raw name if needed
            if parsed.get('target_raw') and not parsed.get('target_id'):
                raw = parsed['target_raw'].lower()
                # Try member
                member = discord.utils.find(lambda m: m.name.lower() == raw or m.display_name.lower() == raw, interaction.guild.members)
                if member:
                    parsed['target_id'] = member.id
                else:
                    # Try channel by name (text/voice/stage/forum/categories)
                    channel = discord.utils.find(lambda c: getattr(c, "name", "").lower() == raw, interaction.guild.channels)
                    if channel:
                        parsed['target_id'] = channel.id
                    else:
                        # Try role by name
                        role = discord.utils.find(lambda r: r.name.lower() == raw, interaction.guild.roles)
                        if role:
                            parsed['target_id'] = role.id
            
            # Fetch audit log entries
            entries = []
            async for entry in interaction.guild.audit_logs(**audit_params):
                # Apply filters
                if parsed.get('user_id'):
                    if not entry.user or entry.user.id != parsed['user_id']:
                        continue

                if parsed.get('target_id'):
                    if not hasattr(entry.target, 'id') or entry.target.id != parsed['target_id']:
                        continue
                
                if parsed.get('before'):
                    if entry.created_at >= parsed['before']:
                        continue
                
                if parsed.get('after'):
                    if entry.created_at <= parsed['after']:
                        continue
                
                entries.append(entry)
                
                if len(entries) >= parsed.get('limit', 100):
                    break
            
            if not entries:
                await interaction.followup.send("📋 No audit log entries found matching your query.", ephemeral=True)
                return
            
            # Format results
            embed = discord.Embed(
                title="📋 Audit Log Query Results",
                description=f"Found {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}",
                color=discord.Color.blue()
            )
            
            # Show query
            embed.add_field(
                name="🔍 Query",
                value=f"```{query[:200]}```",
                inline=False
            )
            
            # Show results (up to 10 entries)
            for i, entry in enumerate(entries[:10]):
                action_name = str(entry.action).replace('AuditLogAction.', '')
                
                user_str = entry.user.mention if entry.user else "Unknown"
                target_str = entry.target.mention if hasattr(entry.target, 'mention') else str(entry.target) if entry.target else "N/A"
                
                reason_str = entry.reason if entry.reason else "No reason provided"
                
                timestamp = f"<t:{int(entry.created_at.timestamp())}:R>"
                
                value = f"**User:** {user_str}\n**Target:** {target_str}\n**Reason:** {reason_str[:50]}\n**When:** {timestamp}"
                
                embed.add_field(
                    name=f"{i+1}. {action_name}",
                    value=value,
                    inline=False
                )
            
            if len(entries) > 10:
                embed.set_footer(text=f"Showing 10 of {len(entries)} entries. Refine your query to see specific results.")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to access the audit log.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in audit log query: {e}")
            await interaction.followup.send(
                f"❌ Error executing query: {str(e)[:200]}",
                ephemeral=True
            )
    
    def _parse_audit_query(self, query: str) -> dict:
        """Parse SQL-like query syntax for audit log filtering
        
        Syntax: SELECT * WHERE action='kick' AND user='@User' AND target='@Target' AND after='2024-01-01' LIMIT 10
        
        Returns dict with: action, user_id, target_id, before, after, limit
        """
        import re
        from datetime import datetime, timedelta
        
        result = {}
        query_upper = query.upper()
        
        # Extract LIMIT
        limit_match = re.search(r'LIMIT\s+(\d+)', query_upper)
        if limit_match:
            result['limit'] = min(int(limit_match.group(1)), 100)
        else:
            result['limit'] = 10
        
        # Extract WHERE clause
        where_match = re.search(r'WHERE\s+(.+?)(?:LIMIT|$)', query, re.IGNORECASE)
        if not where_match:
            return result
        
        where_clause = where_match.group(1).strip()
        
        # Parse conditions (simple AND-based parser)
        conditions = re.split(r'\s+AND\s+', where_clause, flags=re.IGNORECASE)
        
        for condition in conditions:
            cond = condition.strip()
            if "=" not in cond:
                continue
            key, value = cond.split("=", 1)
            key = key.strip().lower()
            value = value.strip()
            # Strip surrounding quotes if present
            if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
                value = value[1:-1]
            
            if key == 'action':
                result['action'] = value
            
            elif key == 'user':
                # Extract user ID from mention or direct ID
                user_id_match = re.search(r'<@!?(\d+)>|^(\d+)$', value)
                if user_id_match:
                    result['user_id'] = int(user_id_match.group(1) or user_id_match.group(2))
                else:
                    # Keep raw for name-based resolution later
                    result['user_raw'] = value
            
            elif key == 'target':
                # Extract target ID from mention or direct ID
                target_id_match = re.search(r'<@!?(\d+)>|<#(\d+)>|<@&(\d+)>|^(\d+)$', value)
                if target_id_match:
                    result['target_id'] = int(target_id_match.group(1) or target_id_match.group(2) or target_id_match.group(3) or target_id_match.group(4))
                else:
                    result['target_raw'] = value
            
            elif key == 'after':
                # Parse date/time
                try:
                    # Try parsing relative time (e.g., "1d", "2h", "30m")
                    relative_match = re.match(r'(\d+)([dhm])', value.lower())
                    if relative_match:
                        amount = int(relative_match.group(1))
                        unit = relative_match.group(2)
                        
                        if unit == 'd':
                            result['after'] = datetime.now() - timedelta(days=amount)
                        elif unit == 'h':
                            result['after'] = datetime.now() - timedelta(hours=amount)
                        elif unit == 'm':
                            result['after'] = datetime.now() - timedelta(minutes=amount)
                    else:
                        # Try parsing absolute date
                        result['after'] = datetime.fromisoformat(value)
                except:
                    result['error'] = f"Invalid date format for 'after': {value}"
                    return result
            
            elif key == 'before':
                # Parse date/time
                try:
                    # Try parsing relative time
                    relative_match = re.match(r'(\d+)([dhm])', value.lower())
                    if relative_match:
                        amount = int(relative_match.group(1))
                        unit = relative_match.group(2)
                        
                        if unit == 'd':
                            result['before'] = datetime.now() - timedelta(days=amount)
                        elif unit == 'h':
                            result['before'] = datetime.now() - timedelta(hours=amount)
                        elif unit == 'm':
                            result['before'] = datetime.now() - timedelta(minutes=amount)
                    else:
                        # Try parsing absolute date
                        result['before'] = datetime.fromisoformat(value)
                except:
                    result['error'] = f"Invalid date format for 'before': {value}"
                    return result
        
        return result
    
