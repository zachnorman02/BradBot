"""Follow-up candidate picker for the emoji message-context-menu family.

Context menus can't take a "which one(s)" text param the way the old slash
commands did, so when a message has more than one emoji/image/reaction
candidate, this Select lets the user pick which to import.
"""
from typing import Awaitable, Callable

import discord
from discord import ui


class EmojiCandidatePickerView(ui.View):
    def __init__(self, options: list[discord.SelectOption], on_pick: Callable[[discord.Interaction, list[int]], Awaitable[None]]):
        super().__init__(timeout=120)
        self.on_pick = on_pick
        select = ui.Select(placeholder="Choose which to import...", options=options, max_values=len(options))
        select.callback = self._callback
        self.add_item(select)
        self._select = select

    async def _callback(self, interaction: discord.Interaction):
        indices = [int(v) for v in self._select.values]
        await self.on_pick(interaction, indices)
