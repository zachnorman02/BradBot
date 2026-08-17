"""Refreshable list views for the permissions domain.

Unlike the pre-reorg versions, these take just a guild and call the
standalone embed-builder helpers directly, instead of holding a reference to
the command-group instance that defined them.
"""
import discord
from discord import ui

from commands.permissions.helpers import build_channel_restrictions_embed, build_conditional_role_configs_embed
from utils.interaction_helpers import has_permission_or_owner


class ChannelRestrictionListView(ui.View):
    """Refreshable list view for channel restrictions."""

    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=300)
        self.guild = guild

    async def _ensure_admin(self, interaction: discord.Interaction) -> bool:
        if not await has_permission_or_owner(interaction, administrator=True):
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return False
        return True

    @ui.button(label="🔄 Refresh", style=discord.ButtonStyle.blurple)
    async def refresh(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._ensure_admin(interaction):
            return
        embed = build_channel_restrictions_embed(self.guild)
        await interaction.response.edit_message(embed=embed, view=self)


class ConditionalRoleListView(ui.View):
    """Refreshable list view for conditional role configs."""

    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=300)
        self.guild = guild

    async def _ensure_admin(self, interaction: discord.Interaction) -> bool:
        if not await has_permission_or_owner(interaction, administrator=True):
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return False
        return True

    @ui.button(label="🔄 Refresh", style=discord.ButtonStyle.blurple)
    async def refresh(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._ensure_admin(interaction):
            return
        embed = build_conditional_role_configs_embed(self.guild)
        await interaction.response.edit_message(embed=embed, view=self)
