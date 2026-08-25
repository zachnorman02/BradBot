"""Board picker follow-up for the starboard message context menus, shown
only when a guild has more than one starboard configured."""
from typing import Literal

import discord

from database import db
from commands.starboard.helpers import force_to_starboard, block_from_starboard, unblock_from_starboard

ACTION_LABELS = {
    "force": ("Forced to starboard", "❌ You need Manage Messages to use this."),
    "block": ("Blocked from starboard", "❌ You need Manage Messages to use this."),
    "unblock": ("Overrides cleared", "❌ You need Manage Messages to use this."),
}


class BoardPickerView(discord.ui.View):
    def __init__(self, message: discord.Message, boards: list[dict], action: Literal["force", "block", "unblock"]):
        super().__init__(timeout=60)
        self.message = message
        self.boards = {str(b["id"]): b for b in boards}
        self.action = action

        options = [
            discord.SelectOption(label=f"#{message.guild.get_channel(b['channel_id']) or b['channel_id']} ({b['emoji']})", value=str(b["id"]))
            for b in boards[:25]
        ]
        select = discord.ui.Select(placeholder="Choose a starboard...", options=options)
        select.callback = self._callback
        self.add_item(select)
        self._select = select

    async def _callback(self, interaction: discord.Interaction):
        board = self.boards[self._select.values[0]]
        await interaction.response.defer(ephemeral=True)

        if self.action == "force":
            await force_to_starboard(interaction.client, board, self.message)
        elif self.action == "block":
            await block_from_starboard(interaction.guild, board, self.message)
        else:
            await unblock_from_starboard(interaction.client, board, self.message)

        label, _ = ACTION_LABELS[self.action]
        await interaction.followup.send(f"✅ {label}.", ephemeral=True)
