"""
Settings command group for user preferences
"""
import discord
from discord import app_commands
from discord.ext import commands
from database import db


class SettingsView(discord.ui.View):
    """Interactive view for user settings"""
    
    def __init__(self, user_id: int, guild_id: int = None):
        super().__init__(timeout=180)  # 3 minute timeout
        self.user_id = user_id
        self.guild_id = guild_id
        self.update_buttons()
    
    def update_buttons(self):
        """Update button states based on current settings"""
        try:
            # Get current settings
            send_pings = db.get_user_setting(self.user_id, self.guild_id, 'send_reply_pings', True)
            receive_pings = db.get_user_reply_notifications(self.user_id, self.guild_id)
            if receive_pings is None:
                receive_pings = True
            
            # Update button labels to show current state
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    if item.custom_id == 'toggle_send_pings':
                        item.label = "Enabled ✓" if send_pings else "Disabled"
                        item.style = discord.ButtonStyle.success if send_pings else discord.ButtonStyle.secondary
                    elif item.custom_id == 'toggle_receive_pings':
                        item.label = "Enabled ✓" if receive_pings else "Disabled"
                        item.style = discord.ButtonStyle.success if receive_pings else discord.ButtonStyle.secondary
                    elif item.custom_id == 'toggle_scope':
                        # Update scope toggle button label
                        item.label = "Switch to This Server" if self.guild_id is None else "Switch to All Servers"
        except Exception as e:
            print(f"Error updating buttons: {e}")
    
    def get_embed(self) -> discord.Embed:
        """Generate the settings embed"""
        try:
            send_pings = db.get_user_setting(self.user_id, self.guild_id, 'send_reply_pings', True)
            receive_pings = db.get_user_reply_notifications(self.user_id, self.guild_id)
            if receive_pings is None:
                receive_pings = True
            
            embed = discord.Embed(
                title="⚙️ Settings",
                description="Configure your BradBot preferences",
                color=discord.Color.blue()
            )
            
            # Send pings setting
            send_status = "🟢 Enabled" if send_pings else "🔴 Disabled"
            embed.add_field(
                name="Send Reply Pings",
                value=f"{send_status}\nYour replies {'will' if send_pings else 'will not'} ping the original poster",
                inline=False
            )
            
            # Receive pings setting
            receive_status = "🟢 Enabled" if receive_pings else "🔴 Disabled"
            embed.add_field(
                name="Receive Reply Notifications",
                value=f"{receive_status}\nYou {'will' if receive_pings else 'will not'} be notified when others reply to your messages",
                inline=False
            )
            
            scope = "this server" if self.guild_id else "all servers"
            embed.set_footer(text=f"Settings apply to {scope}")
            
            return embed
        except Exception as e:
            print(f"Error generating embed: {e}")
            return discord.Embed(
                title="⚙️ Settings",
                description="Error loading settings",
                color=discord.Color.red()
            )
    
    @discord.ui.button(label="Enabled ✓", style=discord.ButtonStyle.success, custom_id="toggle_send_pings", row=0)
    async def toggle_send_pings(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle send pings setting"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ These are not your settings!", ephemeral=True)
            return
        
        try:
            # Get current value and toggle it
            current = db.get_user_setting(self.user_id, self.guild_id, 'send_reply_pings', True)
            new_value = not current
            
            db.set_user_setting(
                user_id=self.user_id,
                guild_id=self.guild_id,
                setting_name='send_reply_pings',
                enabled=new_value
            )
            
            # Update view
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        except Exception as e:
            print(f"Error toggling send pings: {e}")
            await interaction.response.send_message("❌ An error occurred", ephemeral=True)
    
    @discord.ui.button(label="Enabled ✓", style=discord.ButtonStyle.success, custom_id="toggle_receive_pings", row=1)
    async def toggle_receive_pings(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle receive pings setting"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ These are not your settings!", ephemeral=True)
            return
        
        try:
            # Get current value and toggle it
            current = db.get_user_reply_notifications(self.user_id, self.guild_id)
            if current is None:
                current = True
            new_value = not current
            
            db.set_user_reply_notifications(
                user_id=self.user_id,
                guild_id=self.guild_id,
                enabled=new_value
            )
            
            # Update view
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        except Exception as e:
            print(f"Error toggling receive pings: {e}")
            await interaction.response.send_message("❌ An error occurred", ephemeral=True)
    
    @discord.ui.button(label="Switch to All Servers", style=discord.ButtonStyle.primary, custom_id="toggle_scope", row=2)
    async def toggle_scope(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle between server-specific and global settings"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ These are not your settings!", ephemeral=True)
            return
        
        # Toggle between server and global
        if self.guild_id:
            # Switch to global
            self.guild_id = None
            button.label = "Switch to This Server"
        else:
            # Switch back to server (if we have a guild)
            if interaction.guild:
                self.guild_id = interaction.guild.id
                button.label = "Switch to All Servers"
            else:
                await interaction.response.send_message("❌ Cannot switch to server settings outside of a server!", ephemeral=True)
                return
        
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)


class SettingsGroup(app_commands.Group):
    """User settings and preferences"""
    
    def __init__(self):
        super().__init__(name="settings", description="User settings and preferences")
    
    @app_commands.command(name="menu", description="Open your settings menu")
    async def settings_menu(self, interaction: discord.Interaction):
        """Open interactive settings menu"""
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Start with server-specific settings if in a guild, otherwise global
            guild_id = interaction.guild.id if interaction.guild else None
            view = SettingsView(interaction.user.id, guild_id)
            
            await interaction.response.send_message(
                embed=view.get_embed(),
                view=view,
                ephemeral=True
            )
        except Exception as e:
            print(f"Error opening settings menu: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while opening the settings menu.",
                ephemeral=True
            )
    
    # Subcommand: /settings sendpings
    @app_commands.command(name="sendpings", description="Toggle whether your replies trigger pings to the original poster")
    @app_commands.describe(
        enabled="Enable or disable sending pings when you reply",
        all_servers="Apply to all servers (default: current server only)"
    )
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable (my replies ping others)", value=1),
        app_commands.Choice(name="Disable (my replies don't ping)", value=0)
    ])
    async def send_pings(self, interaction: discord.Interaction, enabled: int, all_servers: bool = False):
        """Toggle whether your replies trigger pings"""
        # If all_servers is True, we don't need to be in a guild
        if not all_servers and not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server unless you use `all_servers:True`!", ephemeral=True)
            return
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Update user preference (None = global, guild_id = specific server)
            guild_id = None if all_servers else interaction.guild.id
            db.set_user_setting(
                user_id=interaction.user.id,
                guild_id=guild_id,
                setting_name='send_reply_pings',
                enabled=bool(enabled)
            )
            
            status = "**enabled** ✅" if enabled else "**disabled** 🔕"
            scope = "**in all servers**" if all_servers else "in this server"
            
            response = f"Sending reply pings {status} {scope}\n"
            if all_servers:
                response += f"Your replies will {'now' if enabled else 'no longer'} trigger pings to original posters in any server."
                if not enabled:
                    response += "\n\n💡 This global setting overrides per-server settings."
            else:
                response += f"Your replies will {'now' if enabled else 'no longer'} trigger pings to original posters in this server."
            
            await interaction.response.send_message(response, ephemeral=True)
        except Exception as e:
            print(f"Error updating send pings preference: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating your preference. Please try again later.",
                ephemeral=True
            )
    
    # Subcommand: /settings notify
    @app_commands.command(name="notify", description="Toggle reply notifications when someone replies to your fixed links")
    @app_commands.describe(
        enabled="Enable or disable reply notifications",
        all_servers="Apply to all servers (default: current server only)"
    )
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable notifications", value=1),
        app_commands.Choice(name="Disable notifications", value=0)
    ])
    async def notify(self, interaction: discord.Interaction, enabled: int, all_servers: bool = False):
        """Toggle reply notification preferences"""
        # If all_servers is True, we don't need to be in a guild
        if not all_servers and not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server unless you use `all_servers:True`!", ephemeral=True)
            return
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Update user preference (None = global, guild_id = specific server)
            guild_id = None if all_servers else interaction.guild.id
            db.set_user_reply_notifications(
                user_id=interaction.user.id,
                guild_id=guild_id,
                enabled=bool(enabled)
            )
            
            status = "**enabled** ✅" if enabled else "**disabled** 🔕"
            scope = "**in all servers**" if all_servers else "in this server"
            
            response = f"Reply notifications {status} {scope}\n"
            if all_servers:
                response += f"You will {'now' if enabled else 'no longer'} be pinged when someone replies to your fixed links in any server."
                if not enabled:
                    response += "\n\n💡 This global setting overrides per-server settings."
            else:
                response += f"You will {'now' if enabled else 'no longer'} be pinged when someone replies to messages where the bot fixed your links."
            
            await interaction.response.send_message(response, ephemeral=True)
        except Exception as e:
            print(f"Error updating notification preference: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating your notification preference. Please try again later.",
                ephemeral=True
            )

