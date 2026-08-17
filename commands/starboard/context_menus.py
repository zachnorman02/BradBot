"""Message context menus for starboard actions. Replaces the old
message_link-param lock/block/unblock commands -- if the guild has exactly
one starboard the action applies immediately, otherwise a board picker is
shown (a guild can have more than one starboard)."""
import discord
from discord import app_commands

from database import db
from utils.interaction_helpers import require_guild, send_error, has_permission_or_owner
from commands.starboard.helpers import force_to_starboard, block_from_starboard, unblock_from_starboard
from commands.starboard.views import BoardPickerView


async def _dispatch(interaction: discord.Interaction, message: discord.Message, action: str, success_text: str):
    if not await require_guild(interaction):
        return
    if not await has_permission_or_owner(interaction, manage_messages=True):
        await send_error(interaction, "You need Manage Messages to use this.")
        return

    boards = db.get_starboard_boards(interaction.guild.id)
    if not boards:
        await send_error(interaction, "No starboards configured in this server.")
        return

    if len(boards) > 1:
        await interaction.response.send_message(
            "Multiple starboards configured -- choose one:", view=BoardPickerView(message, boards, action), ephemeral=True
        )
        return

    board = boards[0]
    await interaction.response.defer(ephemeral=True)
    if action == "force":
        await force_to_starboard(interaction.client, board, message)
    elif action == "block":
        await block_from_starboard(interaction.guild, board, message)
    else:
        await unblock_from_starboard(interaction.client, board, message)
    await interaction.followup.send(f"✅ {success_text}.", ephemeral=True)


@app_commands.context_menu(name="Force to Starboard")
async def force_to_starboard_ctx(interaction: discord.Interaction, message: discord.Message):
    await _dispatch(interaction, message, "force", "Message forced to starboard")


@app_commands.context_menu(name="Block from Starboard")
async def block_from_starboard_ctx(interaction: discord.Interaction, message: discord.Message):
    await _dispatch(interaction, message, "block", "Message blocked from starboard")


@app_commands.context_menu(name="Unblock from Starboard")
async def unblock_from_starboard_ctx(interaction: discord.Interaction, message: discord.Message):
    await _dispatch(interaction, message, "unblock", "Overrides cleared")
