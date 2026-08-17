"""Interactive user-settings panel. This is the only surface for
send_reply_pings/receive-notification toggles now -- the old `/settings
sendpings` and `/settings notify` slash commands duplicated exactly what
these buttons already do, so they were removed rather than kept in sync."""
import discord

from database import db
from utils.logger import logger


class SettingsView(discord.ui.View):
    """Interactive view for user settings."""

    def __init__(self, user_id: int, guild_id: int = None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.update_buttons()

    def update_buttons(self):
        try:
            send_pings = db.get_user_setting(self.user_id, self.guild_id, 'send_reply_pings', True)
            receive_pings = db.get_user_reply_notifications(self.user_id, self.guild_id)
            if receive_pings is None:
                receive_pings = True

            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    if item.custom_id == 'toggle_send_pings':
                        item.label = f"🔔 Send Reply Pings {'✓' if send_pings else '✗'}"
                        item.style = discord.ButtonStyle.green if send_pings else discord.ButtonStyle.gray
                    elif item.custom_id == 'toggle_receive_pings':
                        item.label = f"📩 Receive Notifications {'✓' if receive_pings else '✗'}"
                        item.style = discord.ButtonStyle.green if receive_pings else discord.ButtonStyle.gray
                    elif item.custom_id == 'toggle_scope':
                        item.label = "🌐 Switch to This Server" if self.guild_id is None else "🌍 Switch to All Servers"
                        item.style = discord.ButtonStyle.primary
                    elif item.custom_id == 'refresh_settings':
                        item.label = "🔄 Refresh"
                        item.style = discord.ButtonStyle.blurple
        except Exception as e:
            logger.error(f"Error updating buttons: {e}")

    def get_embed(self) -> discord.Embed:
        try:
            send_pings = db.get_user_setting(self.user_id, self.guild_id, 'send_reply_pings', True)
            receive_pings = db.get_user_reply_notifications(self.user_id, self.guild_id)
            if receive_pings is None:
                receive_pings = True

            embed = discord.Embed(title="⚙️ Settings", description="Configure your BradBot preferences", color=discord.Color.blue())

            send_status = "🟢 Enabled" if send_pings else "🔴 Disabled"
            embed.add_field(
                name="Send Reply Pings",
                value=f"{send_status}\nYour replies {'will' if send_pings else 'will not'} ping the original poster",
                inline=False,
            )

            receive_status = "🟢 Enabled" if receive_pings else "🔴 Disabled"
            embed.add_field(
                name="Receive Reply Notifications",
                value=f"{receive_status}\nYou {'will' if receive_pings else 'will not'} be notified when others reply to your messages",
                inline=False,
            )

            embed.set_footer(text=f"Settings apply to {'this server' if self.guild_id else 'all servers'}")
            return embed
        except Exception as e:
            logger.error(f"Error generating embed: {e}")
            return discord.Embed(title="⚙️ Settings", description="Error loading settings", color=discord.Color.red())

    @discord.ui.button(label="🔔 Send Reply Pings", style=discord.ButtonStyle.success, custom_id="toggle_send_pings", row=0)
    async def toggle_send_pings(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ These are not your settings!", ephemeral=True)
            return
        try:
            current = db.get_user_setting(self.user_id, self.guild_id, 'send_reply_pings', True)
            db.set_user_setting(user_id=self.user_id, guild_id=self.guild_id, setting_name='send_reply_pings', enabled=not current)
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        except Exception as e:
            logger.error(f"Error toggling send pings: {e}")
            await interaction.response.send_message("❌ An error occurred", ephemeral=True)

    @discord.ui.button(label="📩 Receive Notifications", style=discord.ButtonStyle.success, custom_id="toggle_receive_pings", row=0)
    async def toggle_receive_pings(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ These are not your settings!", ephemeral=True)
            return
        try:
            current = db.get_user_reply_notifications(self.user_id, self.guild_id)
            if current is None:
                current = True
            db.set_user_reply_notifications(user_id=self.user_id, guild_id=self.guild_id, enabled=not current)
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        except Exception as e:
            logger.error(f"Error toggling receive pings: {e}")
            await interaction.response.send_message("❌ An error occurred", ephemeral=True)

    @discord.ui.button(label="🌍 Switch Scope", style=discord.ButtonStyle.primary, custom_id="toggle_scope", row=1)
    async def toggle_scope(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ These are not your settings!", ephemeral=True)
            return

        if self.guild_id:
            self.guild_id = None
            button.label = "Switch to This Server"
        else:
            if interaction.guild:
                self.guild_id = interaction.guild.id
                button.label = "Switch to All Servers"
            else:
                await interaction.response.send_message("❌ Cannot switch to server settings outside of a server!", ephemeral=True)
                return

        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.blurple, custom_id="refresh_settings", row=1)
    async def refresh_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ These are not your settings!", ephemeral=True)
            return
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
