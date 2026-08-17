"""View components for the admin domain."""
from typing import Optional

import discord
from discord import ui

from database import db
from utils.interaction_helpers import has_permission_or_owner


class AdminSettingsView(ui.View):
    """Interactive admin settings view with toggle buttons"""

    def __init__(self, guild_id: int, persistent: bool = False, custom_id_prefix: Optional[str] = None):
        super().__init__(timeout=None if persistent else 180)
        self.guild_id = guild_id
        self.persistent = persistent
        self.custom_id_prefix = custom_id_prefix
        if self.persistent:
            self.timeout = None
            self._set_persistent_custom_ids()
        self.update_buttons()

    def _set_persistent_custom_ids(self):
        prefix = self.custom_id_prefix or f"admin_panel:{self.guild_id}"
        suffixes = [
            "link", "verify", "booster", "unverified", "reply",
            "member_send", "auto_kick", "auto_ban", "rules_reaction_cleanup", "refresh",
        ]
        buttons = [child for child in self.children if isinstance(child, discord.ui.Button)]
        for button, suffix in zip(buttons, suffixes):
            button.custom_id = f"{prefix}:{suffix}"

    def get_embed(self) -> discord.Embed:
        link_replacement = db.get_guild_setting(self.guild_id, 'link_replacement_enabled', 'true').lower() == 'true'
        verify_roles = db.get_guild_setting(self.guild_id, 'verify_roles_enabled', 'true').lower() == 'true'
        booster_roles = db.get_guild_setting(self.guild_id, 'booster_roles_enabled', 'true').lower() == 'true'
        unverified_kicks = db.get_guild_setting(self.guild_id, 'unverified_kicks_enabled', 'false').lower() == 'true'
        reply_pings = db.get_guild_setting(self.guild_id, 'reply_pings_enabled', 'true').lower() == 'true'
        member_send_pings = db.get_guild_setting(self.guild_id, 'member_send_pings_enabled', 'true').lower() == 'true'
        auto_kick_single = db.get_guild_setting(self.guild_id, 'auto_kick_single_server', 'false').lower() == 'true'
        auto_ban_single = db.get_guild_setting(self.guild_id, 'auto_ban_single_server', 'false').lower() == 'true'
        rules_cleanup_on_verify = db.get_guild_setting(
            self.guild_id, 'rules_reaction_cleanup_on_verify_enabled', 'false'
        ).lower() == 'true'

        embed = discord.Embed(
            title="⚙️ Server Settings",
            description="Toggle server automation and features",
            color=discord.Color.blue(),
        )
        embed.add_field(name="🔗 Link Replacement", value='🟢 Enabled' if link_replacement else '🔴 Disabled', inline=True)
        embed.add_field(name="✅ Verify Roles", value='🟢 Enabled' if verify_roles else '🔴 Disabled', inline=True)
        embed.add_field(name="💎 Booster Roles", value='🟢 Enabled' if booster_roles else '🔴 Disabled', inline=True)
        embed.add_field(name="👢 Unverified Kicks", value='🟢 Enabled' if unverified_kicks else '🔴 Disabled', inline=True)
        embed.add_field(name="🔔 Reply Pings", value='🟢 Enabled' if reply_pings else '🔴 Disabled', inline=True)
        embed.add_field(name="📤 Member Send Pings", value='🟢 Enabled' if member_send_pings else '🔴 Disabled', inline=True)
        embed.add_field(name="🦵 Auto-Kick Single Server", value='🟢 Enabled' if auto_kick_single else '🔴 Disabled', inline=True)
        embed.add_field(name="🔨 Auto-Ban Single Server", value='🟢 Enabled' if auto_ban_single else '🔴 Disabled', inline=True)
        embed.add_field(name="🧹 Rules Reaction Cleanup", value='🟢 Enabled' if rules_cleanup_on_verify else '🔴 Disabled', inline=True)
        embed.set_footer(text="Click buttons to toggle settings")
        return embed

    def update_buttons(self):
        link_replacement = db.get_guild_setting(self.guild_id, 'link_replacement_enabled', 'true').lower() == 'true'
        verify_roles = db.get_guild_setting(self.guild_id, 'verify_roles_enabled', 'true').lower() == 'true'
        booster_roles = db.get_guild_setting(self.guild_id, 'booster_roles_enabled', 'true').lower() == 'true'
        unverified_kicks = db.get_guild_setting(self.guild_id, 'unverified_kicks_enabled', 'false').lower() == 'true'
        reply_pings = db.get_guild_setting(self.guild_id, 'reply_pings_enabled', 'true').lower() == 'true'
        member_send_pings = db.get_guild_setting(self.guild_id, 'member_send_pings_enabled', 'true').lower() == 'true'
        auto_kick_single = db.get_guild_setting(self.guild_id, 'auto_kick_single_server', 'false').lower() == 'true'
        auto_ban_single = db.get_guild_setting(self.guild_id, 'auto_ban_single_server', 'false').lower() == 'true'
        rules_cleanup_on_verify = db.get_guild_setting(
            self.guild_id, 'rules_reaction_cleanup_on_verify_enabled', 'false'
        ).lower() == 'true'

        self.children[0].style = discord.ButtonStyle.green if link_replacement else discord.ButtonStyle.gray
        self.children[0].label = "🔗 Link Replacement " + ("✓" if link_replacement else "✗")
        self.children[1].style = discord.ButtonStyle.green if verify_roles else discord.ButtonStyle.gray
        self.children[1].label = "✅ Verify Roles " + ("✓" if verify_roles else "✗")
        self.children[2].style = discord.ButtonStyle.green if booster_roles else discord.ButtonStyle.gray
        self.children[2].label = "💎 Booster Roles " + ("✓" if booster_roles else "✗")
        self.children[3].style = discord.ButtonStyle.green if unverified_kicks else discord.ButtonStyle.gray
        self.children[3].label = "👢 Unverified Kicks " + ("✓" if unverified_kicks else "✗")
        self.children[4].style = discord.ButtonStyle.green if reply_pings else discord.ButtonStyle.gray
        self.children[4].label = "🔔 Reply Pings " + ("✓" if reply_pings else "✗")
        self.children[5].style = discord.ButtonStyle.green if member_send_pings else discord.ButtonStyle.gray
        self.children[5].label = "📤 Member Send Pings " + ("✓" if member_send_pings else "✗")
        self.children[6].style = discord.ButtonStyle.green if auto_kick_single else discord.ButtonStyle.gray
        self.children[6].label = "🦵 Auto-Kick Singles " + ("✓" if auto_kick_single else "✗")
        self.children[7].style = discord.ButtonStyle.green if auto_ban_single else discord.ButtonStyle.gray
        self.children[7].label = "🔨 Auto-Ban Singles " + ("✓" if auto_ban_single else "✗")
        self.children[8].style = discord.ButtonStyle.green if rules_cleanup_on_verify else discord.ButtonStyle.gray
        self.children[8].label = "🧹 Rules Cleanup " + ("✓" if rules_cleanup_on_verify else "✗")

    @ui.button(label="🔗 Link Replacement", style=discord.ButtonStyle.gray, row=0)
    async def toggle_link_replacement(self, interaction: discord.Interaction, button: ui.Button):
        if not await has_permission_or_owner(interaction, administrator=True):
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'link_replacement_enabled', 'true').lower() == 'true'
        db.set_guild_link_replacement(self.guild_id, not current, interaction.user.id, str(interaction.user))
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @ui.button(label="✅ Verify Roles", style=discord.ButtonStyle.gray, row=0)
    async def toggle_verify_roles(self, interaction: discord.Interaction, button: ui.Button):
        if not await has_permission_or_owner(interaction, administrator=True):
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'verify_roles_enabled', 'true').lower() == 'true'
        db.set_guild_setting(self.guild_id, 'verify_roles_enabled', 'true' if not current else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @ui.button(label="💎 Booster Roles", style=discord.ButtonStyle.gray, row=0)
    async def toggle_booster_roles(self, interaction: discord.Interaction, button: ui.Button):
        if not await has_permission_or_owner(interaction, administrator=True):
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'booster_roles_enabled', 'true').lower() == 'true'
        db.set_guild_setting(self.guild_id, 'booster_roles_enabled', 'true' if not current else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @ui.button(label="👢 Unverified Kicks", style=discord.ButtonStyle.gray, row=1)
    async def toggle_unverified_kicks(self, interaction: discord.Interaction, button: ui.Button):
        if not await has_permission_or_owner(interaction, administrator=True):
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'unverified_kicks_enabled', 'false').lower() == 'true'
        db.set_guild_setting(self.guild_id, 'unverified_kicks_enabled', 'true' if not current else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @ui.button(label="🔔 Reply Pings", style=discord.ButtonStyle.gray, row=1)
    async def toggle_reply_pings(self, interaction: discord.Interaction, button: ui.Button):
        if not await has_permission_or_owner(interaction, administrator=True):
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'reply_pings_enabled', 'true').lower() == 'true'
        db.set_guild_setting(self.guild_id, 'reply_pings_enabled', 'true' if not current else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @ui.button(label="📤 Member Send Pings", style=discord.ButtonStyle.gray, row=1)
    async def toggle_member_send_pings(self, interaction: discord.Interaction, button: ui.Button):
        if not await has_permission_or_owner(interaction, administrator=True):
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'member_send_pings_enabled', 'true').lower() == 'true'
        db.set_guild_setting(self.guild_id, 'member_send_pings_enabled', 'true' if not current else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @ui.button(label="🦵 Auto-Kick Single Server", style=discord.ButtonStyle.gray, row=2)
    async def toggle_auto_kick_single(self, interaction: discord.Interaction, button: ui.Button):
        if not await has_permission_or_owner(interaction, administrator=True):
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'auto_kick_single_server', 'false').lower() == 'true'
        db.set_guild_setting(self.guild_id, 'auto_kick_single_server', 'true' if not current else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @ui.button(label="🔨 Auto-Ban Single Server", style=discord.ButtonStyle.gray, row=2)
    async def toggle_auto_ban_single(self, interaction: discord.Interaction, button: ui.Button):
        if not await has_permission_or_owner(interaction, administrator=True):
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'auto_ban_single_server', 'false').lower() == 'true'
        db.set_guild_setting(self.guild_id, 'auto_ban_single_server', 'true' if not current else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @ui.button(label="🧹 Rules Reaction Cleanup", style=discord.ButtonStyle.gray, row=3)
    async def toggle_rules_reaction_cleanup(self, interaction: discord.Interaction, button: ui.Button):
        if not await has_permission_or_owner(interaction, administrator=True):
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        current = db.get_guild_setting(self.guild_id, 'rules_reaction_cleanup_on_verify_enabled', 'false').lower() == 'true'
        db.set_guild_setting(self.guild_id, 'rules_reaction_cleanup_on_verify_enabled', 'true' if not current else 'false')
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @ui.button(label="🔄 Refresh Panel", style=discord.ButtonStyle.blurple, row=3)
    async def refresh_panel(self, interaction: discord.Interaction, button: ui.Button):
        if not await has_permission_or_owner(interaction, administrator=True):
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)


class CommandToggleView(ui.View):
    """Panel to toggle commands like echo and TTS per guild."""

    def __init__(self, guild_id: int, persistent: bool = False, custom_id_prefix: Optional[str] = None):
        super().__init__(timeout=None if persistent else 180)
        self.guild_id = guild_id
        self.persistent = persistent
        self.custom_id_prefix = custom_id_prefix
        if self.persistent:
            self.timeout = None
            self._set_persistent_custom_ids()
        self.update_buttons()

    def _set_persistent_custom_ids(self):
        prefix = self.custom_id_prefix or f"command_panel:{self.guild_id}"
        suffixes = ["echo", "tts", "refresh"]
        buttons = [child for child in self.children if isinstance(child, discord.ui.Button)]
        for idx, button in enumerate(buttons):
            suffix = suffixes[idx] if idx < len(suffixes) else f"btn{idx}"
            button.custom_id = f"{prefix}:{suffix}"
        for idx, child in enumerate(self.children):
            if isinstance(child, discord.ui.Button) and not child.custom_id:
                child.custom_id = f"{prefix}:extra{idx}"

    def _is_enabled(self, command_name: str) -> bool:
        return not db.is_command_disabled(self.guild_id, command_name)

    def get_embed(self) -> discord.Embed:
        echo_enabled = self._is_enabled('echo')
        tts_enabled = self._is_enabled('tts')
        embed = discord.Embed(
            title="🎚️ Command Toggles",
            description="Enable or disable commands server-wide.",
            color=discord.Color.dark_grey(),
        )
        embed.add_field(name="Echo", value="🟢 Enabled" if echo_enabled else "🔴 Disabled", inline=True)
        embed.add_field(name="TTS", value="🟢 Enabled" if tts_enabled else "🔴 Disabled", inline=True)
        embed.set_footer(text="Admins can toggle commands for this server.")
        return embed

    def update_buttons(self):
        echo_enabled = self._is_enabled('echo')
        tts_enabled = self._is_enabled('tts')
        if len(self.children) >= 1:
            self.children[0].style = discord.ButtonStyle.green if echo_enabled else discord.ButtonStyle.gray
            self.children[0].label = "Echo " + ("✓" if echo_enabled else "✗")
        if len(self.children) >= 2:
            self.children[1].style = discord.ButtonStyle.green if tts_enabled else discord.ButtonStyle.gray
            self.children[1].label = "TTS " + ("✓" if tts_enabled else "✗")

    async def _ensure_admin(self, interaction: discord.Interaction) -> bool:
        if not await has_permission_or_owner(interaction, administrator=True):
            await interaction.response.send_message("❌ You need administrator permissions to use this!", ephemeral=True)
            return False
        return True

    @ui.button(label="Echo", style=discord.ButtonStyle.gray, row=0, custom_id="command_panel:echo")
    async def toggle_echo(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._ensure_admin(interaction):
            return
        db.set_command_enabled(self.guild_id, 'echo', not self._is_enabled('echo'))
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @ui.button(label="TTS", style=discord.ButtonStyle.gray, row=0, custom_id="command_panel:tts")
    async def toggle_tts(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._ensure_admin(interaction):
            return
        db.set_command_enabled(self.guild_id, 'tts', not self._is_enabled('tts'))
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @ui.button(label="🔄 Refresh", style=discord.ButtonStyle.blurple, row=1)
    async def refresh(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._ensure_admin(interaction):
            return
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)


class MirrorChannelPickerView(ui.View):
    """Follow-up channel picker for the 'Mirror This Message' context menu.

    Context menus can't take extra parameters the way slash commands can, so
    the target channel is collected via a live ChannelSelect instead of a
    manually-typed channel argument.
    """

    def __init__(self, message: discord.Message):
        super().__init__(timeout=120)
        self.message = message

    @ui.select(cls=ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Choose a target channel")
    async def pick_channel(self, interaction: discord.Interaction, select: ui.ChannelSelect):
        from commands.admin.helpers import mirror_message_to_channel

        target_channel = select.values[0].resolve() or await select.values[0].fetch()
        await interaction.response.defer(ephemeral=True)
        await mirror_message_to_channel(interaction, self.message, target_channel)
