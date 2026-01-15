"""
Issue reporting view components
"""
import discord
from discord import ui
from typing import Optional


class IssuePanelView(ui.View):
    """View containing a single button to open the issue submission modal."""

    def __init__(self, guild_id: int, custom_id_prefix: Optional[str] = None):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.custom_id_prefix = custom_id_prefix or f"issue_panel:{guild_id}"
        self.report_issue_button.custom_id = f"{self.custom_id_prefix}:report"

    @ui.button(label="Submit an Issue", style=discord.ButtonStyle.blurple, emoji="📝")
    async def report_issue_button(self, interaction: discord.Interaction, button: ui.Button):
        # Import here to avoid circular dependency
        from commands.issues_commands import IssueReportModal
        
        modal = IssueReportModal()
        await interaction.response.send_modal(modal)
