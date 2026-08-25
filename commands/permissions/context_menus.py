"""User-targeted (Apps) context menu commands for the permissions domain."""
import discord
from discord import app_commands

from commands.permissions.helpers import compute_channel_visibility
from utils.interaction_helpers import send_error, require_guild, has_permission_or_owner
from utils.pagination import build_paginated_embed


@app_commands.context_menu(name="Check Channel Access")
async def check_channel_access_ctx(interaction: discord.Interaction, member: discord.Member):
    if not await require_guild(interaction):
        return
    if not await has_permission_or_owner(interaction, administrator=True):
        await send_error(interaction, "You need administrator permissions to use this.")
        return

    await interaction.response.defer(ephemeral=True)
    can_see, cannot_see = compute_channel_visibility(interaction.guild, member=member)
    embed = build_paginated_embed("👁️ Channel Visibility: can see", can_see, color=discord.Color.green(), description=f"For {member.mention}")
    embed2 = build_paginated_embed("🚫 Cannot see", cannot_see, color=discord.Color.red())
    await interaction.followup.send(embeds=[embed, embed2], ephemeral=True)
