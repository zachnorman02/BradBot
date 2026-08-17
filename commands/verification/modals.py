"""Modal for setting up tracked rules-agreement messages."""
import re

import discord

from database import db
from utils.logger import logger
from utils.interaction_helpers import send_error

MESSAGE_URL_RE = re.compile(r'https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)')


class SetupRulesMessagesModal(discord.ui.Modal, title="Set Up Rules Messages"):
    message_urls = discord.ui.Label(
        text="Message URLs",
        description="One or more message links, separated by commas or newlines.",
        component=discord.ui.TextInput(style=discord.TextStyle.paragraph, max_length=2000),
    )

    async def on_submit(self, interaction: discord.Interaction):
        urls = [u.strip() for u in re.split(r'[,\n]+', self.message_urls.component.value) if u.strip()]
        if not urls:
            await send_error(interaction, "Please provide at least one message URL.")
            return

        message_data = []
        for url in urls:
            match = MESSAGE_URL_RE.match(url)
            if not match:
                await send_error(interaction, f"Invalid message URL: `{url}`\nRight-click messages and select 'Copy Message Link'.")
                return

            guild_id, channel_id, message_id = match.groups()
            if int(guild_id) != interaction.guild.id:
                await send_error(interaction, f"Message URL is from a different server: `{url}`")
                return

            message_data.append({'channel_id': int(channel_id), 'message_id': int(message_id), 'url': url})

        await interaction.response.defer(ephemeral=False)

        verified_messages = []
        for data in message_data:
            try:
                channel = interaction.guild.get_channel(data['channel_id'])
                if not channel:
                    await interaction.followup.send(f"❌ Could not find channel for message: `{data['url']}`", ephemeral=True)
                    return

                message = await channel.fetch_message(data['message_id'])
                verified_messages.append({'channel_id': data['channel_id'], 'message_id': data['message_id'], 'jump_url': message.jump_url})
            except discord.NotFound:
                await interaction.followup.send(f"❌ Could not find message: `{data['url']}`", ephemeral=True)
                return
            except discord.Forbidden:
                await interaction.followup.send(f"❌ I don't have permission to access the channel for: `{data['url']}`", ephemeral=True)
                return

        db.set_rules_agreement_messages(interaction.guild.id, verified_messages)

        embed = discord.Embed(
            title="✅ Rules Agreement Setup Complete",
            description=f"Tracking {len(verified_messages)} message(s) for rules agreement.",
            color=discord.Color.green(),
        )
        for i, msg_data in enumerate(verified_messages, 1):
            embed.add_field(name=f"Message {i}", value=f"[Jump to message]({msg_data['jump_url']})", inline=False)

        await interaction.followup.send(embed=embed)
        logger.info(f"Rules agreement setup by {interaction.user} with {len(verified_messages)} messages")
