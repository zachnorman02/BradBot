import re
from types import SimpleNamespace
from typing import Optional

import discord
from discord import app_commands

from core.message_processing import process_message_links


MESSAGE_LINK_RE = re.compile(
    r"https?://(?:canary\.|ptb\.)?discord(?:app)?\.com/channels/(?P<guild_id>\d+|@me)/(?P<channel_id>\d+)/(?P<message_id>\d+)"
)
MENTION_PREFIX_RE = re.compile(r"^<@!?(\d+)>:")


def _parse_message_link(link: str) -> Optional[tuple[int, int, int]]:
    match = MESSAGE_LINK_RE.match(link.strip())
    if not match:
        return None
    guild_id = match.group("guild_id")
    if guild_id == "@me":
        return None
    return int(guild_id), int(match.group("channel_id")), int(match.group("message_id"))


class LinkEditModal(discord.ui.Modal):
    def __init__(self, message: discord.Message, mention: str, outer_group: "LinkGroup"):
        super().__init__(title="Edit replaced message", timeout=300)
        self.message = message
        self.mention = mention
        self.outer = outer_group
        self.text_input = discord.ui.TextInput(
            label="Message content",
            style=discord.TextStyle.paragraph,
            max_length=1900,
            default=message.content,
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_content = self.text_input.value.strip()
        if not new_content:
            await interaction.response.send_message("❌ Message cannot be empty.", ephemeral=True)
            return

        base_text, extra_lines = self.outer._split_user_text(new_content, self.mention)
        if not base_text:
            await interaction.response.send_message("❌ Message cannot be empty.", ephemeral=True)
            return

        dummy_message = SimpleNamespace(
            content=base_text,
            guild=interaction.guild,
            author=interaction.user,
            reference=None,
        )
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


class LinkGroup(app_commands.Group):
    """Commands for editing or deleting bot-created link replacement messages."""

    def __init__(self):
        super().__init__(name="link", description="Manage your replaced link messages")

    async def _fetch_and_validate_message(
        self,
        interaction: discord.Interaction,
        message_link: str,
    ) -> tuple[discord.Message, str]:
        parsed = _parse_message_link(message_link)
        if not parsed:
            raise app_commands.AppCommandError("Invalid message link.")
        guild_id, channel_id, message_id = parsed

        if not interaction.guild or interaction.guild.id != guild_id:
            raise app_commands.AppCommandError("That message is not in this server.")

        channel = interaction.client.get_channel(channel_id)
        if not channel:
            try:
                channel = await interaction.client.fetch_channel(channel_id)
            except discord.DiscordException:
                raise app_commands.AppCommandError("I can't access that channel.")
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            raise app_commands.AppCommandError("Message not found.")
        except discord.Forbidden:
            raise app_commands.AppCommandError("I don't have permission to view that message.")

        if message.author.id != interaction.client.user.id:
            raise app_commands.AppCommandError("That message was not sent by me.")

        mention_match = MENTION_PREFIX_RE.match(message.content.strip())
        if not mention_match or int(mention_match.group(1)) != interaction.user.id:
            raise app_commands.AppCommandError("You can only modify your own replaced messages.")
        mention_str = mention_match.group(0)[:-1]  # remove trailing colon
        return message, mention_str

    def _split_user_text(self, content: str, mention: str) -> tuple[str, list[str]]:
        text = content
        prefix = f"{mention}:"
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip()
        lines = text.split("\n")
        main_lines = []
        extra_lines = []
        for line in lines:
            if line.strip().startswith("-# "):
                extra_lines.append(line.strip())
            else:
                main_lines.append(line)
        base_text = "\n".join(main_lines).strip()
        return base_text, extra_lines

    @app_commands.command(name="edit", description="Edit your replaced link message")
    @app_commands.describe(message_link="Link to the bot's message")
    async def edit(self, interaction: discord.Interaction, message_link: str):
        try:
            message, mention = await self._fetch_and_validate_message(interaction, message_link)
        except app_commands.AppCommandError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        modal = LinkEditModal(message=message, mention=mention, outer_group=self)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="delete", description="Delete your replaced link message")
    @app_commands.describe(message_link="Link to the bot's message you want to delete")
    async def delete(self, interaction: discord.Interaction, message_link: str):
        try:
            message, _ = await self._fetch_and_validate_message(interaction, message_link)
        except app_commands.AppCommandError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        try:
            await message.delete()
            await interaction.response.send_message("✅ Message deleted.", ephemeral=True)
        except discord.DiscordException as e:
            await interaction.response.send_message(f"❌ Failed to delete message: {e}", ephemeral=True)
