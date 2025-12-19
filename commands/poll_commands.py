"""
Poll command group for creating text-response polls
"""
import discord
from discord import app_commands
from database import db
import datetime as dt
import io
import traceback
from collections import Counter
from wordcloud import WordCloud
import matplotlib
matplotlib.use('Agg')  # Use non-GUI backend
import matplotlib.pyplot as plt


async def update_poll_embed(poll_id: int, channel, message_id: int):
    """Helper function to update poll embed with current responses"""
    try:
        poll_info = db.get_poll(poll_id)
        if not poll_info:
            return
        
        message = await channel.fetch_message(message_id)
        if not message.embeds:
            return
        
        embed = message.embeds[0]
        
        # Get current response count
        response_count = db.get_poll_response_count(poll_id)
        
        # Update footer to show response count
        footer_text = embed.footer.text if embed.footer else ""
        if " • " in footer_text:
            # Remove old response count if exists (handle both old and new formats)
            parts = footer_text.split(" • ")
            # Take first two parts (Poll ID and Creator), ignore any existing response count
            if len(parts) >= 2:
                base_footer = f"{parts[0]} • {parts[1]}"
            else:
                base_footer = parts[0] if parts else f"Poll ID: {poll_id}"
        else:
            # Fallback if no footer or unexpected format
            base_footer = footer_text if footer_text else f"Poll ID: {poll_id}"
        
        embed.set_footer(text=f"{base_footer} • {response_count} response{'s' if response_count != 1 else ''}")
        
        # If show_responses is enabled, add/update responses field
        if poll_info['show_responses']:
            responses = db.get_poll_responses(poll_id)
            
            # Remove old responses field if it exists
            for i, field in enumerate(embed.fields):
                if field.name.startswith("📝 Responses"):
                    embed.remove_field(i)
                    break
            
            if response_count > 0:
                # Show first few responses
                response_preview = []
                for i, resp in enumerate(responses[:5]):  # Show max 5
                    preview_text = resp['response_text'][:100]
                    if len(resp['response_text']) > 100:
                        preview_text += "..."
                    response_preview.append(f"**{resp['username']}**: {preview_text}")
                
                more_text = ""
                if response_count > 5:
                    more_text = f"\n*...and {response_count - 5} more*"
                
                embed.add_field(
                    name=f"📝 Responses ({response_count})",
                    value="\n\n".join(response_preview) + more_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="📝 Responses (0)",
                    value="*No responses yet*",
                    inline=False
                )
        
        await message.edit(embed=embed)
    except Exception as e:
        print(f"Error updating poll embed: {e}")


class ResponseModal(discord.ui.Modal, title="Submit Your Response"):
    """Modal for users to submit their poll responses"""
    
    def __init__(self, poll_id: int, question: str):
        super().__init__()
        self.poll_id = poll_id
        
        # Add text input for response
        self.response_input = discord.ui.TextInput(
            label=question[:45],  # Discord limits label to 45 chars
            style=discord.TextStyle.paragraph,
            placeholder="Type your response here...",
            max_length=1000,
            required=True
        )
        self.add_item(self.response_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle response submission"""
        try:
            print(f"[POLL] Response submission started for poll {self.poll_id} by {interaction.user}")
            
            # Store response in database
            try:
                db.store_poll_response(
                    poll_id=self.poll_id,
                    user_id=interaction.user.id,
                    username=str(interaction.user),
                    response_text=self.response_input.value
                )
            except Exception as e:
                if "already submitted" in str(e):
                    await interaction.response.send_message(
                        "❌ You have already submitted a response to this poll and multiple responses are not allowed.",
                        ephemeral=True
                    )
                    return
                raise
            
            print(f"[POLL] Response stored successfully")
            
            # Check if poll just closed due to max_responses
            poll_info = db.get_poll(self.poll_id)
            if not poll_info['is_active'] and poll_info['max_responses']:
                response_count = db.get_poll_response_count(self.poll_id)
                if response_count >= poll_info['max_responses']:
                    await interaction.response.send_message(
                        f"✅ Your response has been submitted!\n🔒 This poll has now closed (reached {poll_info['max_responses']} responses).",
                        ephemeral=True
                    )
                    
                    # Try to update the original message
                    try:
                        if poll_info['message_id']:
                            channel = interaction.channel
                            message = await channel.fetch_message(poll_info['message_id'])
                            
                            if message.embeds:
                                embed = message.embeds[0]
                                embed.color = discord.Color.red()
                                embed.title = "📊 Poll (CLOSED)"
                                
                                # Disable the button
                                view = discord.ui.View()
                                button = discord.ui.Button(
                                    label="Poll Closed",
                                    style=discord.ButtonStyle.secondary,
                                    disabled=True
                                )
                                view.add_item(button)
                                
                                await message.edit(embed=embed, view=view)
                    except Exception as e:
                        print(f"Error updating poll message after auto-close: {e}")
                    
                    return
            
            print(f"[POLL] Sending success message")
            await interaction.response.send_message(
                "✅ Your response has been submitted!",
                ephemeral=True
            )
            
            print(f"[POLL] Attempting to update poll embed")
            # Update poll embed to show response count and responses if enabled
            poll_info = db.get_poll(self.poll_id)
            if poll_info and poll_info['message_id']:
                await update_poll_embed(self.poll_id, interaction.channel, poll_info['message_id'])
            print(f"[POLL] Poll embed updated successfully")
                
        except Exception as e:
            print(f"[POLL ERROR] Error in response submission: {e}")
            traceback.print_exc()
            try:
                await interaction.response.send_message(
                    f"❌ Error: {str(e)}",
                    ephemeral=True
                )
            except:
                # If we can't respond, try followup
                try:
                    await interaction.followup.send(
                        f"❌ Error: {str(e)}",
                        ephemeral=True
                    )
                except Exception as followup_error:
                    print(f"[POLL ERROR] Could not send error message: {followup_error}")


class PollView(discord.ui.View):
    """View with a button to respond to the poll"""
    
    def __init__(self, poll_id: int, question: str):
        super().__init__(timeout=None)  # Persistent view
        self.poll_id = poll_id
        self.question = question
        
        # Create button with unique custom_id for this poll
        button = discord.ui.Button(
            label="Submit Response",
            style=discord.ButtonStyle.primary,
            emoji="📝",
            custom_id=f"poll_submit_{poll_id}"
        )
        button.callback = self.respond_button
        self.add_item(button)
    
    async def respond_button(self, interaction: discord.Interaction):
        """Show modal to collect user response"""
        print(f"[POLL] Button clicked for poll {self.poll_id} by {interaction.user}")
        modal = ResponseModal(self.poll_id, self.question)
        await interaction.response.send_modal(modal)


class PollGroup(app_commands.Group):
    """Commands for creating and managing text-response polls"""
    
    @app_commands.command(name="create", description="Create a new text-response poll")
    @app_commands.describe(
        question="The poll question or prompt",
        max_responses="Optional: Auto-close after this many responses",
        duration_minutes="Optional: Auto-close after this many minutes",
        show_responses="Show responses in the poll box (default: hidden)",
        public_results="Allow anyone to view results (default: yes, only creator+admins if no)",
        allow_multiple="Allow users to submit multiple responses (default: yes)"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def create_poll(self, interaction: discord.Interaction, question: str, 
                         max_responses: int = None, duration_minutes: int = None,
                         show_responses: bool = False, public_results: bool = True,
                         allow_multiple: bool = True):
        """Create a new poll where users can submit text responses"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Calculate close_at timestamp if duration provided
            close_at = None
            if duration_minutes:
                close_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=duration_minutes)
            
            # Create poll in database
            poll_id = db.create_poll(
                guild_id=interaction.guild.id,
                channel_id=interaction.channel.id,
                creator_id=interaction.user.id,
                question=question,
                max_responses=max_responses,
                close_at=close_at,
                show_responses=show_responses,
                public_results=public_results,
                allow_multiple_responses=allow_multiple
            )
            
            # Create embed for the poll
            embed = discord.Embed(
                title="📊 Poll",
                description=question,
                color=discord.Color.blue(),
                timestamp=dt.datetime.now(dt.timezone.utc)
            )
            embed.set_footer(text=f"Poll ID: {poll_id} • Created by {interaction.user.display_name} • 0 responses")
            embed.add_field(name="How to Respond", value="Click the **Submit Response** button below to share your answer!", inline=False)
            
            # Add poll settings info
            poll_settings = []
            if not allow_multiple:
                poll_settings.append("🔒 One response per person")
            if not public_results:
                poll_settings.append("🔐 Results visible to creator & admins only")
            
            if poll_settings:
                embed.add_field(name="⚙️ Settings", value="\n".join(poll_settings), inline=False)
            
            # Add auto-close info if applicable
            auto_close_info = []
            if max_responses:
                auto_close_info.append(f"• Closes after **{max_responses}** responses")
            if close_at:
                auto_close_info.append(f"• Closes <t:{int(close_at.timestamp())}:R>")
            
            if auto_close_info:
                embed.add_field(name="⏱️ Auto-Close", value="\n".join(auto_close_info), inline=False)
            
            # Create view with response button
            view = PollView(poll_id, question)
            
            # Send poll message
            await interaction.response.send_message(embed=embed, view=view)
            
            # Get the message and store its ID
            message = await interaction.original_response()
            db.update_poll_message_id(poll_id, message.id)
            
            print(f"📊 Poll created by {interaction.user} in {interaction.guild.name}: {question}")
            
        except Exception as e:
            print(f"Error creating poll: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while creating the poll. Please try again.",
                ephemeral=True
            )
    
    @app_commands.command(name="results", description="View responses to a poll")
    @app_commands.describe(poll_id="The ID of the poll (shown in the poll's footer)")
    async def view_results(self, interaction: discord.Interaction, poll_id: int):
        """View all responses to a poll"""
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Get poll info
            poll_info = db.get_poll(poll_id)
            if not poll_info:
                await interaction.response.send_message("❌ Poll not found.")
                return
            
            # Check permission based on public_results setting
            is_creator = poll_info['creator_id'] == interaction.user.id
            has_manage_perms = interaction.user.guild_permissions.manage_messages
            
            # Check if user has access to the poll's channel (skip for poll creator)
            if not is_creator:
                try:
                    poll_channel = interaction.guild.get_channel(poll_info['channel_id'])
                    if not poll_channel:
                        await interaction.response.send_message(
                            "❌ Poll channel not found.",
                            ephemeral=True
                        )
                        return
                    
                    # Check if user can view the channel
                    channel_perms = poll_channel.permissions_for(interaction.user)
                    if not channel_perms.view_channel:
                        await interaction.response.send_message(
                            "❌ You don't have access to the channel where this poll was created.",
                            ephemeral=True
                        )
                        return
                except Exception as e:
                    print(f"Error checking channel permissions: {e}")
                    await interaction.response.send_message(
                        "❌ Could not verify channel access.",
                        ephemeral=True
                    )
                    return
            
            if not poll_info['public_results'] and not is_creator and not has_manage_perms:
                await interaction.response.send_message(
                    "❌ This poll's results are only visible to the creator and admins.",
                    ephemeral=True
                )
                return
            
            # Get responses
            responses = db.get_poll_responses(poll_id)
            
            if not responses:
                await interaction.response.send_message(
                    f"📊 **Poll Results**\n**Question:** {poll_info['question']}\n\n*No responses yet.*"
                )
                return
            
            # Build response message
            embed = discord.Embed(
                title="📊 Poll Results",
                description=f"**Question:** {poll_info['question']}\n**Total Responses:** {len(responses)}",
                color=discord.Color.green(),
                timestamp=dt.datetime.now(dt.timezone.utc)
            )
            
            # Add responses (limit to prevent message being too long)
            for i, response in enumerate(responses[:25], 1):
                embed.add_field(
                    name=f"{i}. {response['username']}",
                    value=response['response_text'][:1024],  # Discord field value limit
                    inline=False
                )
            
            if len(responses) > 25:
                embed.set_footer(text=f"Showing first 25 of {len(responses)} responses")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Error viewing poll results: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while fetching poll results.",
                ephemeral=True
            )

    @app_commands.command(name="toggle_show_responses", description="Toggle whether a poll shows responses in its message")
    @app_commands.describe(
        poll_id="The ID of the poll to update",
        show_responses="Enable or disable showing responses in the poll embed"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
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
            has_manage = interaction.user.guild_permissions.manage_messages
            if not (is_creator or has_manage):
                await interaction.response.send_message(
                    "❌ You don't have permission to update this poll.",
                    ephemeral=True
                )
                return

            db.set_poll_show_responses(poll_id, show_responses)

            # Update message if it exists
            if poll_info.get('message_id'):
                channel = interaction.guild.get_channel(poll_info['channel_id'])
                if channel:
                    try:
                        await update_poll_embed(poll_id, channel, poll_info['message_id'])
                    except Exception as e:
                        print(f"[POLL] Could not refresh poll embed after toggling responses: {e}")

            status = "now showing" if show_responses else "no longer showing"
            await interaction.response.send_message(
                f"✅ Poll #{poll_id} is {status} responses in its panel.",
                ephemeral=True
            )
        except Exception as e:
            print(f"[POLL] Error toggling show_responses: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating the poll.",
                ephemeral=True
            )
    
    @app_commands.command(name="close", description="Close a poll and prevent new responses")
    @app_commands.describe(poll_id="The ID of the poll to close")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def close_poll(self, interaction: discord.Interaction, poll_id: int):
        """Close a poll and prevent further responses"""
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Get poll info
            poll_info = db.get_poll(poll_id)
            if not poll_info:
                await interaction.response.send_message("❌ Poll not found.", ephemeral=True)
                return
            
            # Check if user has permission (creator or manage messages)
            if poll_info['creator_id'] != interaction.user.id and not interaction.user.guild_permissions.manage_messages:
                await interaction.response.send_message(
                    "❌ You don't have permission to close this poll.",
                    ephemeral=True
                )
                return
            
            # Close the poll
            db.close_poll(poll_id)
            
            # Try to edit the original message to show it's closed
            if poll_info.get('message_id'):
                try:
                    channel = interaction.guild.get_channel(poll_info['channel_id'])
                    if channel:
                        message = await channel.fetch_message(poll_info['message_id'])
                        
                        # Update embed
                        embed = message.embeds[0] if message.embeds else discord.Embed()
                        embed.color = discord.Color.red()
                        embed.title = "📊 Poll (CLOSED)"
                        
                        # Remove the button
                        await message.edit(embed=embed, view=None)
                except Exception as e:
                    print(f"Could not edit poll message: {e}")
            
            await interaction.response.send_message(
                f"✅ Poll #{poll_id} has been closed. No new responses will be accepted.",
                ephemeral=True
            )
            
            print(f"📊 Poll {poll_id} closed by {interaction.user}")
            
        except Exception as e:
            print(f"Error closing poll: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while closing the poll.",
                ephemeral=True
            )
    
    @app_commands.command(name="reopen", description="Reopen a closed poll to allow new responses")
    @app_commands.describe(poll_id="The ID of the poll to reopen")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def reopen_poll(self, interaction: discord.Interaction, poll_id: int):
        """Reopen a closed poll to allow further responses"""
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Get poll info
            poll_info = db.get_poll(poll_id)
            if not poll_info:
                await interaction.response.send_message("❌ Poll not found.", ephemeral=True)
                return
            
            # Check if user has permission (creator or manage messages)
            if poll_info['creator_id'] != interaction.user.id and not interaction.user.guild_permissions.manage_messages:
                await interaction.response.send_message(
                    "❌ You don't have permission to reopen this poll.",
                    ephemeral=True
                )
                return
            
            # Check if poll is already active
            if poll_info['is_active']:
                await interaction.response.send_message(
                    "❌ This poll is already open.",
                    ephemeral=True
                )
                return
            
            # Reopen the poll
            db.reopen_poll(poll_id)
            
            # Try to edit the original message to show it's open
            if poll_info.get('message_id'):
                try:
                    channel = interaction.guild.get_channel(poll_info['channel_id'])
                    if channel:
                        message = await channel.fetch_message(poll_info['message_id'])
                        
                        # Update embed
                        embed = message.embeds[0] if message.embeds else discord.Embed()
                        embed.color = discord.Color.blue()
                        embed.title = "📊 Poll"
                        
                        # Add the button back
                        view = PollView(poll_id, poll_info['question'])
                        await message.edit(embed=embed, view=view)
                except Exception as e:
                    print(f"Could not edit poll message: {e}")
            
            await interaction.response.send_message(
                f"✅ Poll #{poll_id} has been reopened. Responses are now accepted.",
                ephemeral=True
            )
            
            print(f"📊 Poll {poll_id} reopened by {interaction.user}")
            
        except Exception as e:
            print(f"Error reopening poll: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while reopening the poll.",
                ephemeral=True
            )
    
    @app_commands.command(name="refresh", description="Refresh a poll's button to fix interaction issues")
    @app_commands.describe(poll_id="The ID of the poll to refresh")
    async def refresh_poll(self, interaction: discord.Interaction, poll_id: int):
        """Refresh a poll's button view to fix issues with old polls"""
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Get poll info
            poll_info = db.get_poll(poll_id)
            if not poll_info:
                await interaction.response.send_message("❌ Poll not found.", ephemeral=True)
                return
            
            # Check if user has permission (creator or manage messages)
            if poll_info['creator_id'] != interaction.user.id and not interaction.user.guild_permissions.manage_messages:
                await interaction.response.send_message(
                    "❌ You don't have permission to refresh this poll.",
                    ephemeral=True
                )
                return
            
            # Check if poll has a message
            if not poll_info.get('message_id'):
                await interaction.response.send_message(
                    "❌ This poll doesn't have an associated message.",
                    ephemeral=True
                )
                return
            
            # Fetch the original message
            try:
                channel = interaction.guild.get_channel(poll_info['channel_id'])
                if not channel:
                    await interaction.response.send_message(
                        "❌ Poll channel not found.",
                        ephemeral=True
                    )
                    return
                
                message = await channel.fetch_message(poll_info['message_id'])
                
                # Create new view with updated button
                if poll_info['is_active']:
                    view = PollView(poll_id, poll_info['question'])
                else:
                    # Poll is closed, use disabled button
                    view = discord.ui.View()
                    button = discord.ui.Button(
                        label="Poll Closed",
                        style=discord.ButtonStyle.secondary,
                        disabled=True
                    )
                    view.add_item(button)
                
                # Edit message with new view
                await message.edit(view=view)
                
                await interaction.response.send_message(
                    f"✅ Poll #{poll_id} has been refreshed! The button should work now.",
                    ephemeral=True
                )
                
                print(f"📊 Poll {poll_id} refreshed by {interaction.user}")
                
            except discord.NotFound:
                await interaction.response.send_message(
                    "❌ Poll message not found. It may have been deleted.",
                    ephemeral=True
                )
            except Exception as e:
                print(f"Error fetching/editing poll message: {e}")
                await interaction.response.send_message(
                    f"❌ Could not refresh poll message: {str(e)[:100]}",
                    ephemeral=True
                )
            
        except Exception as e:
            print(f"Error refreshing poll: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while refreshing the poll.",
                ephemeral=True
            )
    
    @app_commands.command(name="list", description="List all active polls in this server")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def list_polls(self, interaction: discord.Interaction):
        """List all active polls in the server"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Get active polls
            polls = db.get_active_polls(interaction.guild.id)
            
            if not polls:
                await interaction.response.send_message(
                    "📊 No active polls in this server.",
                    ephemeral=True
                )
                return
            
            # Build embed
            embed = discord.Embed(
                title="📊 Active Polls",
                description=f"There are {len(polls)} active poll(s) in this server:",
                color=discord.Color.blue()
            )
            
            for poll in polls[:25]:  # Limit to 25 to fit in embed
                response_count = db.get_poll_response_count(poll['id'])
                embed.add_field(
                    name=f"Poll #{poll['id']}",
                    value=f"**Q:** {poll['question'][:100]}\n**Responses:** {response_count}\n**Channel:** <#{poll['channel_id']}>",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error listing polls: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while listing polls.",
                ephemeral=True
            )
    
    @app_commands.command(name="wordcloud", description="Generate a word cloud from poll responses")
    @app_commands.describe(poll_id="The ID of the poll")
    async def wordcloud(self, interaction: discord.Interaction, poll_id: int):
        """Generate a word cloud visualization from all poll responses"""
        await interaction.response.defer()
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Get poll info
            poll_info = db.get_poll(poll_id)
            if not poll_info:
                await interaction.followup.send("❌ Poll not found.")
                return
            
            # Check permission based on public_results setting
            is_creator = poll_info['creator_id'] == interaction.user.id
            has_manage_perms = interaction.user.guild_permissions.manage_messages
            
            # Check if user has access to the poll's channel (skip for poll creator)
            if not is_creator:
                try:
                    poll_channel = interaction.guild.get_channel(poll_info['channel_id'])
                    if not poll_channel:
                        await interaction.followup.send(
                            "❌ Poll channel not found."
                        )
                        return
                    
                    # Check if user can view the channel
                    channel_perms = poll_channel.permissions_for(interaction.user)
                    if not channel_perms.view_channel:
                        await interaction.followup.send(
                            "❌ You don't have access to the channel where this poll was created."
                        )
                        return
                except Exception as e:
                    print(f"Error checking channel permissions: {e}")
                    await interaction.followup.send(
                        "❌ Could not verify channel access."
                    )
                    return
            
            if not poll_info['public_results'] and not is_creator and not has_manage_perms:
                await interaction.followup.send(
                    "❌ This poll's results are only visible to the creator and admins."
                )
                return
            
            # Get responses
            responses = db.get_poll_responses(poll_id)
            
            if not responses:
                await interaction.followup.send(
                    "❌ No responses yet. Word cloud requires at least one response."
                )
                return
            
            # Combine all response texts
            all_text = " ".join([r['response_text'] for r in responses])
            
            # Generate word cloud
            wordcloud = WordCloud(
                width=1200,
                height=600,
                background_color='white',
                colormap='viridis',
                relative_scaling=0.5,
                min_font_size=10
            ).generate(all_text)
            
            # Create matplotlib figure
            plt.figure(figsize=(12, 6), facecolor='white')
            plt.imshow(wordcloud, interpolation='bilinear')
            plt.axis('off')
            plt.title(f"Word Cloud: {poll_info['question'][:50]}", fontsize=16, pad=20)
            plt.tight_layout(pad=0)
            
            # Save to buffer
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
            buffer.seek(0)
            plt.close()
            
            # Create Discord file
            file = discord.File(buffer, filename=f"wordcloud_poll_{poll_id}.png")
            
            # Create embed
            embed = discord.Embed(
                title=f"📊 Word Cloud - Poll #{poll_id}",
                description=f"**Question:** {poll_info['question']}\n**Total Responses:** {len(responses)}",
                color=discord.Color.purple(),
                timestamp=dt.datetime.now(dt.timezone.utc)
            )
            embed.set_image(url=f"attachment://wordcloud_poll_{poll_id}.png")
            embed.set_footer(text="Word cloud shows most frequently used words")
            
            await interaction.followup.send(embed=embed, file=file)
            
            print(f"📊 Generated word cloud for poll {poll_id} requested by {interaction.user}")
            
        except Exception as e:
            print(f"Error generating word cloud: {e}")
            traceback.print_exc()
            await interaction.followup.send(
                f"❌ An error occurred while generating the word cloud: {str(e)[:200]}"
            )
    
    @app_commands.command(name="stats", description="Generate statistics and visualizations from poll responses")
    @app_commands.describe(poll_id="The ID of the poll")
    async def stats(self, interaction: discord.Interaction, poll_id: int):
        """Generate bar chart statistics showing response distribution and counts"""
        await interaction.response.defer()
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Get poll info
            poll_info = db.get_poll(poll_id)
            if not poll_info:
                await interaction.followup.send("❌ Poll not found.")
                return
            
            # Check permission based on public_results setting
            is_creator = poll_info['creator_id'] == interaction.user.id
            has_manage_perms = interaction.user.guild_permissions.manage_messages
            
            # Check if user has access to the poll's channel (skip for poll creator)
            if not is_creator:
                try:
                    poll_channel = interaction.guild.get_channel(poll_info['channel_id'])
                    if not poll_channel:
                        await interaction.followup.send(
                            "❌ Poll channel not found."
                        )
                        return
                    
                    # Check if user can view the channel
                    channel_perms = poll_channel.permissions_for(interaction.user)
                    if not channel_perms.view_channel:
                        await interaction.followup.send(
                            "❌ You don't have access to the channel where this poll was created."
                        )
                        return
                except Exception as e:
                    print(f"Error checking channel permissions: {e}")
                    await interaction.followup.send(
                        "❌ Could not verify channel access."
                    )
                    return
            
            if not poll_info['public_results'] and not is_creator and not has_manage_perms:
                await interaction.followup.send(
                    "❌ This poll's results are only visible to the creator and admins."
                )
                return
            
            # Get responses
            responses = db.get_poll_responses(poll_id)
            
            if not responses:
                await interaction.followup.send(
                    "❌ No responses yet. Statistics require at least one response."
                )
                return
            
            # Count response frequencies (normalize to lowercase and strip whitespace)
            response_counts = Counter()
            for r in responses:
                # Normalize: lowercase, strip whitespace
                normalized = r['response_text'].strip().lower()
                response_counts[normalized] += 1
            
            # Get top 10 most common responses
            top_responses = response_counts.most_common(10)
            
            # Create bar chart
            fig, ax = plt.subplots(figsize=(12, 8), facecolor='white')
            
            labels = []
            counts = []
            for response_text, count in top_responses:
                # Truncate long responses for display
                display_text = response_text[:40]
                if len(response_text) > 40:
                    display_text += "..."
                labels.append(display_text)
                counts.append(count)
            
            # Create horizontal bar chart
            bars = ax.barh(range(len(labels)), counts, color='#5865F2')
            ax.set_yticks(range(len(labels)))
            ax.set_yticklabels(labels)
            ax.set_xlabel('Number of Responses', fontsize=12)
            ax.set_title(f'Poll Response Distribution: {poll_info["question"][:50]}', fontsize=14, pad=20)
            ax.invert_yaxis()  # Highest count at top
            
            # Add count labels on bars
            for i, (bar, count) in enumerate(zip(bars, counts)):
                width = bar.get_width()
                ax.text(width + 0.1, bar.get_y() + bar.get_height()/2,
                       f'{count}',
                       ha='left', va='center', fontsize=10, fontweight='bold')
            
            plt.tight_layout()
            
            # Save to buffer
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
            buffer.seek(0)
            plt.close()
            
            # Create Discord file
            file = discord.File(buffer, filename=f"stats_poll_{poll_id}.png")
            
            # Create summary embed
            total_responses = len(responses)
            unique_responses = len(response_counts)
            
            embed = discord.Embed(
                title=f"📊 Poll Statistics - Poll #{poll_id}",
                description=f"**Question:** {poll_info['question']}",
                color=discord.Color.blue(),
                timestamp=dt.datetime.now(dt.timezone.utc)
            )
            
            embed.add_field(
                name="📈 Summary",
                value=f"**Total Responses:** {total_responses}\n**Unique Responses:** {unique_responses}\n**Most Common:** {top_responses[0][0][:50]} ({top_responses[0][1]} times)",
                inline=False
            )
            
            embed.set_image(url=f"attachment://stats_poll_{poll_id}.png")
            embed.set_footer(text=f"Showing top {len(top_responses)} responses")
            
            await interaction.followup.send(embed=embed, file=file)
            
            print(f"📊 Generated statistics for poll {poll_id} requested by {interaction.user}")
            
        except Exception as e:
            print(f"Error generating poll statistics: {e}")
            traceback.print_exc()
            await interaction.followup.send(
                f"❌ An error occurred while generating statistics: {str(e)[:200]}"
            )
