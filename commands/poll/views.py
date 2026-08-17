"""Poll view components."""
import discord

from commands.poll.modals import ResponseModal


class PollView(discord.ui.View):
    """Persistent view with a button to respond to the poll."""

    def __init__(self, poll_id: int, question: str):
        super().__init__(timeout=None)
        self.poll_id = poll_id
        self.question = question

        button = discord.ui.Button(
            label="Submit Response", style=discord.ButtonStyle.primary, emoji="📝", custom_id=f"poll_submit_{poll_id}"
        )
        button.callback = self.respond_button
        self.add_item(button)

    async def respond_button(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ResponseModal(self.poll_id, self.question))


class ClosedPollView(discord.ui.View):
    """Disabled-button view shown on a poll message once it's closed.
    Consolidates two byte-for-byte-duplicated inline views from the old
    poll_commands.py (ResponseModal's auto-close path and refresh_poll)."""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Poll Closed", style=discord.ButtonStyle.secondary, disabled=True))
