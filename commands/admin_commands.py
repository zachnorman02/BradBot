"""
Admin command group for server and database management
"""
import discord
from discord import app_commands
from discord.ext import commands
from discord import ui
import datetime as dt
from database import db


class AdminSettingsView(ui.View):
    """Interactive admin settings view with toggle buttons"""
    
    def __init__(self, guild_id: int, persistent: bool = False):
        super().__init__(timeout=None if persistent else 180)
        self.guild_id = guild_id
        self.persistent = persistent
        self.update_buttons()
    
    def get_embed(self) -> discord.Embed:
        """Generate the settings display embed"""
        # Fetch current settings
        link_replacement = db.get_guild_setting(self.guild_id, 'link_replacement_enabled', 'true').lower() == 'true'
        verify_roles = db.get_guild_setting(self.guild_id, 'verify_roles_enabled', 'true').lower() == 'true'
        booster_roles = db.get_guild_setting(self.guild_id, 'booster_roles_enabled', 'true').lower() == 'true'
        unverified_kicks = db.get_guild_setting(self.guild_id, 'unverified_kicks_enabled', 'false').lower() == 'true'
        reply_pings = db.get_guild_setting(self.guild_id, 'reply_pings_enabled', 'true').lower() == 'true'
        member_send_pings = db.get_guild_setting(self.guild_id, 'member_send_pings_enabled', 'true').lower() == 'true'
        auto_kick_single = db.get_guild_setting(self.guild_id, 'auto_kick_single_server', 'false').lower() == 'true'
        auto_ban_single = db.get_guild_setting(self.guild_id, 'auto_ban_single_server', 'false').lower() == 'true'
        
        embed = discord.Embed(
            title="⚙️ Server Settings",
            description="Toggle server automation and features",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🔗 Link Replacement",
            value=f"{'🟢 Enabled' if link_replacement else '🔴 Disabled'}",
            inline=True
        )
        embed.add_field(
            name="✅ Verify Roles",
            value=f"{'🟢 Enabled' if verify_roles else '🔴 Disabled'}",
            inline=True
        )
        embed.add_field(
            name="💎 Booster Roles",
            value=f"{'🟢 Enabled' if booster_roles else '🔴 Disabled'}",
            inline=True
        )
        embed.add_field(
            name="👢 Unverified Kicks",
            value=f"{'🟢 Enabled' if unverified_kicks else '🔴 Disabled'}",
            inline=True
        )
        embed.add_field(
            name="🔔 Reply Pings",
            value=f"{'🟢 Enabled' if reply_pings else '🔴 Disabled'}",
            inline=True
        )
        embed.add_field(
            name="📤 Member Send Pings",
            value=f"{'🟢 Enabled' if member_send_pings else '🔴 Disabled'}",
            inline=True
        )
        embed.add_field(
            name="🦵 Auto-Kick Single Server",
            value=f"{'🟢 Enabled' if auto_kick_single else '🔴 Disabled'}",
            inline=True
        )
        embed.add_field(
            name="🔨 Auto-Ban Single Server",
            value=f"{'🟢 Enabled' if auto_ban_single else '🔴 Disabled'}",
            inline=True
        )
        
        embed.set_footer(text="Click buttons to toggle settings")
        return embed
    
    def update_buttons(self):
        """Update button styles based on current settings"""
        link_replacement = db.get_guild_setting(self.guild_id, 'link_replacement_enabled', 'true').lower() == 'true'
        verify_roles = db.get_guild_setting(self.guild_id, 'verify_roles_enabled', 'true').lower() == 'true'
        booster_roles = db.get_guild_setting(self.guild_id, 'booster_roles_enabled', 'true').lower() == 'true'
        unverified_kicks = db.get_guild_setting(self.guild_id, 'unverified_kicks_enabled', 'false').lower() == 'true'
        reply_pings = db.get_guild_setting(self.guild_id, 'reply_pings_enabled', 'true').lower() == 'true'
        member_send_pings = db.get_guild_setting(self.guild_id, 'member_send_pings_enabled', 'true').lower() == 'true'
        auto_kick_single = db.get_guild_setting(self.guild_id, 'auto_kick_single_server', 'false').lower() == 'true'
        auto_ban_single = db.get_guild_setting(self.guild_id, 'auto_ban_single_server', 'false').lower() == 'true'
        
        # Update button children
        self.children[0].style = discord.ButtonStyle.green if link_replacement else discord.ButtonStyle.gray
        self.children[0].label = "🔗 Link Replacement " + ("✓" if link_replacement else "✗")
        
        self.children[1].style = discord.ButtonStyle.green if verify_roles else discord.ButtonStyle.gray
        self.children[1].label = "✅ Verify Roles " + ("✓" if verify_roles else "✗")
        
        self.children[2].style = discord.ButtonStyle.green if booster_roles else discord.ButtonStyle.gray
        self.children[2].label = "💎 Booster Roles " + ("✓" if booster_roles else "✗")
        
        self.children[3].style = discord.ButtonStyle.green if unverified_kicks else discord.ButtonStyle.gray
        self.children[3].label = "👢 Unverified Kicks " + ("✓" if unverified_kicks else "✗")
        
        self.children[4].style = discord.ButtonStyle.green if reply_pings else discord.ButtonStyle.gray
        self.children[4].label = "🔔 Reply Pings " + ("✓" if reply_pings else "✗")
        
        self.children[5].style = discord.ButtonStyle.green if member_send_pings else discord.ButtonStyle.gray
        self.children[5].label = "📤 Member Send Pings " + ("✓" if member_send_pings else "✗")
        
        self.children[6].style = discord.ButtonStyle.green if auto_kick_single else discord.ButtonStyle.gray
        self.children[6].label = "🦵 Auto-Kick Singles " + ("✓" if auto_kick_single else "✗")
        
        self.children[7].style = discord.ButtonStyle.green if auto_ban_single else discord.ButtonStyle.gray
        self.children[7].label = "🔨 Auto-Ban Singles " + ("✓" if auto_ban_single else "✗")
    
    @ui.button(label="🔗 Link Replacement", style=discord.ButtonStyle.gray, row=0)
    async def toggle_link_replacement(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'link_replacement_enabled', 'true').lower() == 'true'
        new_value = not current
        db.set_guild_link_replacement(self.guild_id, new_value, interaction.user.id, str(interaction.user))
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="✅ Verify Roles", style=discord.ButtonStyle.gray, row=0)
    async def toggle_verify_roles(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'verify_roles_enabled', 'true').lower() == 'true'
        new_value = not current
        db.set_guild_setting(self.guild_id, 'verify_roles_enabled', 'true' if new_value else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="💎 Booster Roles", style=discord.ButtonStyle.gray, row=0)
    async def toggle_booster_roles(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'booster_roles_enabled', 'true').lower() == 'true'
        new_value = not current
        db.set_guild_setting(self.guild_id, 'booster_roles_enabled', 'true' if new_value else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="👢 Unverified Kicks", style=discord.ButtonStyle.gray, row=1)
    async def toggle_unverified_kicks(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'unverified_kicks_enabled', 'false').lower() == 'true'
        new_value = not current
        db.set_guild_setting(self.guild_id, 'unverified_kicks_enabled', 'true' if new_value else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="🔔 Reply Pings", style=discord.ButtonStyle.gray, row=1)
    async def toggle_reply_pings(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'reply_pings_enabled', 'true').lower() == 'true'
        new_value = not current
        db.set_guild_setting(self.guild_id, 'reply_pings_enabled', 'true' if new_value else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="📤 Member Send Pings", style=discord.ButtonStyle.gray, row=1)
    async def toggle_member_send_pings(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'member_send_pings_enabled', 'true').lower() == 'true'
        new_value = not current
        db.set_guild_setting(self.guild_id, 'member_send_pings_enabled', 'true' if new_value else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="🦵 Auto-Kick Singles", style=discord.ButtonStyle.gray, row=2)
    async def toggle_auto_kick_single(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'auto_kick_single_server', 'false').lower() == 'true'
        new_value = not current
        db.set_guild_setting(self.guild_id, 'auto_kick_single_server', 'true' if new_value else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="🔨 Auto-Ban Singles", style=discord.ButtonStyle.gray, row=2)
    async def toggle_auto_ban_single(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'auto_ban_single_server', 'false').lower() == 'true'
        new_value = not current
        db.set_guild_setting(self.guild_id, 'auto_ban_single_server', 'true' if new_value else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="🔄 Refresh Panel", style=discord.ButtonStyle.blurple, row=2)
    async def refresh_panel(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)


class AdminToolsGroup(app_commands.Group):
    """Database and role management tools"""
    
    def __init__(self):
        super().__init__(name="tools", description="Database and role management tools")
    
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
                            print(f"Could not read icon for {member.display_name}: {e}")
                    
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
                    print(f"Error saving role for {member.display_name}: {e}")
            
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
            print(f"Error loading booster roles: {e}")
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
                    print(f"Could not read icon for role {role.name}: {e}")
            
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
            print(f"Error saving booster role: {e}")
            await interaction.followup.send(
                f"❌ An error occurred while saving the booster role: {str(e)[:100]}",
                ephemeral=True
            )

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
            db.init_role_rules_table()
            
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
            print(f"Error in autorole command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="channelrestriction", description="Configure channel access restrictions based on roles")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        action="What action to perform",
        channel="The channel to restrict access to",
        blocking_role="Role that blocks access to the channel",
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="add - Block role from viewing channel", value="add"),
        app_commands.Choice(name="remove - Remove channel restriction", value="remove"),
        app_commands.Choice(name="list - Show all channel restrictions", value="list"),
        app_commands.Choice(name="apply-all - Apply restrictions to all current members", value="apply-all")
    ])
    async def channel_restriction(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        channel: discord.TextChannel = None,
        blocking_role: discord.Role = None
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
            db.init_channel_restrictions_table()
            
            if action.value == "list":
                restrictions = db.get_channel_restrictions(interaction.guild.id)
                
                if not restrictions:
                    await interaction.followup.send("📋 No channel restrictions configured for this server.", ephemeral=True)
                    return
                
                embed = discord.Embed(
                    title="🔒 Channel Restrictions",
                    description=f"Found {len(restrictions)} restriction(s)",
                    color=discord.Color.blue()
                )
                
                # Group by channel
                from collections import defaultdict
                by_channel = defaultdict(list)
                for r in restrictions:
                    by_channel[r['channel_id']].append(r)
                
                for channel_id, channel_restrictions in by_channel.items():
                    channel_obj = interaction.guild.get_channel(channel_id)
                    channel_name = channel_obj.mention if channel_obj else f"Unknown Channel ({channel_id})"
                    
                    role_mentions = []
                    for r in channel_restrictions:
                        role = interaction.guild.get_role(r['blocking_role_id'])
                        role_mentions.append(role.mention if role else f"Unknown ({r['blocking_role_id']})")
                    
                    embed.add_field(
                        name=f"🔒 {channel_obj.name if channel_obj else 'Unknown'}",
                        value=f"**Channel:** {channel_name}\n**Blocked Roles:** {', '.join(role_mentions)}",
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            elif action.value == "remove":
                if not channel or not blocking_role:
                    await interaction.followup.send("❌ Please specify both channel and blocking_role for remove action.", ephemeral=True)
                    return
                
                db.remove_channel_restriction(interaction.guild.id, channel.id, blocking_role.id)
                await interaction.followup.send(
                    f"✅ Removed channel restriction\n"
                    f"• Channel: {channel.mention}\n"
                    f"• Blocking Role: {blocking_role.mention}",
                    ephemeral=True
                )
                return
            
            elif action.value == "add":
                if not channel or not blocking_role:
                    await interaction.followup.send("❌ Please specify both channel and blocking_role for add action.", ephemeral=True)
                    return
                
                # Save to database
                db.add_channel_restriction(interaction.guild.id, channel.id, blocking_role.id)
                
                await interaction.followup.send(
                    f"✅ Added channel restriction\n"
                    f"• Channel: {channel.mention}\n"
                    f"• Blocking Role: {blocking_role.mention}\n\n"
                    f"Members with {blocking_role.mention} will be blocked from viewing {channel.mention}.\n"
                    f"Use `apply-all` action to apply this to existing members.",
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
                    by_channel[r['channel_id']].append(r['blocking_role_id'])
                
                # Process each channel
                for channel_id, blocking_role_ids in by_channel.items():
                    channel_obj = interaction.guild.get_channel(channel_id)
                    if not channel_obj:
                        results['errors'].append(f"Channel {channel_id} not found")
                        continue
                    
                    # Check each member
                    for member in interaction.guild.members:
                        if member.bot:
                            continue
                        
                        member_role_ids = {r.id for r in member.roles}
                        has_blocking_role = any(rid in member_role_ids for rid in blocking_role_ids)
                        
                        try:
                            if has_blocking_role:
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
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
        
        except Exception as e:
            print(f"Error in channelrestriction command: {e}")
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
        user_required_actions = ["mark", "unmark", "check", "assign"]
        if action_value in user_required_actions and not user:
            await interaction.followup.send(f"❌ Please specify a user for the {action_value} action.", ephemeral=True)
            return
        
        try:
            if not db.connection_pool:
                db.init_pool()
            
            # Ensure tables exist
            db.init_conditional_roles_tables()
            
            # ================================================================
            # CONFIGURATION ACTIONS
            # ================================================================
            
            if action_value == "list_configs":
                configs = db.get_all_conditional_role_configs(interaction.guild.id)
                
                if not configs:
                    await interaction.followup.send("📋 No conditional roles configured for this server.", ephemeral=True)
                    return
                
                embed = discord.Embed(
                    title="⚙️ Conditional Role Configurations",
                    description=f"Found {len(configs)} configured role(s)",
                    color=discord.Color.blue()
                )
                
                for config in configs:
                    role_obj = interaction.guild.get_role(config['role_id'])
                    role_mention = role_obj.mention if role_obj else f"<@&{config['role_id']}> (deleted)"
                    
                    blocking_mentions = []
                    for blocking_id in config['blocking_role_ids']:
                        blocking_role = interaction.guild.get_role(blocking_id)
                        blocking_mentions.append(blocking_role.mention if blocking_role else f"<@&{blocking_id}> (deleted)")
                    
                    blocking_text = ", ".join(blocking_mentions) if blocking_mentions else "None"
                    
                    deferral_mentions = []
                    for deferral_id in config.get('deferral_role_ids', []):
                        deferral_role = interaction.guild.get_role(deferral_id)
                        deferral_mentions.append(deferral_role.mention if deferral_role else f"<@&{deferral_id}> (deleted)")
                    
                    deferral_text = ", ".join(deferral_mentions) if deferral_mentions else "None"
                    
                    embed.add_field(
                        name=f"🔒 {config.get('role_name', 'Unknown')}",
                        value=f"**Role:** {role_mention}\n**Blocking Roles:** {blocking_text}\n**Deferral Roles:** {deferral_text}",
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
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
                            deferral_role_ids = config.get('deferral_role_ids', [])
                            
                            member_role_ids = {r.id for r in member.roles}
                            has_conditional_role = conditional_role_id in member_role_ids
                            has_deferral_role = any(dr_id in member_role_ids for dr_id in deferral_role_ids)
                            
                            # Check eligibility
                            eligibility = db.get_conditional_role_eligibility(
                                interaction.guild.id,
                                member.id,
                                conditional_role_id
                            )
                            is_deferred = bool(eligibility)  # If in table, they're deferred
                            
                            conditional_role = interaction.guild.get_role(conditional_role_id)
                            role_name = conditional_role.name if conditional_role else f"Role {conditional_role_id}"
                            
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
                            elif is_deferred and not has_deferral_role and not has_conditional_role and deferral_role_ids:
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
                
                if is_eligible:
                    await interaction.followup.send(f"✅ {user.mention} is eligible for {role.mention}.", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ {user.mention} is NOT eligible for {role.mention}.", ephemeral=True)
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
            print(f"Error in conditionalrole command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)


class AdminMaintenanceGroup(app_commands.Group):
    """Server maintenance and moderation tools"""
    
    def __init__(self):
        super().__init__(name="maintenance", description="Server maintenance and moderation tools")

    @app_commands.command(name="assignlvl0", description="Assign lvl 0 to all verified members without a level role")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def assign_lvl0(self, interaction: discord.Interaction):
        """Assign lvl 0 role to verified members who don't have any level role"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get role objects
            verified_role = discord.utils.get(interaction.guild.roles, name="verified")
            lvl0_role = discord.utils.get(interaction.guild.roles, name="lvl 0")
            
            if not verified_role:
                await interaction.followup.send("❌ No 'verified' role found in this server.", ephemeral=True)
                return
            
            if not lvl0_role:
                await interaction.followup.send("❌ No 'lvl 0' role found in this server.", ephemeral=True)
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
                    has_lvl_role = any(role.name.startswith("lvl ") for role in member.roles)
                    
                    if not has_lvl_role:
                        # They need lvl 0
                        try:
                            await member.add_roles(lvl0_role, reason=f"Manual lvl 0 assignment by {interaction.user}")
                            assigned_count += 1
                            print(f"[ADMIN] Assigned lvl 0 to {member.display_name}")
                        except Exception as e:
                            error_msg = f"{member.display_name}: {str(e)[:50]}"
                            errors.append(error_msg)
                            print(f"[ADMIN] Error assigning lvl 0 to {member.display_name}: {e}")
            
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
            print(f"[ADMIN] Error in assign_lvl0 command: {e}")
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
            # Get role objects
            unverified_role = discord.utils.get(interaction.guild.roles, name="unverified")
            
            if not unverified_role:
                await interaction.followup.send("❌ No 'unverified' role found in this server.", ephemeral=True)
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
                            print(f"[ADMIN] Skipped {member.display_name} (in verification ticket)")
                        else:
                            # Kick the member (or add to dry run list)
                            if dry_run:
                                kick_list.append(f"{member.display_name} ({member.mention}) - {days_since_join} days")
                                kicked_count += 1
                            else:
                                try:
                                    await member.kick(reason=f"Kicked by {interaction.user}: Unverified for {days_since_join} days with no active verification ticket")
                                    kicked_count += 1
                                    print(f"[ADMIN] Kicked {member.display_name} (unverified for {days_since_join} days)")
                                except Exception as e:
                                    error_msg = f"{member.display_name}: {str(e)[:50]}"
                                    errors.append(error_msg)
                                    print(f"[ADMIN] Error kicking {member.display_name}: {e}")
            
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
            print(f"[ADMIN] Error in kick_unverified command: {e}")
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)[:200]}",
                ephemeral=True
            )



class AdminGroup(app_commands.Group):
    """Admin commands for server management"""
    
    def __init__(self):
        super().__init__(name="admin", description="Admin server management commands")
        
        # Add subgroups
        self.tools = AdminToolsGroup()
        self.maintenance = AdminMaintenanceGroup()
        
        self.add_command(self.tools)
        self.add_command(self.maintenance)
        # Note: Toggle commands removed - use /admin menu or /admin panel instead
    
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
            print(f"Error opening admin menu: {e}")
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
            
            view = AdminSettingsView(interaction.guild.id, persistent=True)
            
            # Send the persistent panel to the channel
            await interaction.channel.send(
                embed=view.get_embed(),
                view=view
            )
            
            # Confirm to the admin
            await interaction.response.send_message(
                "✅ Persistent admin panel created! Anyone with administrator permissions can use it.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error creating admin panel: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while creating the admin panel.",
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
            print(f"🔍 SQL Query executed by {interaction.user} (ID: {interaction.user.id}):")
            print(f"   Query: {query}")
            
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
            
            print(f"   ✅ Query completed successfully")
            
        except Exception as e:
            error_msg = str(e)
            print(f"   ❌ Query failed: {error_msg}")
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
            print(f"Error viewing task logs: {e}")
            await interaction.followup.send(
                f"❌ Error retrieving task logs: {str(e)[:100]}",
                ephemeral=True
            )
    
