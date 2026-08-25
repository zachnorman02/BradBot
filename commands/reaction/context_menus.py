"""Message context menu replacing reaction.check, reaction.check_url, and
utility.check_reaction -- all three answered "did user X react to message Y"
with independently-written link/ID parsing; a context menu gets the message
for free."""
import discord
from discord import app_commands

from utils.interaction_helpers import require_guild
from commands.reaction.modals import ReactionCheckModal


@app_commands.context_menu(name="Check Reactions")
async def check_reactions_ctx(interaction: discord.Interaction, message: discord.Message):
    if not await require_guild(interaction):
        return
    await interaction.response.send_modal(ReactionCheckModal(message))
