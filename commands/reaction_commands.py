"""Reaction checking and rules agreement command groups"""
import discord
from discord import app_commands
from typing import Optional
import re

from database import db
from utils.logger import logger
from utils.interaction_helpers import require_guild, send_error, send_success, send_info


class ReactionGroup(app_commands.Group):
    """Commands for checking message reactions"""
    
    def __init__(self):
        super().__init__(name="reaction", description="Check user reactions on messages")
    
    @app_commands.command(name="check", description="Check if a user reacted to a specific message")
    @app_commands.describe(
        message_id="The ID of the message to check",
        user="The user to check reactions for"
    )
    async def check_reaction(
        self,
        interaction: discord.Interaction,
        message_id: str,
        user: discord.User
    ):
        """Check if a user reacted to a specific message"""
        if not await require_guild(interaction):
            return
        
        try:
            # Try to find the message in the current channel first
            channel = interaction.channel
            try:
                message = await channel.fetch_message(int(message_id))
            except (discord.NotFound, discord.HTTPException):
                # Try to search in all text channels
                message = None
                for text_channel in interaction.guild.text_channels:
                    try:
                        message = await text_channel.fetch_message(int(message_id))
                        channel = text_channel
                        break
                    except (discord.NotFound, discord.HTTPException, discord.Forbidden):
                        continue
                
                if not message:
                    return await send_error(
                        interaction,
                        f"Could not find message with ID `{message_id}` in this server."
                    )
            
            # Check reactions
            user_reactions = []
            for reaction in message.reactions:
                users = [u async for u in reaction.users()]
                if user in users:
                    user_reactions.append(str(reaction.emoji))
            
            # Build response
            embed = discord.Embed(
                title="🔍 Reaction Check",
                color=discord.Color.blue()
            )
            embed.add_field(name="User", value=user.mention, inline=True)
            embed.add_field(name="Message", value=f"[Jump to message]({message.jump_url})", inline=True)
            
            if user_reactions:
                embed.add_field(
                    name="✅ Reactions Found",
                    value=" ".join(user_reactions),
                    inline=False
                )
                embed.color = discord.Color.green()
            else:
                embed.add_field(
                    name="❌ No Reactions",
                    value=f"{user.mention} has not reacted to this message.",
                    inline=False
                )
                embed.color = discord.Color.red()
            
            await interaction.response.send_message(embed=embed)
            
        except ValueError:
            await send_error(interaction, "Invalid message ID. Please provide a valid message ID.")
        except Exception as e:
            logger.error(f"Error checking reaction: {e}")
            await send_error(interaction, "An error occurred while checking reactions.")
    
    @app_commands.command(name="check_url", description="Check if a user reacted to a message using its URL")
    @app_commands.describe(
        message_url="The URL of the message (right-click → Copy Message Link)",
        user="The user to check reactions for"
    )
    async def check_reaction_url(
        self,
        interaction: discord.Interaction,
        message_url: str,
        user: discord.User
    ):
        """Check if a user reacted to a message using the message URL"""
        if not await require_guild(interaction):
            return
        
        # Parse message URL: https://discord.com/channels/guild_id/channel_id/message_id
        pattern = r'https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)'
        match = re.match(pattern, message_url)
        
        if not match:
            return await send_error(
                interaction,
                "Invalid message URL. Right-click a message and select 'Copy Message Link'."
            )
        
        guild_id, channel_id, message_id = match.groups()
        
        if int(guild_id) != interaction.guild.id:
            return await send_error(interaction, "That message is from a different server.")
        
        try:
            channel = interaction.guild.get_channel(int(channel_id))
            if not channel:
                return await send_error(interaction, "Could not find that channel in this server.")
            
            message = await channel.fetch_message(int(message_id))
            
            # Check reactions
            user_reactions = []
            for reaction in message.reactions:
                users = [u async for u in reaction.users()]
                if user in users:
                    user_reactions.append(str(reaction.emoji))
            
            # Build response
            embed = discord.Embed(
                title="🔍 Reaction Check",
                color=discord.Color.blue()
            )
            embed.add_field(name="User", value=user.mention, inline=True)
            embed.add_field(name="Message", value=f"[Jump to message]({message.jump_url})", inline=True)
            
            if user_reactions:
                embed.add_field(
                    name="✅ Reactions Found",
                    value=" ".join(user_reactions),
                    inline=False
                )
                embed.color = discord.Color.green()
            else:
                embed.add_field(
                    name="❌ No Reactions",
                    value=f"{user.mention} has not reacted to this message.",
                    inline=False
                )
                embed.color = discord.Color.red()
            
            await interaction.response.send_message(embed=embed)
            
        except discord.NotFound:
            await send_error(interaction, "Could not find that message.")
        except discord.Forbidden:
            await send_error(interaction, "I don't have permission to access that channel.")
        except Exception as e:
            logger.error(f"Error checking reaction from URL: {e}")
            await send_error(interaction, "An error occurred while checking reactions.")


class RulesAgreementGroup(app_commands.Group):
    """Commands for managing rules agreement tracking"""
    
    def __init__(self):
        super().__init__(name="rules_agreement", description="Manage rules agreement tracking")
    
    @app_commands.command(name="setup", description="Set up rules messages to track (Admin only)")
    @app_commands.describe(
        message_urls="Message URLs separated by commas or newlines"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_rules(
        self,
        interaction: discord.Interaction,
        message_urls: str
    ):
        """Set up which messages to track for rules agreement"""
        if not await require_guild(interaction):
            return
        
        # Parse multiple URLs
        urls = [url.strip() for url in re.split(r'[,\n]+', message_urls) if url.strip()]
        
        if not urls:
            return await send_error(interaction, "Please provide at least one message URL.")
        
        pattern = r'https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)'
        message_data = []
        
        for url in urls:
            match = re.match(pattern, url)
            if not match:
                return await send_error(
                    interaction,
                    f"Invalid message URL: `{url}`\nRight-click messages and select 'Copy Message Link'."
                )
            
            guild_id, channel_id, message_id = match.groups()
            
            if int(guild_id) != interaction.guild.id:
                return await send_error(
                    interaction,
                    f"Message URL is from a different server: `{url}`"
                )
            
            message_data.append({
                'channel_id': int(channel_id),
                'message_id': int(message_id),
                'url': url
            })
        
        # Verify all messages exist
        verified_messages = []
        for data in message_data:
            try:
                channel = interaction.guild.get_channel(data['channel_id'])
                if not channel:
                    return await send_error(
                        interaction,
                        f"Could not find channel for message: `{data['url']}`"
                    )
                
                message = await channel.fetch_message(data['message_id'])
                verified_messages.append({
                    'channel_id': data['channel_id'],
                    'message_id': data['message_id'],
                    'jump_url': message.jump_url
                })
            except discord.NotFound:
                return await send_error(
                    interaction,
                    f"Could not find message: `{data['url']}`"
                )
            except discord.Forbidden:
                return await send_error(
                    interaction,
                    f"I don't have permission to access the channel for: `{data['url']}`"
                )
        
        # Store in database
        db.set_rules_agreement_messages(interaction.guild.id, verified_messages)
        
        embed = discord.Embed(
            title="✅ Rules Agreement Setup Complete",
            description=f"Tracking {len(verified_messages)} message(s) for rules agreement.",
            color=discord.Color.green()
        )
        
        for i, msg_data in enumerate(verified_messages, 1):
            embed.add_field(
                name=f"Message {i}",
                value=f"[Jump to message]({msg_data['jump_url']})",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
        logger.info(f"Rules agreement setup by {interaction.user} with {len(verified_messages)} messages")
    
    @app_commands.command(name="check", description="Check which rules messages a user has reacted to")
    @app_commands.describe(user="The user to check")
    async def check_agreement(
        self,
        interaction: discord.Interaction,
        user: discord.User
    ):
        """Check which rules messages a user has agreed to by reacting"""
        if not await require_guild(interaction):
            return
        
        rules_messages = db.get_rules_agreement_messages(interaction.guild.id)
        
        if not rules_messages:
            return await send_error(
                interaction,
                "Rules agreement tracking is not set up. Use `/rules_agreement setup` first."
            )
        
        await interaction.response.defer()
        
        # Check each message for reactions
        results = []
        for msg_data in rules_messages:
            try:
                channel = interaction.guild.get_channel(msg_data['channel_id'])
                if not channel:
                    results.append({
                        'message_id': msg_data['message_id'],
                        'reacted': False,
                        'error': 'Channel not found',
                        'jump_url': msg_data.get('jump_url', '#')
                    })
                    continue
                
                message = await channel.fetch_message(msg_data['message_id'])
                
                # Check if user reacted
                user_reacted = False
                user_reactions = []
                for reaction in message.reactions:
                    users = [u async for u in reaction.users()]
                    if user in users:
                        user_reacted = True
                        user_reactions.append(str(reaction.emoji))
                
                results.append({
                    'message_id': msg_data['message_id'],
                    'reacted': user_reacted,
                    'reactions': user_reactions,
                    'jump_url': message.jump_url
                })
                
            except discord.NotFound:
                results.append({
                    'message_id': msg_data['message_id'],
                    'reacted': False,
                    'error': 'Message not found',
                    'jump_url': msg_data.get('jump_url', '#')
                })
            except discord.Forbidden:
                results.append({
                    'message_id': msg_data['message_id'],
                    'reacted': False,
                    'error': 'No permission',
                    'jump_url': msg_data.get('jump_url', '#')
                })
        
        # Build response
        agreed_count = sum(1 for r in results if r['reacted'])
        total_count = len(results)
        all_agreed = agreed_count == total_count
        
        embed = discord.Embed(
            title="📋 Rules Agreement Check",
            description=f"**User:** {user.mention}\n**Status:** {agreed_count}/{total_count} messages reacted",
            color=discord.Color.green() if all_agreed else discord.Color.orange()
        )
        
        for i, result in enumerate(results, 1):
            if result['reacted']:
                status = f"✅ Agreed ({' '.join(result['reactions'])})"
            elif 'error' in result:
                status = f"⚠️ {result['error']}"
            else:
                status = "❌ Not agreed"
            
            embed.add_field(
                name=f"Message {i}",
                value=f"{status}\n[Jump to message]({result['jump_url']})",
                inline=False
            )
        
        if all_agreed:
            embed.set_footer(text="✅ User has agreed to all rules!")
        else:
            embed.set_footer(text="⚠️ User has not agreed to all rules")
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="status", description="Show current rules agreement configuration")
    async def show_status(self, interaction: discord.Interaction):
        """Show which messages are being tracked for rules agreement"""
        if not await require_guild(interaction):
            return
        
        rules_messages = db.get_rules_agreement_messages(interaction.guild.id)
        
        if not rules_messages:
            return await send_info(
                interaction,
                "Rules agreement tracking is not set up.\n"
                "Administrators can use `/rules_agreement setup` to configure it."
            )
        
        embed = discord.Embed(
            title="📋 Rules Agreement Configuration",
            description=f"Tracking {len(rules_messages)} message(s) for rules agreement.",
            color=discord.Color.blue()
        )
        
        for i, msg_data in enumerate(rules_messages, 1):
            jump_url = msg_data.get('jump_url', '#')
            embed.add_field(
                name=f"Message {i}",
                value=f"Channel: <#{msg_data['channel_id']}>\n[Jump to message]({jump_url})",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="clear", description="Clear rules agreement configuration (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def clear_rules(self, interaction: discord.Interaction):
        """Clear the rules agreement tracking configuration"""
        if not await require_guild(interaction):
            return
        
        rules_messages = db.get_rules_agreement_messages(interaction.guild.id)
        
        if not rules_messages:
            return await send_info(interaction, "Rules agreement tracking is not currently set up.")
        
        db.clear_rules_agreement_messages(interaction.guild.id)
        
        await send_success(
            interaction,
            f"✅ Cleared rules agreement tracking ({len(rules_messages)} message(s) removed)."
        )
        logger.info(f"Rules agreement cleared by {interaction.user} in {interaction.guild.name}")


def setup_reaction_commands(tree: app_commands.CommandTree):
    """Add reaction and rules agreement command groups to the tree"""
    tree.add_command(ReactionGroup())
    tree.add_command(RulesAgreementGroup())
