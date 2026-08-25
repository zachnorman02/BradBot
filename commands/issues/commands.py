"""GitHub issue reporting commands."""
import datetime as dt

import discord
from discord import app_commands

import config
from database import db
from utils.logger import logger
from commands.issues.views import IssuePanelView


class IssuesGroup(app_commands.Group):
    """Slash command group for issue reporting utilities."""

    def __init__(self):
        super().__init__(name="issues", description="GitHub issue reporting commands")

    @app_commands.command(name="panel", description="Create a persistent GitHub issue submission panel")
    @app_commands.default_permissions(administrator=True)
    async def panel(self, interaction: discord.Interaction):
        """Create a panel that lets users submit GitHub issues via a modal."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        try:
            if not db.connection_pool:
                db.init_pool()

            prefix = f"issue_panel:{interaction.guild.id}:{int(dt.datetime.now(dt.timezone.utc).timestamp())}"
            view = IssuePanelView(interaction.guild.id, custom_id_prefix=prefix)

            embed = discord.Embed(
                title="🐞 Report an Issue or Discussion",
                description=(
                    "Found a bug or have an idea? Click below to submit directly to GitHub.\n\n"
                    "The modal lets you choose between Bug, Enhancement, Q&A discussion, or General discussion."
                ),
                color=discord.Color.orange(),
            )
            embed.set_footer(text="Issues are created on GitHub with your Discord username.")

            message = await interaction.channel.send(embed=embed, view=view)
            interaction.client.add_view(view, message_id=message.id)

            db.save_persistent_panel(
                message_id=message.id, guild_id=interaction.guild.id, channel_id=interaction.channel.id,
                panel_type=config.PANEL_TYPE_ISSUE_PANEL, metadata={'custom_id_prefix': prefix},
            )

            await interaction.response.send_message("✅ Issue submission panel created! Anyone can now open the modal from this message.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating issues panel: {e}")
            await interaction.response.send_message("❌ An error occurred while creating the issues panel.", ephemeral=True)
