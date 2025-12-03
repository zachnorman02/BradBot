"""
Poll command group for creating text-response polls
"""
import discord
from discord import app_commands
from database import db
import datetime as dt
import io
from wordcloud import WordCloud
import matplotlib
matplotlib.use('Agg')  # Use non-GUI backend
import matplotlib.pyplot as plt


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
            # Store response in database
            db.store_poll_response(
                poll_id=self.poll_id,
                user_id=interaction.user.id,
                username=str(interaction.user),
                response_text=self.response_input.value
            )
            
            await interaction.response.send_message(
                "✅ Your response has been submitted!",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error storing poll response: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while submitting your response. Please try again.",
                ephemeral=True
            )


class PollView(discord.ui.View):
    """View with a button to respond to the poll"""
    
    def __init__(self, poll_id: int, question: str):
        super().__init__(timeout=None)  # Persistent view
        self.poll_id = poll_id
        self.question = question
    
    @discord.ui.button(label="Submit Response", style=discord.ButtonStyle.primary, emoji="📝")
    async def respond_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show modal to collect user response"""
        modal = ResponseModal(self.poll_id, self.question)
        await interaction.response.send_modal(modal)


class PollGroup(app_commands.Group):
    """Commands for creating and managing text-response polls"""
    
    @app_commands.command(name="create", description="Create a new text-response poll")
    @app_commands.describe(question="The poll question or prompt")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def create_poll(self, interaction: discord.Interaction, question: str):
        """Create a new poll where users can submit text responses"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Create poll in database
            poll_id = db.create_poll(
                guild_id=interaction.guild.id,
                channel_id=interaction.channel.id,
                creator_id=interaction.user.id,
                question=question
            )
            
            # Create embed for the poll
            embed = discord.Embed(
                title="📊 Poll",
                description=question,
                color=discord.Color.blue(),
                timestamp=dt.datetime.now(dt.timezone.utc)
            )
            embed.set_footer(text=f"Poll ID: {poll_id} • Created by {interaction.user.display_name}")
            embed.add_field(name="How to Respond", value="Click the **Submit Response** button below to share your answer!", inline=False)
            
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
    @app_commands.checks.has_permissions(manage_messages=True)
    async def view_results(self, interaction: discord.Interaction, poll_id: int):
        """View all responses to a poll"""
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Get poll info
            poll_info = db.get_poll(poll_id)
            if not poll_info:
                await interaction.response.send_message("❌ Poll not found.", ephemeral=True)
                return
            
            # Check if user has permission to view (creator or manage messages)
            if poll_info['creator_id'] != interaction.user.id and not interaction.user.guild_permissions.manage_messages:
                await interaction.response.send_message(
                    "❌ You don't have permission to view these results.",
                    ephemeral=True
                )
                return
            
            # Get responses
            responses = db.get_poll_responses(poll_id)
            
            if not responses:
                await interaction.response.send_message(
                    f"📊 **Poll Results**\n**Question:** {poll_info['question']}\n\n*No responses yet.*",
                    ephemeral=True
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
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error viewing poll results: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while fetching poll results.",
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
    @app_commands.checks.has_permissions(manage_messages=True)
    async def wordcloud(self, interaction: discord.Interaction, poll_id: int):
        """Generate a word cloud visualization from all poll responses"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Get poll info
            poll_info = db.get_poll(poll_id)
            if not poll_info:
                await interaction.followup.send("❌ Poll not found.", ephemeral=True)
                return
            
            # Check if user has permission to view (creator or manage messages)
            if poll_info['creator_id'] != interaction.user.id and not interaction.user.guild_permissions.manage_messages:
                await interaction.followup.send(
                    "❌ You don't have permission to view this poll's data.",
                    ephemeral=True
                )
                return
            
            # Get responses
            responses = db.get_poll_responses(poll_id)
            
            if not responses:
                await interaction.followup.send(
                    "❌ No responses yet. Word cloud requires at least one response.",
                    ephemeral=True
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
            
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)
            
            print(f"📊 Generated word cloud for poll {poll_id} requested by {interaction.user}")
            
        except Exception as e:
            print(f"Error generating word cloud: {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send(
                f"❌ An error occurred while generating the word cloud: {str(e)[:200]}",
                ephemeral=True
            )
