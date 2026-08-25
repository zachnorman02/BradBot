"""Poll command group for creating and managing text-response polls."""
import datetime as dt
import io
import traceback
from collections import Counter

import discord
from discord import app_commands
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from wordcloud import WordCloud

from database import db
from utils.logger import logger
from utils.interaction_helpers import has_permission_or_owner
from commands.common import owner_or_permissions
from commands.poll.views import PollView, ClosedPollView
from commands.poll.helpers import update_poll_embed, can_view_poll_results


class PollGroup(app_commands.Group):
    """Commands for creating and managing text-response polls."""

    def __init__(self):
        super().__init__(name="poll", description="Create and manage text-response polls")

    @app_commands.command(name="create", description="Create a new text-response poll")
    @app_commands.describe(
        question="The poll question or prompt",
        max_responses="Optional: Auto-close after this many responses",
        duration_minutes="Optional: Auto-close after this many minutes",
        show_responses="Show responses in the poll box (default: hidden)",
        public_results="Allow anyone to view results (default: yes, only creator+admins if no)",
        allow_multiple="Allow users to submit multiple responses (default: yes)",
    )
    @owner_or_permissions(send_polls=True)
    async def create(
        self, interaction: discord.Interaction, question: str,
        max_responses: int = None, duration_minutes: int = None,
        show_responses: bool = False, public_results: bool = True, allow_multiple: bool = True,
    ):
        """Create a new poll where users can submit text responses."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        try:
            if not db.connection_pool:
                db.init_pool()

            close_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=duration_minutes) if duration_minutes else None

            poll_id = db.create_poll(
                guild_id=interaction.guild.id, channel_id=interaction.channel.id, creator_id=interaction.user.id,
                question=question, max_responses=max_responses, close_at=close_at,
                show_responses=show_responses, public_results=public_results, allow_multiple_responses=allow_multiple,
            )

            embed = discord.Embed(title="📊 Poll", description=question, color=discord.Color.blue(), timestamp=dt.datetime.now(dt.timezone.utc))
            embed.set_footer(text=f"Poll ID: {poll_id} • Created by {interaction.user.display_name} • 0 responses")
            embed.add_field(name="How to Respond", value="Click the **Submit Response** button below to share your answer!", inline=False)

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

    @create.error
    async def create_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            message = "❌ You need the **Create Polls** permission to use this command."
            if not interaction.response.is_done():
                await interaction.response.send_message(message, ephemeral=True)
            else:
                await interaction.followup.send(message, ephemeral=True)
        else:
            raise error

    @app_commands.command(name="results", description="View responses to a poll")
    @app_commands.describe(poll_id="The ID of the poll (shown in the poll's footer)")
    async def results(self, interaction: discord.Interaction, poll_id: int):
        """View all responses to a poll."""
        try:
            if not db.connection_pool:
                db.init_pool()

            poll_info = db.get_poll(poll_id)
            if not poll_info:
                await interaction.response.send_message("❌ Poll not found.")
                return

            error = await can_view_poll_results(interaction, poll_info)
            if error:
                await interaction.response.send_message(f"❌ {error}", ephemeral=True)
                return

            responses = db.get_poll_responses(poll_id)
            if not responses:
                await interaction.response.send_message(f"📊 **Poll Results**\n**Question:** {poll_info['question']}\n\n*No responses yet.*")
                return

            embed = discord.Embed(
                title="📊 Poll Results",
                description=f"**Question:** {poll_info['question']}\n**Total Responses:** {len(responses)}",
                color=discord.Color.green(), timestamp=dt.datetime.now(dt.timezone.utc),
            )
            for i, response in enumerate(responses[:25], 1):
                embed.add_field(name=f"{i}. {response['username']}", value=response['response_text'][:1024], inline=False)
            if len(responses) > 25:
                embed.set_footer(text=f"Showing first 25 of {len(responses)} responses")

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error viewing poll results: {e}")
            await interaction.response.send_message("❌ An error occurred while fetching poll results.", ephemeral=True)

    @app_commands.command(name="toggle_show_responses", description="Toggle whether a poll shows responses in its message")
    @app_commands.describe(poll_id="The ID of the poll to update", show_responses="Enable or disable showing responses in the poll embed")
    @owner_or_permissions(manage_messages=True)
    async def toggle_show_responses(self, interaction: discord.Interaction, poll_id: int, show_responses: bool):
        """Allow creators/admins to toggle response visibility on the poll embed."""
        try:
            if not db.connection_pool:
                db.init_pool()

            poll_info = db.get_poll(poll_id)
            if not poll_info:
                await interaction.response.send_message("❌ Poll not found.", ephemeral=True)
                return

            is_creator = poll_info['creator_id'] == interaction.user.id
            if not (is_creator or await has_permission_or_owner(interaction, manage_messages=True)):
                await interaction.response.send_message("❌ You don't have permission to update this poll.", ephemeral=True)
                return

            db.set_poll_show_responses(poll_id, show_responses)

            if poll_info.get('message_id'):
                channel = interaction.guild.get_channel(poll_info['channel_id'])
                if channel:
                    try:
                        await update_poll_embed(poll_id, channel, poll_info['message_id'])
                    except Exception as e:
                        logger.error(f"Could not refresh poll embed after toggling responses: {e}")

            status = "now showing" if show_responses else "no longer showing"
            await interaction.response.send_message(f"✅ Poll #{poll_id} is {status} responses in its panel.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error toggling show_responses: {e}")
            await interaction.response.send_message("❌ An error occurred while updating the poll.", ephemeral=True)

    @app_commands.command(name="close", description="Close a poll and prevent new responses")
    @app_commands.describe(poll_id="The ID of the poll to close")
    @owner_or_permissions(manage_messages=True)
    async def close(self, interaction: discord.Interaction, poll_id: int):
        """Close a poll and prevent further responses."""
        try:
            if not db.connection_pool:
                db.init_pool()

            poll_info = db.get_poll(poll_id)
            if not poll_info:
                await interaction.response.send_message("❌ Poll not found.", ephemeral=True)
                return

            if poll_info['creator_id'] != interaction.user.id and not await has_permission_or_owner(interaction, manage_messages=True):
                await interaction.response.send_message("❌ You don't have permission to close this poll.", ephemeral=True)
                return

            db.close_poll(poll_id)

            if poll_info.get('message_id'):
                try:
                    channel = interaction.guild.get_channel(poll_info['channel_id'])
                    if channel:
                        message = await channel.fetch_message(poll_info['message_id'])
                        embed = message.embeds[0] if message.embeds else discord.Embed()
                        embed.color = discord.Color.red()
                        embed.title = "📊 Poll (CLOSED)"
                        await message.edit(embed=embed, view=None)
                except Exception as e:
                    logger.error(f"Could not edit poll message: {e}")

            await interaction.response.send_message(f"✅ Poll #{poll_id} has been closed. No new responses will be accepted.", ephemeral=True)
            logger.info(f"📊 Poll {poll_id} closed by {interaction.user}")
        except Exception as e:
            logger.error(f"Error closing poll: {e}")
            await interaction.response.send_message("❌ An error occurred while closing the poll.", ephemeral=True)

    @app_commands.command(name="reopen", description="Reopen a closed poll to allow new responses")
    @app_commands.describe(poll_id="The ID of the poll to reopen")
    @owner_or_permissions(manage_messages=True)
    async def reopen(self, interaction: discord.Interaction, poll_id: int):
        """Reopen a closed poll to allow further responses."""
        try:
            if not db.connection_pool:
                db.init_pool()

            poll_info = db.get_poll(poll_id)
            if not poll_info:
                await interaction.response.send_message("❌ Poll not found.", ephemeral=True)
                return

            if poll_info['creator_id'] != interaction.user.id and not await has_permission_or_owner(interaction, manage_messages=True):
                await interaction.response.send_message("❌ You don't have permission to reopen this poll.", ephemeral=True)
                return

            if poll_info['is_active']:
                await interaction.response.send_message("❌ This poll is already open.", ephemeral=True)
                return

            db.reopen_poll(poll_id)

            if poll_info.get('message_id'):
                try:
                    channel = interaction.guild.get_channel(poll_info['channel_id'])
                    if channel:
                        message = await channel.fetch_message(poll_info['message_id'])
                        embed = message.embeds[0] if message.embeds else discord.Embed()
                        embed.color = discord.Color.blue()
                        embed.title = "📊 Poll"
                        await message.edit(embed=embed, view=PollView(poll_id, poll_info['question']))
                except Exception as e:
                    logger.error(f"Could not edit poll message: {e}")

            await interaction.response.send_message(f"✅ Poll #{poll_id} has been reopened. Responses are now accepted.", ephemeral=True)
            logger.info(f"📊 Poll {poll_id} reopened by {interaction.user}")
        except Exception as e:
            logger.error(f"Error reopening poll: {e}")
            await interaction.response.send_message("❌ An error occurred while reopening the poll.", ephemeral=True)

    @app_commands.command(name="refresh", description="Refresh a poll's button to fix interaction issues")
    @app_commands.describe(poll_id="The ID of the poll to refresh")
    async def refresh(self, interaction: discord.Interaction, poll_id: int):
        """Refresh a poll's button view to fix issues with old polls."""
        try:
            if not db.connection_pool:
                db.init_pool()

            poll_info = db.get_poll(poll_id)
            if not poll_info:
                await interaction.response.send_message("❌ Poll not found.", ephemeral=True)
                return

            if poll_info['creator_id'] != interaction.user.id and not await has_permission_or_owner(interaction, manage_messages=True):
                await interaction.response.send_message("❌ You don't have permission to refresh this poll.", ephemeral=True)
                return

            if not poll_info.get('message_id'):
                await interaction.response.send_message("❌ This poll doesn't have an associated message.", ephemeral=True)
                return

            try:
                channel = interaction.guild.get_channel(poll_info['channel_id'])
                if not channel:
                    await interaction.response.send_message("❌ Poll channel not found.", ephemeral=True)
                    return

                message = await channel.fetch_message(poll_info['message_id'])
                view = PollView(poll_id, poll_info['question']) if poll_info['is_active'] else ClosedPollView()
                await message.edit(view=view)

                await interaction.response.send_message(f"✅ Poll #{poll_id} has been refreshed! The button should work now.", ephemeral=True)
                logger.info(f"📊 Poll {poll_id} refreshed by {interaction.user}")
            except discord.NotFound:
                await interaction.response.send_message("❌ Poll message not found. It may have been deleted.", ephemeral=True)
            except Exception as e:
                logger.error(f"Error fetching/editing poll message: {e}")
                await interaction.response.send_message(f"❌ Could not refresh poll message: {str(e)[:100]}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error refreshing poll: {e}")
            await interaction.response.send_message("❌ An error occurred while refreshing the poll.", ephemeral=True)

    @app_commands.command(name="list", description="List all active polls in this server")
    @owner_or_permissions(manage_messages=True)
    async def list_polls(self, interaction: discord.Interaction):
        """List all active polls in the server."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        try:
            if not db.connection_pool:
                db.init_pool()

            polls = db.get_active_polls(interaction.guild.id)
            if not polls:
                await interaction.response.send_message("📊 No active polls in this server.", ephemeral=True)
                return

            embed = discord.Embed(title="📊 Active Polls", description=f"There are {len(polls)} active poll(s) in this server:", color=discord.Color.blue())
            for poll in polls[:25]:
                response_count = db.get_poll_response_count(poll['id'])
                embed.add_field(
                    name=f"Poll #{poll['id']}",
                    value=f"**Q:** {poll['question'][:100]}\n**Responses:** {response_count}\n**Channel:** <#{poll['channel_id']}>",
                    inline=False,
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error listing polls: {e}")
            await interaction.response.send_message("❌ An error occurred while listing polls.", ephemeral=True)

    @app_commands.command(name="wordcloud", description="Generate a word cloud from poll responses")
    @app_commands.describe(poll_id="The ID of the poll")
    async def wordcloud(self, interaction: discord.Interaction, poll_id: int):
        """Generate a word cloud visualization from all poll responses."""
        await interaction.response.defer()
        try:
            if not db.connection_pool:
                db.init_pool()

            poll_info = db.get_poll(poll_id)
            if not poll_info:
                await interaction.followup.send("❌ Poll not found.")
                return

            error = await can_view_poll_results(interaction, poll_info)
            if error:
                await interaction.followup.send(f"❌ {error}")
                return

            responses = db.get_poll_responses(poll_id)
            if not responses:
                await interaction.followup.send("❌ No responses yet. Word cloud requires at least one response.")
                return

            all_text = " ".join(r['response_text'] for r in responses)
            wordcloud = WordCloud(width=1200, height=600, background_color='white', colormap='viridis', relative_scaling=0.5, min_font_size=10).generate(all_text)

            plt.figure(figsize=(12, 6), facecolor='white')
            plt.imshow(wordcloud, interpolation='bilinear')
            plt.axis('off')
            plt.title(f"Word Cloud: {poll_info['question'][:50]}", fontsize=16, pad=20)
            plt.tight_layout(pad=0)

            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
            buffer.seek(0)
            plt.close()

            file = discord.File(buffer, filename=f"wordcloud_poll_{poll_id}.png")
            embed = discord.Embed(
                title=f"📊 Word Cloud - Poll #{poll_id}",
                description=f"**Question:** {poll_info['question']}\n**Total Responses:** {len(responses)}",
                color=discord.Color.purple(), timestamp=dt.datetime.now(dt.timezone.utc),
            )
            embed.set_image(url=f"attachment://wordcloud_poll_{poll_id}.png")
            embed.set_footer(text="Word cloud shows most frequently used words")

            await interaction.followup.send(embed=embed, file=file)
            logger.info(f"📊 Generated word cloud for poll {poll_id} requested by {interaction.user}")
        except Exception as e:
            logger.error(f"Error generating word cloud: {e}")
            traceback.print_exc()
            await interaction.followup.send(f"❌ An error occurred while generating the word cloud: {str(e)[:200]}")

    @app_commands.command(name="stats", description="Generate statistics and visualizations from poll responses")
    @app_commands.describe(poll_id="The ID of the poll")
    async def stats(self, interaction: discord.Interaction, poll_id: int):
        """Generate bar chart statistics showing response distribution and counts."""
        await interaction.response.defer()
        try:
            if not db.connection_pool:
                db.init_pool()

            poll_info = db.get_poll(poll_id)
            if not poll_info:
                await interaction.followup.send("❌ Poll not found.")
                return

            error = await can_view_poll_results(interaction, poll_info)
            if error:
                await interaction.followup.send(f"❌ {error}")
                return

            responses = db.get_poll_responses(poll_id)
            if not responses:
                await interaction.followup.send("❌ No responses yet. Statistics require at least one response.")
                return

            response_counts = Counter(r['response_text'].strip().lower() for r in responses)
            top_responses = response_counts.most_common(10)

            fig, ax = plt.subplots(figsize=(12, 8), facecolor='white')
            labels = []
            counts = []
            for response_text, count in top_responses:
                display_text = response_text[:40] + ("..." if len(response_text) > 40 else "")
                labels.append(display_text)
                counts.append(count)

            bars = ax.barh(range(len(labels)), counts, color='#5865F2')
            ax.set_yticks(range(len(labels)))
            ax.set_yticklabels(labels)
            ax.set_xlabel('Number of Responses', fontsize=12)
            ax.set_title(f'Poll Response Distribution: {poll_info["question"][:50]}', fontsize=14, pad=20)
            ax.invert_yaxis()

            for bar, count in zip(bars, counts):
                width = bar.get_width()
                ax.text(width + 0.1, bar.get_y() + bar.get_height() / 2, f'{count}', ha='left', va='center', fontsize=10, fontweight='bold')

            plt.tight_layout()

            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
            buffer.seek(0)
            plt.close()

            file = discord.File(buffer, filename=f"stats_poll_{poll_id}.png")
            total_responses = len(responses)
            unique_responses = len(response_counts)

            embed = discord.Embed(
                title=f"📊 Poll Statistics - Poll #{poll_id}", description=f"**Question:** {poll_info['question']}",
                color=discord.Color.blue(), timestamp=dt.datetime.now(dt.timezone.utc),
            )
            embed.add_field(
                name="📈 Summary",
                value=f"**Total Responses:** {total_responses}\n**Unique Responses:** {unique_responses}\n**Most Common:** {top_responses[0][0][:50]} ({top_responses[0][1]} times)",
                inline=False,
            )
            embed.set_image(url=f"attachment://stats_poll_{poll_id}.png")
            embed.set_footer(text=f"Showing top {len(top_responses)} responses")

            await interaction.followup.send(embed=embed, file=file)
            logger.info(f"📊 Generated statistics for poll {poll_id} requested by {interaction.user}")
        except Exception as e:
            logger.error(f"Error generating poll statistics: {e}")
            traceback.print_exc()
            await interaction.followup.send(f"❌ An error occurred while generating statistics: {str(e)[:200]}")
