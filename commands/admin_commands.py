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
    
    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id
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
        current = db.get_guild_setting(self.guild_id, 'link_replacement_enabled', 'true').lower() == 'true'
        new_value = not current
        db.set_guild_link_replacement(self.guild_id, new_value, interaction.user.id, str(interaction.user))
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="✅ Verify Roles", style=discord.ButtonStyle.gray, row=0)
    async def toggle_verify_roles(self, interaction: discord.Interaction, button: ui.Button):
        current = db.get_guild_setting(self.guild_id, 'verify_roles_enabled', 'true').lower() == 'true'
        new_value = not current
        db.set_guild_setting(self.guild_id, 'verify_roles_enabled', 'true' if new_value else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="💎 Booster Roles", style=discord.ButtonStyle.gray, row=0)
    async def toggle_booster_roles(self, interaction: discord.Interaction, button: ui.Button):
        current = db.get_guild_setting(self.guild_id, 'booster_roles_enabled', 'true').lower() == 'true'
        new_value = not current
        db.set_guild_setting(self.guild_id, 'booster_roles_enabled', 'true' if new_value else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="👢 Unverified Kicks", style=discord.ButtonStyle.gray, row=1)
    async def toggle_unverified_kicks(self, interaction: discord.Interaction, button: ui.Button):
        current = db.get_guild_setting(self.guild_id, 'unverified_kicks_enabled', 'false').lower() == 'true'
        new_value = not current
        db.set_guild_setting(self.guild_id, 'unverified_kicks_enabled', 'true' if new_value else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="🔔 Reply Pings", style=discord.ButtonStyle.gray, row=1)
    async def toggle_reply_pings(self, interaction: discord.Interaction, button: ui.Button):
        current = db.get_guild_setting(self.guild_id, 'reply_pings_enabled', 'true').lower() == 'true'
        new_value = not current
        db.set_guild_setting(self.guild_id, 'reply_pings_enabled', 'true' if new_value else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="📤 Member Send Pings", style=discord.ButtonStyle.gray, row=1)
    async def toggle_member_send_pings(self, interaction: discord.Interaction, button: ui.Button):
        current = db.get_guild_setting(self.guild_id, 'member_send_pings_enabled', 'true').lower() == 'true'
        new_value = not current
        db.set_guild_setting(self.guild_id, 'member_send_pings_enabled', 'true' if new_value else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="🦵 Auto-Kick Singles", style=discord.ButtonStyle.gray, row=2)
    async def toggle_auto_kick_single(self, interaction: discord.Interaction, button: ui.Button):
        current = db.get_guild_setting(self.guild_id, 'auto_kick_single_server', 'false').lower() == 'true'
        new_value = not current
        db.set_guild_setting(self.guild_id, 'auto_kick_single_server', 'true' if new_value else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="🔨 Auto-Ban Singles", style=discord.ButtonStyle.gray, row=2)
    async def toggle_auto_ban_single(self, interaction: discord.Interaction, button: ui.Button):
        current = db.get_guild_setting(self.guild_id, 'auto_ban_single_server', 'false').lower() == 'true'
        new_value = not current
        db.set_guild_setting(self.guild_id, 'auto_ban_single_server', 'true' if new_value else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)


class AdminGroup(app_commands.Group):
    """Admin commands for database management"""
    
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
    
    @app_commands.command(name="linkreplacement", description="Toggle automatic link replacement for this server")
    @app_commands.describe(enabled="Enable or disable automatic link replacement")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable link replacement", value=1),
        app_commands.Choice(name="Disable link replacement", value=0)
    ])
    @app_commands.default_permissions(administrator=True)
    async def link_replacement(self, interaction: discord.Interaction, enabled: int):
        """Toggle link replacement for the server (requires administrator permission)"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Update guild setting
            db.set_guild_link_replacement(
                guild_id=interaction.guild.id,
                enabled=bool(enabled),
                changed_by_user_id=interaction.user.id,
                changed_by_username=str(interaction.user)
            )
            
            status = "**enabled** ✅" if enabled else "**disabled** 🔕"
            await interaction.response.send_message(
                f"Link replacement {status}\n"
                f"The bot will {'now automatically fix' if enabled else 'no longer fix'} social media links "
                f"(Twitter/X, TikTok, Instagram, Reddit, etc.) in this server.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error updating link replacement setting: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating the link replacement setting. Please try again later.",
                ephemeral=True
            )
    
    @app_commands.command(name="verifyroles", description="Toggle automatic verified/lvl 0 role management for this server")
    @app_commands.describe(enabled="Enable or disable automatic verified role management")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable verified role automation", value=1),
        app_commands.Choice(name="Disable verified role automation", value=0)
    ])
    @app_commands.default_permissions(administrator=True)
    async def verify_roles(self, interaction: discord.Interaction, enabled: int):
        """Toggle verified/lvl 0 role automation for the server (requires administrator permission)"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Update guild setting
            db.set_guild_setting(
                guild_id=interaction.guild.id,
                setting_name='verify_roles_enabled',
                setting_value='true' if enabled else 'false'
            )
            
            status = "**enabled** ✅" if enabled else "**disabled** 🔕"
            await interaction.response.send_message(
                f"Verified role automation {status}\n"
                f"The bot will {'now automatically' if enabled else 'no longer'}:\n"
                f"• Remove 'unverified' role when 'verified' role is added\n"
                f"• Assign 'lvl 0' to verified members without a level role\n"
                f"• Remove 'lvl 0' when members gain a higher level role",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error updating verify roles setting: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating the verify roles setting. Please try again later.",
                ephemeral=True
            )
    
    @app_commands.command(name="boosterroles", description="Toggle automatic booster role creation/restoration for this server")
    @app_commands.describe(enabled="Enable or disable automatic booster role management")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable booster role automation", value=1),
        app_commands.Choice(name="Disable booster role automation", value=0)
    ])
    @app_commands.default_permissions(administrator=True)
    async def booster_roles(self, interaction: discord.Interaction, enabled: int):
        """Toggle booster role automation for the server (requires administrator permission)"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Update guild setting
            db.set_guild_setting(
                guild_id=interaction.guild.id,
                setting_name='booster_roles_enabled',
                setting_value='true' if enabled else 'false'
            )
            
            status = "**enabled** ✅" if enabled else "**disabled** 🔕"
            await interaction.response.send_message(
                f"Booster role automation {status}\n"
                f"The bot will {'now automatically' if enabled else 'no longer'}:\n"
                f"• Create/restore custom roles when members start boosting\n"
                f"• Save role configurations when members stop boosting\n"
                f"• Manage booster role persistence",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error updating booster roles setting: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating the booster roles setting. Please try again later.",
                ephemeral=True
            )
    
    @app_commands.command(name="unverifiedkicks", description="Toggle automatic 30-day unverified user kicks for this server")
    @app_commands.describe(enabled="Enable or disable automatic unverified user kicks")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable unverified kicks", value=1),
        app_commands.Choice(name="Disable unverified kicks", value=0)
    ])
    @app_commands.default_permissions(administrator=True)
    async def unverified_kicks(self, interaction: discord.Interaction, enabled: int):
        """Toggle automatic unverified user kicks for the server (requires administrator permission)"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Update guild setting
            db.set_guild_setting(
                guild_id=interaction.guild.id,
                setting_name='unverified_kicks_enabled',
                setting_value='true' if enabled else 'false'
            )
            
            status = "**enabled** ✅" if enabled else "**disabled** 🔕"
            await interaction.response.send_message(
                f"Unverified user kicks {status}\n"
                f"The bot will {'now automatically' if enabled else 'no longer'}:\n"
                f"• Kick users with 'unverified' role after 30 days\n"
                f"• Skip users in active verification tickets\n"
                f"• Run checks daily at midnight UTC",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error updating unverified kicks setting: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating the unverified kicks setting. Please try again later.",
                ephemeral=True
            )
    
    @app_commands.command(name="replypings", description="Toggle reply ping notifications for this server")
    @app_commands.describe(enabled="Enable or disable reply ping notifications")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable reply pings", value=1),
        app_commands.Choice(name="Disable reply pings", value=0)
    ])
    @app_commands.default_permissions(administrator=True)
    async def reply_pings(self, interaction: discord.Interaction, enabled: int):
        """Toggle reply ping notifications for the server (requires administrator permission)"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Update guild setting
            db.set_guild_setting(
                guild_id=interaction.guild.id,
                setting_name='reply_pings_enabled',
                setting_value='true' if enabled else 'false'
            )
            
            status = "**enabled** ✅" if enabled else "**disabled** 🔕"
            await interaction.response.send_message(
                f"Reply ping notifications {status}\n"
                f"The bot will {'now' if enabled else 'no longer'} send ping notifications when:\n"
                f"• Someone replies to a bot message\n"
                f"• The original user has reply notifications enabled\n"
                f"• The replier is not the original user\n\n"
                f"ℹ️ Users can still control their own notification preferences with `/settings notify` and `/settings sendpings`",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error updating reply pings setting: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating the reply pings setting. Please try again later.",
                ephemeral=True
            )
    
    @app_commands.command(name="membersendpings", description="Toggle whether members' replies can trigger pings in this server")
    @app_commands.describe(enabled="Enable or disable members sending reply pings")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable (members can trigger pings)", value=1),
        app_commands.Choice(name="Disable (members can't trigger pings)", value=0)
    ])
    @app_commands.default_permissions(administrator=True)
    async def member_send_pings(self, interaction: discord.Interaction, enabled: int):
        """Toggle whether members can trigger reply pings in this server (requires administrator permission)"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Update guild setting
            db.set_guild_setting(
                guild_id=interaction.guild.id,
                setting_name='member_send_pings_enabled',
                setting_value='true' if enabled else 'false'
            )
            
            status = "**enabled** ✅" if enabled else "**disabled** 🔕"
            await interaction.response.send_message(
                f"Members sending reply pings {status}\n"
                f"Members in this server {'can now' if enabled else 'can no longer'} trigger ping notifications when replying to bot messages.\n\n"
                f"ℹ️ Individual users can still control whether they send pings with `/settings sendpings`\n"
                f"⚠️ This setting overrides individual user preferences when disabled",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error updating member send pings setting: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating the member send pings setting. Please try again later.",
                ephemeral=True
            )
    
    @app_commands.command(name="autokicksingle", description="Toggle auto-kick for members only in this server with the bot")
    @app_commands.describe(enabled="Enable or disable auto-kick for single-server members")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable auto-kick", value=1),
        app_commands.Choice(name="Disable auto-kick", value=0)
    ])
    @app_commands.default_permissions(administrator=True)
    async def auto_kick_single(self, interaction: discord.Interaction, enabled: int):
        """Toggle auto-kick for members who share only this server with the bot (requires administrator permission)"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Update guild setting
            db.set_guild_setting(
                guild_id=interaction.guild.id,
                setting_name='auto_kick_single_server',
                setting_value='true' if enabled else 'false'
            )
            
            status = "**enabled** ✅" if enabled else "**disabled** 🔕"
            await interaction.response.send_message(
                f"Auto-kick single-server members {status}\n"
                f"The bot will {'now automatically kick' if enabled else 'no longer kick'} members who join and are only in this server with the bot.\n\n"
                f"⚠️ Use this feature to prevent spam/raid accounts that only join one server.\n"
                f"⚠️ This cannot be used with auto-ban enabled for the same setting.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error updating auto-kick single server setting: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating the auto-kick setting. Please try again later.",
                ephemeral=True
            )
    
    @app_commands.command(name="autobansingle", description="Toggle auto-ban for members only in this server with the bot")
    @app_commands.describe(enabled="Enable or disable auto-ban for single-server members")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable auto-ban", value=1),
        app_commands.Choice(name="Disable auto-ban", value=0)
    ])
    @app_commands.default_permissions(administrator=True)
    async def auto_ban_single(self, interaction: discord.Interaction, enabled: int):
        """Toggle auto-ban for members who share only this server with the bot (requires administrator permission)"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Update guild setting
            db.set_guild_setting(
                guild_id=interaction.guild.id,
                setting_name='auto_ban_single_server',
                setting_value='true' if enabled else 'false'
            )
            
            status = "**enabled** ✅" if enabled else "**disabled** 🔕"
            await interaction.response.send_message(
                f"Auto-ban single-server members {status}\n"
                f"The bot will {'now automatically ban' if enabled else 'no longer ban'} members who join and are only in this server with the bot.\n\n"
                f"⚠️ Use this feature to prevent spam/raid accounts that only join one server.\n"
                f"⚠️ This is more severe than auto-kick and prevents rejoining.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error updating auto-ban single server setting: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating the auto-ban setting. Please try again later.",
                ephemeral=True
            )
            await interaction.response.send_message(
                "❌ An error occurred while updating the member send pings setting. Please try again later.",
                ephemeral=True
            )
    
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

