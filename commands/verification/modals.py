"""Modal for setting up tracked rules-agreement messages."""
import re

import discord

from database import db
from utils.logger import logger

MESSAGE_URL_RE = re.compile(r'https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)')


class VerifySettingsModal(discord.ui.Modal, title="Rules Agreement Settings"):
    verified_role = discord.ui.Label(
        text="Verified Role (optional)",
        description="Leave empty to keep the current setting.",
        component=discord.ui.RoleSelect(min_values=0, max_values=1, required=False),
    )
    remove_on_verify = discord.ui.Label(
        text="Remove Reactions On Verify",
        description="Auto-remove tracked rules reactions when a member gets verified.",
        component=discord.ui.Select(options=[
            discord.SelectOption(label="Enabled", value="true"),
            discord.SelectOption(label="Disabled", value="false"),
        ]),
    )
    remove_on_leave = discord.ui.Label(
        text="Remove Reactions On Leave",
        description="Auto-remove tracked rules reactions when a member leaves.",
        component=discord.ui.Select(options=[
            discord.SelectOption(label="Enabled", value="true"),
            discord.SelectOption(label="Disabled", value="false"),
        ]),
    )
    message_urls = discord.ui.Label(
        text="Tracked Message URLs (optional)",
        description="Prefilled with what's currently tracked. One per line (or comma-separated) -- this REPLACES the whole list, so edit in place rather than typing only a new one. Clearing this box does nothing (use /verify clear to actually stop tracking).",
        component=discord.ui.TextInput(style=discord.TextStyle.paragraph, required=False, max_length=2000),
    )

    def __init__(
        self, guild: discord.Guild, current_verified_role_name: str, current_remove_on_verify: bool,
        current_remove_on_leave: bool, current_message_urls: list[str] = None,
    ):
        super().__init__()
        role_obj = discord.utils.get(guild.roles, name=current_verified_role_name)
        if role_obj:
            self.verified_role.component.default_values = [role_obj]
        for opt in self.remove_on_verify.component.options:
            opt.default = opt.value == ("true" if current_remove_on_verify else "false")
        for opt in self.remove_on_leave.component.options:
            opt.default = opt.value == ("true" if current_remove_on_leave else "false")
        if current_message_urls:
            self.message_urls.component.default = "\n".join(current_message_urls)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        changes = []

        roles = list(self.verified_role.component.values)
        if roles:
            db.set_guild_setting(guild_id, 'verified_role_name', roles[0].name)
            changes.append(f"Verified role: {roles[0].mention}")

        remove_on_verify = self.remove_on_verify.component.values[0] == "true"
        db.set_guild_setting(guild_id, 'rules_reaction_cleanup_on_verify_enabled', 'true' if remove_on_verify else 'false')
        changes.append(f"Remove on verify: **{'enabled' if remove_on_verify else 'disabled'}**")

        remove_on_leave = self.remove_on_leave.component.values[0] == "true"
        db.set_guild_setting(guild_id, 'rules_reaction_cleanup_on_leave_enabled', 'true' if remove_on_leave else 'false')
        changes.append(f"Remove on leave: **{'enabled' if remove_on_leave else 'disabled'}**")

        raw_urls = self.message_urls.component.value
        if not raw_urls:
            await interaction.response.send_message("✅ Updated rules-agreement settings.\n" + "\n".join(changes), ephemeral=True)
            return

        # Role + toggle changes above are already saved -- a problem parsing
        # the message list shouldn't roll those back, just stop short of
        # touching the tracked-message list.
        urls = [u.strip() for u in re.split(r'[,\n]+', raw_urls) if u.strip()]
        message_data = []
        for url in urls:
            match = MESSAGE_URL_RE.match(url)
            if not match:
                await interaction.response.send_message(
                    "✅ Updated rules-agreement settings.\n" + "\n".join(changes) +
                    f"\n\n⚠️ Tracked messages NOT updated: invalid message URL `{url}`.\nRight-click a message and select 'Copy Message Link'.",
                    ephemeral=True,
                )
                return
            msg_guild_id, channel_id, message_id = match.groups()
            if int(msg_guild_id) != guild_id:
                await interaction.response.send_message(
                    "✅ Updated rules-agreement settings.\n" + "\n".join(changes) +
                    f"\n\n⚠️ Tracked messages NOT updated: message URL is from a different server: `{url}`.",
                    ephemeral=True,
                )
                return
            message_data.append({'channel_id': int(channel_id), 'message_id': int(message_id), 'url': url})

        await interaction.response.defer(ephemeral=True)

        verified_messages = []
        for data in message_data:
            try:
                channel = interaction.guild.get_channel(data['channel_id'])
                if not channel:
                    await interaction.followup.send(
                        "✅ Updated rules-agreement settings.\n" + "\n".join(changes) +
                        f"\n\n⚠️ Tracked messages NOT updated: could not find channel for message `{data['url']}`.",
                        ephemeral=True,
                    )
                    return
                message = await channel.fetch_message(data['message_id'])
                verified_messages.append({'channel_id': data['channel_id'], 'message_id': data['message_id'], 'jump_url': message.jump_url})
            except discord.NotFound:
                await interaction.followup.send(
                    "✅ Updated rules-agreement settings.\n" + "\n".join(changes) +
                    f"\n\n⚠️ Tracked messages NOT updated: could not find message `{data['url']}`.",
                    ephemeral=True,
                )
                return
            except discord.Forbidden:
                await interaction.followup.send(
                    "✅ Updated rules-agreement settings.\n" + "\n".join(changes) +
                    f"\n\n⚠️ Tracked messages NOT updated: no permission to access the channel for `{data['url']}`.",
                    ephemeral=True,
                )
                return

        db.set_rules_agreement_messages(guild_id, verified_messages)
        changes.append(f"Tracked messages: {len(verified_messages)} message(s)")
        logger.info(f"Rules agreement messages set by {interaction.user} with {len(verified_messages)} messages")

        await interaction.followup.send("✅ Updated rules-agreement settings.\n" + "\n".join(changes), ephemeral=True)
