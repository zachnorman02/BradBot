import discord
from discord.ext import commands
from discord import app_commands
import os
import re
from dotenv import load_dotenv
from websites import fix_link_async, get_site_name

# Load environment variables from .env file
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# In-memory settings: {guild_id: include_original_message}
settings = {}

@bot.event
async def on_ready():
    print(f'{bot.user} has logged in!')
    try:
        # Sync slash commands
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.event
async def on_message(message):
    # Don't respond to bot messages
    if message.author.bot:
        return
    
    # Process commands first
    await bot.process_commands(message)
    
    # Check if message contains URLs
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, message.content)
    
    if not urls:
        return
    
    # Start with the original message content
    fixed_content = message.content
    any_links_fixed = False
    
    for url in urls:
        # Try to fix the link
        fixed_url = await fix_link_async(url)
        if fixed_url:
            # Get the platform name for markdown formatting
            site_name = get_site_name(url)
            # Create markdown link with platform name as the text
            markdown_link = f"[{site_name}]({fixed_url})"
            # Replace the original URL with the markdown formatted link
            fixed_content = fixed_content.replace(url, markdown_link)
            any_links_fixed = True
    
    # Send the fixed message if any links were replaced
    if any_links_fixed:
        # Create the response with user ping and fixed content
        response = f"{message.author.mention}: {fixed_content}"
        
        # Send the fixed message
        await message.channel.send(response, silent=True)
        
        # Delete the original message
        try:
            await message.delete()
        except discord.Forbidden:
            # Bot doesn't have permission to delete messages
            await message.channel.send("*Note: I don't have permission to delete the original message*")
        except discord.NotFound:
            # Message was already deleted
            pass

# Slash command for setting include original
@bot.tree.command(name="set_include_original", description="Set whether to include original message")
@app_commands.describe(value="Whether to include the original message")
async def set_include_original(interaction: discord.Interaction, value: bool):
    settings[interaction.guild_id] = value
    await interaction.response.send_message(f"Set include_original_message to {value} for this server.")

# Manual sync command (useful for testing) - keep as text command
@bot.command()
@commands.is_owner()
async def sync(ctx):
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} command(s)")
    except Exception as e:
        await ctx.send(f"Failed to sync: {e}")

# Use environment variable for token
bot.run(os.getenv("DISCORD_TOKEN"))