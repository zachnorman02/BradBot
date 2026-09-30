"""Modals for the poll domain: submitting a response (ResponseModal, moved
here from commands/poll_commands.py so commands/poll/views.py can import it
directly instead of the circular-import-avoidance local-import hack the old
poll_views.py used) and creating a poll (PollCreateModal)."""
import datetime as dt
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


class PollCreateModal(discord.ui.Modal, title="Create Poll"):
    """Everything /poll create used to take as separate command options,
    collected in one form instead. Discord caps modals at 5 top-level
    components, which is exactly how many are here -- the three on/off
    options (show responses, restrict results, one response per person)
    share one multi-select instead of three fields, same trick the booster
    customize modal uses for its color fields."""

    question = discord.ui.Label(
        text="Question",
        description="The poll question or prompt.",
        component=discord.ui.TextInput(style=discord.TextStyle.paragraph, max_length=1000, required=True),
    )
    image = discord.ui.Label(
        text="Image",
        description="Optional: image to display with the poll.",
        component=discord.ui.FileUpload(required=False, max_values=1),
    )
    settings = discord.ui.Label(
        text="Settings",
        description="Select any that apply.",
        component=discord.ui.Select(
            options=[
                discord.SelectOption(label="Show responses in the poll embed", value="show_responses"),
                discord.SelectOption(label="Restrict results to creator/admins only", value="restrict_results"),
                discord.SelectOption(label="Limit to one response per person", value="one_response"),
            ],
            min_values=0,
            max_values=3,
            required=False,
        ),
    )
    max_responses = discord.ui.Label(
        text="Max Responses",
        description="Optional: auto-close after this many responses.",
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=6),
    )
    duration_minutes = discord.ui.Label(
        text="Duration (Minutes)",
        description="Optional: auto-close after this many minutes.",
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=6),
    )

    async def on_submit(self, interaction: discord.Interaction):
        from commands.poll.views import PollView

        max_responses_raw = self.max_responses.component.value.strip()
        duration_raw = self.duration_minutes.component.value.strip()
        try:
            max_responses = int(max_responses_raw) if max_responses_raw else None
            duration_minutes = int(duration_raw) if duration_raw else None
        except ValueError:
            await interaction.response.send_message("❌ Max Responses and Duration must be whole numbers.", ephemeral=True)
            return

        image_files = self.image.component.values
        image = image_files[0] if image_files else None
        if image and not (image.content_type or "").startswith("image/"):
            await interaction.response.send_message("❌ That attachment isn't an image.", ephemeral=True)
            return

        selected = self.settings.component.values
        show_responses = "show_responses" in selected
        public_results = "restrict_results" not in selected
        allow_multiple = "one_response" not in selected

        question = self.question.component.value.strip()

        try:
            if not db.connection_pool:
                db.init_pool()

            close_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=duration_minutes) if duration_minutes else None

            poll_id = db.create_poll(
                guild_id=interaction.guild.id, channel_id=interaction.channel.id, creator_id=interaction.user.id,
                question=question, max_responses=max_responses, close_at=close_at,
                show_responses=show_responses, public_results=public_results, allow_multiple_responses=allow_multiple,
            )

            embed = discord.Embed(
                title="📊 Poll", description=question, color=discord.Color.blue(), timestamp=dt.datetime.now(dt.timezone.utc),
            )
            embed.set_footer(text=f"Poll ID: {poll_id} • Created by {interaction.user.display_name} • 0 responses")
            embed.add_field(name="How to Respond", value="Click the **Submit Response** button below to share your answer!", inline=False)
            if image:
                embed.set_image(url=image.url)

            poll_settings = []
            if not allow_multiple:
                poll_settings.append("🔒 One response per person")
            if not public_results:
                poll_settings.append("🔐 Results visible to creator & admins only")
            if poll_settings:
                embed.add_field(name="⚙️ Settings", value="\n".join(poll_settings), inline=False)

            auto_close_info = []
            if max_responses:
                auto_close_info.append(f"• Closes after **{max_responses}** responses")
            if close_at:
                auto_close_info.append(f"• Closes <t:{int(close_at.timestamp())}:R>")
            if auto_close_info:
                embed.add_field(name="⏱️ Auto-Close", value="\n".join(auto_close_info), inline=False)

            view = PollView(poll_id, question)
            await interaction.response.send_message(embed=embed, view=view)

            message = await interaction.original_response()
            db.update_poll_message_id(poll_id, message.id)

            logger.info(f"📊 Poll created by {interaction.user} in {interaction.guild.name}: {question}")
        except Exception as e:
            logger.error(f"Error creating poll: {e}")
            await interaction.response.send_message("❌ An error occurred while creating the poll. Please try again.", ephemeral=True)
