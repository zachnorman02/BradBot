"""Modal for editing a bot-replaced link message."""
from types import SimpleNamespace

import discord

from core.message_processing import process_message_links
from commands.link.helpers import split_user_text


class LinkEditModal(discord.ui.Modal):
    def __init__(self, message: discord.Message, mention: str):
        super().__init__(title="Edit replaced message", timeout=300)
        self.message = message
        self.mention = mention
        self.text_input = discord.ui.TextInput(
            label="Message content", style=discord.TextStyle.paragraph, max_length=1900, default=message.content,
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_content = self.text_input.value.strip()
        if not new_content:
            await interaction.response.send_message("❌ Message cannot be empty.", ephemeral=True)
            return

        base_text, extra_lines = split_user_text(new_content, self.mention)
        if not base_text:
            await interaction.response.send_message("❌ Message cannot be empty.", ephemeral=True)
            return

        dummy_message = SimpleNamespace(content=base_text, guild=interaction.guild, author=interaction.user, reference=None)
        processed = await process_message_links(dummy_message)
        if processed and processed.get("content_changed"):
            final_content = processed["new_content"]
        else:
            final_content = f"{self.mention}: {base_text}"
            if extra_lines:
                final_content += "\n" + "\n".join(extra_lines)

        try:
            await self.message.edit(content=final_content)
            await interaction.response.send_message("✅ Message updated.", ephemeral=True)
        except discord.DiscordException as e:
            await interaction.response.send_message(f"❌ Failed to edit message: {e}", ephemeral=True)
