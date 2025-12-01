"""
Settings command group for user preferences
"""
import discord
from discord import app_commands
from database import db


class SettingsGroup(app_commands.Group):
    """User settings and preferences"""
    
    @app_commands.command(name="notify", description="Toggle reply notifications when someone replies to your fixed links")
    @app_commands.describe(enabled="Enable or disable reply notifications")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable notifications", value=1),
        app_commands.Choice(name="Disable notifications", value=0)
    ])
    async def notify(self, interaction: discord.Interaction, enabled: int):
        """Toggle reply notification preferences"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Update user preference
            db.set_user_reply_notifications(
                user_id=interaction.user.id,
                guild_id=interaction.guild.id,
                enabled=bool(enabled)
            )
            
            status = "**enabled** ✅" if enabled else "**disabled** 🔕"
            await interaction.response.send_message(
                f"Reply notifications {status}\n"
                f"You will {'now' if enabled else 'no longer'} be pinged when someone replies to messages "
                f"where the bot fixed your links.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error updating notification preference: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating your notification preference. Please try again later.",
                ephemeral=True
            )
