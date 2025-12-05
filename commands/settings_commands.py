"""
Settings command group for user preferences
"""
import discord
from discord import app_commands
from database import db


class SettingsGroup(app_commands.Group):
    """User settings and preferences"""
    
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

