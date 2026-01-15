"""
Poll view components
"""
import discord
from discord import ui


class PollView(discord.ui.View):
    """View with a button to respond to the poll"""
    
    def __init__(self, poll_id: int, question: str):
        super().__init__(timeout=None)  # Persistent view
        self.poll_id = poll_id
        self.question = question
        
        # Create button with unique custom_id for this poll
        button = discord.ui.Button(
            label="Submit Response",
            style=discord.ButtonStyle.primary,
            emoji="📝",
            custom_id=f"poll_submit_{poll_id}"
        )
        button.callback = self.respond_button
        self.add_item(button)
    
    async def respond_button(self, interaction: discord.Interaction):
        """Show modal to collect user response"""
        # Import here to avoid circular dependency
        from commands.poll_commands import ResponseModal
        
        print(f"[POLL] Button clicked for poll {self.poll_id} by {interaction.user}")
        modal = ResponseModal(self.poll_id, self.question)
        await interaction.response.send_modal(modal)
