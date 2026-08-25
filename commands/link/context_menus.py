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
