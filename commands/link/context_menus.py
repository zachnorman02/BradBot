"""Message-targeted (Apps) context menus for editing/deleting the bot's
replaced-link messages. Replaces the old message_link-param slash commands
-- the message is already resolved by Discord, no link to parse."""
import discord
from discord import app_commands

from commands.link.helpers import validate_own_replaced_message
from commands.link.modals import LinkEditModal


@app_commands.context_menu(name="Edit Bot Message")
async def edit_bot_message_ctx(interaction: discord.Interaction, message: discord.Message):
    ok, result = validate_own_replaced_message(message, interaction)
    if not ok:
        await interaction.response.send_message(f"❌ {result}", ephemeral=True)
        return

    await interaction.response.send_modal(LinkEditModal(message=message, mention=result))


@app_commands.context_menu(name="Delete Bot Message")
async def delete_bot_message_ctx(interaction: discord.Interaction, message: discord.Message):
    ok, result = validate_own_replaced_message(message, interaction)
    if not ok:
        await interaction.response.send_message(f"❌ {result}", ephemeral=True)
        return

    try:
        await message.delete()
        await interaction.response.send_message("✅ Message deleted.", ephemeral=True)
    except discord.DiscordException as e:
        await interaction.response.send_message(f"❌ Failed to delete message: {e}", ephemeral=True)


@app_commands.context_menu(name="Remove Embed")
async def remove_embed_ctx(interaction: discord.Interaction, message: discord.Message):
    """Suppress the embed Discord generated for the link, keeping the
    message text itself -- e.g. the link turned out NSFW or otherwise isn't
    something the author wants previewed. Same author-only lock as
    Delete/Edit Bot Message; also reachable via the 🙈 reaction shortcut."""
    ok, result = validate_own_replaced_message(message, interaction)
    if not ok:
        await interaction.response.send_message(f"❌ {result}", ephemeral=True)
        return

    try:
        await message.edit(suppress=True)
        await interaction.response.send_message("✅ Embed removed.", ephemeral=True)
    except discord.DiscordException as e:
        await interaction.response.send_message(f"❌ Failed to remove embed: {e}", ephemeral=True)
