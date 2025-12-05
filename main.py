import discord
from discord.ext import commands
from discord import app_commands
import os
import datetime as dt
import asyncio
from typing import Literal
from dotenv import load_dotenv

# Import database
from database import db

# Import command groups
from commands import (
    EmojiGroup, 
    BoosterGroup, 
    AdminGroup, 
    SettingsGroup,
    PollGroup,
    UtilityGroup,
    tconvert_command,
    timestamp_command
)

# Import poll views
from commands.poll_commands import PollView

# Import core functionality
from core import (
    daily_booster_role_check,
    poll_auto_close_check,
    reminder_check,
    timer_check,
    on_member_update_handler,
    handle_reply_notification,
    process_message_links,
    send_processed_message
)

# Import helpers for standalone commands
from utils.timestamp_helpers import TimestampStyle
from utils.conversion_helpers import ConversionType

# Load environment variables from .env file
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=":", intents=intents)


# ============================================================================
# EVENT HANDLERS
# ============================================================================

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """Handle member updates - delegate to core module"""
    await on_member_update_handler(before, after)

@bot.event
async def on_ready():
    print(f'{bot.user} has logged in!')
    
    # Initialize database connection pool
    try:
        db.init_pool()
        # Test the connection with a simple query
        result = db.execute_query("SELECT 1")
        print(f"✅ Database connected successfully")
    except Exception as e:
        print(f"⚠️  Database initialization failed: {e}")
        print("   Reply notifications will not work until database is configured")
    
    # Re-register persistent views for active polls
    try:
        # Get all active polls
        active_polls = db.execute_query(
            "SELECT id, question FROM main.polls WHERE is_active = TRUE"
        )
        for poll_id, question in active_polls:
            view = PollView(poll_id, question)
            bot.add_view(view)
        print(f"✅ Registered {len(active_polls)} active poll view(s)")
    except Exception as e:
        print(f"⚠️  Failed to register poll views: {e}")
    
    # Add command groups to the tree
    bot.tree.add_command(EmojiGroup(name="emoji", description="Emoji and sticker management commands"))
    bot.tree.add_command(BoosterGroup())
    bot.tree.add_command(SettingsGroup(name="settings", description="User settings and preferences"))
    bot.tree.add_command(AdminGroup(name="admin", description="Admin server management commands"))
    bot.tree.add_command(PollGroup(name="poll", description="Create and manage text-response polls"))
    bot.tree.add_command(UtilityGroup(name="utility", description="Reminders and timers"))
    
    try:
        # Sync slash commands
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    
    # Start daily booster role check task
    bot.loop.create_task(daily_booster_role_check(bot))
    
    # Start poll auto-close check task
    bot.loop.create_task(poll_auto_close_check(bot))
    
    # Start reminder check task
    bot.loop.create_task(reminder_check(bot))
    
    # Start timer check task
    bot.loop.create_task(timer_check(bot))
    
@bot.event
async def on_message(message):
    """Process messages for link replacement and reply notifications"""
    if message.author.bot:
        return
    await bot.process_commands(message)
    
    # Handle replies to bot's messages - ping the original poster if they have notifications enabled
    await handle_reply_notification(message, bot)
    
    # Process message links for replacement and embeds
    processed_result = await process_message_links(message)
    
    # Send processed message if content was changed
    await send_processed_message(message, processed_result, bot)

# Manual sync command (useful for testing) - keep as text command
@bot.command()
@commands.is_owner()
async def sync(ctx):
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} command(s)")
    except Exception as e:
        await ctx.send(f"Failed to sync: {e}")

@bot.command()
@commands.is_owner()
async def clearcmds(ctx):
    """Clear all global commands and resync - use this to remove stale commands"""
    try:
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        await ctx.send("✅ Cleared all global commands and resynced")
    except Exception as e:
        await ctx.send(f"Failed to clear commands: {e}")


# ============================================================================
# STANDALONE SLASH COMMANDS  
# ============================================================================
@bot.tree.command(name="tconvert", description="Convert between testosterone cypionate and gel")
@app_commands.describe(
    starting_type="Type of testosterone (cypionate or gel)",
    dose="Dose amount (in mg or ml)",
    frequency="Frequency of dose (in days)"
)
@app_commands.choices(starting_type=[
    app_commands.Choice(name="Cypionate", value=ConversionType.CYPIONATE.value),
    app_commands.Choice(name="Gel", value=ConversionType.GEL.value)
])
async def tconvert(
    interaction: discord.Interaction,
    starting_type: str,
    dose: float,
    frequency: int
):
    """Converts between testosterone cypionate and gel doses."""
    await tconvert_command(interaction, starting_type, dose, frequency)

@bot.tree.command(name="timestamp", description="Generate a Discord timestamp")
@app_commands.describe(
    date="Date in YYYY-MM-DD format (optional, defaults to today)",
    time="Time in 24hr (13:00) or 12hr (1 PM, 1:00 PM) format (optional, defaults to current time)",
    style="Display style for the timestamp",
    timezone_offset="Hours behind UTC for the input time (e.g. -6 for CST, -4 for EDT, 1 for CET)"
)
async def timestamp(
    interaction: discord.Interaction,
    date: str = None,
    time: str = None,
    style: TimestampStyle = None,
    timezone_offset: int = 0
):
    """Creates a Discord timestamp that shows relative time and adapts to user's timezone."""
    await timestamp_command(interaction, date, time, style, timezone_offset)


# ============================================================================
# RUN BOT
# ============================================================================

bot.run(os.getenv("DISCORD_TOKEN"))
