"""Modal for submitting a poll response. Moved here from commands/poll_commands.py
so commands/poll/views.py can import it directly instead of the
circular-import-avoidance local-import hack the old poll_views.py used."""
import traceback

import discord

from database import db
from utils.logger import logger
from commands.poll.helpers import update_poll_embed


class ResponseModal(discord.ui.Modal, title="Submit Your Response"):
    """Modal for users to submit their poll responses."""

    def __init__(self, poll_id: int, question: str):
        super().__init__()
        self.poll_id = poll_id
        self.response_input = discord.ui.TextInput(
            label=question[:45],
            style=discord.TextStyle.paragraph,
            placeholder="Type your response here...",
            max_length=1000,
            required=True,
        )
        self.add_item(self.response_input)

    async def on_submit(self, interaction: discord.Interaction):
        from commands.poll.views import ClosedPollView

        try:
            logger.info(f"Response submission started for poll {self.poll_id} by {interaction.user}")

            try:
                db.store_poll_response(
                    poll_id=self.poll_id, user_id=interaction.user.id,
                    username=str(interaction.user), response_text=self.response_input.value,
                )
            except Exception as e:
                if "already submitted" in str(e):
                    await interaction.response.send_message(
                        "❌ You have already submitted a response to this poll and multiple responses are not allowed.",
                        ephemeral=True,
                    )
                    return
                raise

            poll_info = db.get_poll(self.poll_id)
            if not poll_info['is_active'] and poll_info['max_responses']:
                response_count = db.get_poll_response_count(self.poll_id)
                if response_count >= poll_info['max_responses']:
                    await interaction.response.send_message(
                        f"✅ Your response has been submitted!\n🔒 This poll has now closed (reached {poll_info['max_responses']} responses).",
                        ephemeral=True,
                    )
                    try:
                        if poll_info['message_id']:
                            message = await interaction.channel.fetch_message(poll_info['message_id'])
                            if message.embeds:
                                embed = message.embeds[0]
                                embed.color = discord.Color.red()
                                embed.title = "📊 Poll (CLOSED)"
                                await message.edit(embed=embed, view=ClosedPollView())
                    except Exception as e:
                        logger.error(f"Error updating poll message after auto-close: {e}")
                    return

            await interaction.response.send_message("✅ Your response has been submitted!", ephemeral=True)

            poll_info = db.get_poll(self.poll_id)
            if poll_info and poll_info['message_id']:
                await update_poll_embed(self.poll_id, interaction.channel, poll_info['message_id'])

        except Exception as e:
            logger.error(f"Error in response submission: {e}")
            traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            except Exception:
                try:
                    await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
                except Exception as followup_error:
                    logger.error(f"Could not send error message: {followup_error}")
