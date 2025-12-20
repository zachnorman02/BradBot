import re
from typing import Optional

import discord
from discord import app_commands


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


class LinkGroup(app_commands.Group):
    """Commands for editing or deleting bot-created link replacement messages."""

    def __init__(self):
        super().__init__(name="link", description="Manage your replaced link messages")

    async def _fetch_and_validate_message(
        self,
        interaction: discord.Interaction,
        message_link: str,
    ) -> discord.Message:
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
        return message

    def _preserve_extra_lines(self, content: str) -> list[str]:
        lines = content.split("\n")
        return [line for line in lines[1:] if line.startswith("-# ")]

    @app_commands.command(name="edit", description="Edit your replaced link message")
    @app_commands.describe(message_link="Link to the bot's message", new_text="Replacement text (without mention)")
    async def edit(self, interaction: discord.Interaction, message_link: str, new_text: str):
        if not new_text or not new_text.strip():
            await interaction.response.send_message("❌ New text cannot be empty.", ephemeral=True)
            return
        try:
            message = await self._fetch_and_validate_message(interaction, message_link)
        except app_commands.AppCommandError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        extra_lines = self._preserve_extra_lines(message.content)
        new_content = f"{interaction.user.mention}: {new_text.strip()}"
        if extra_lines:
            new_content += "\n" + "\n".join(extra_lines)

        try:
            await message.edit(content=new_content)
            await interaction.response.send_message("✅ Message updated.", ephemeral=True)
        except discord.DiscordException as e:
            await interaction.response.send_message(f"❌ Failed to edit message: {e}", ephemeral=True)

    @app_commands.command(name="delete", description="Delete your replaced link message")
    @app_commands.describe(message_link="Link to the bot's message you want to delete")
    async def delete(self, interaction: discord.Interaction, message_link: str):
        try:
            message = await self._fetch_and_validate_message(interaction, message_link)
        except app_commands.AppCommandError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        try:
            await message.delete()
            await interaction.response.send_message("✅ Message deleted.", ephemeral=True)
        except discord.DiscordException as e:
            await interaction.response.send_message(f"❌ Failed to delete message: {e}", ephemeral=True)
