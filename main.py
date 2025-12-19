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
    IssuesGroup,
    ConversionGroup,
    PollGroup,
    UtilityGroup,
    VoiceGroup,
    AlarmGroup,
    timestamp_command,
    echo_command
)

# Import poll views
from commands.poll_commands import PollView
from commands.admin_commands import AdminSettingsView
from commands.issues_commands import IssuePanelView

# Import core functionality
from core import (
    daily_booster_role_check,
    poll_auto_close_check,
    poll_results_refresh,
    reminder_check,
    timer_check,
    on_member_update_handler,
    handle_reply_notification,
    process_message_links,
    send_processed_message,
    handle_message_mirror,
    handle_message_edit,
    handle_message_delete
)
from utils.ffmpeg_helper import ensure_ffmpeg, which_ffmpeg

# Import helpers for standalone commands
from utils.timestamp_helpers import TimestampStyle
from utils.secrets_manager import load_secret_env

# Load environment variables from .env file
load_dotenv()
load_secret_env()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=":", intents=intents)

# Add command groups to the tree
bot.tree.add_command(EmojiGroup(bot))
bot.tree.add_command(BoosterGroup())
bot.tree.add_command(SettingsGroup())
bot.tree.add_command(AdminGroup())
bot.tree.add_command(IssuesGroup())
bot.tree.add_command(ConversionGroup())
bot.tree.add_command(PollGroup(name="poll", description="Create and manage text-response polls"))
bot.tree.add_command(UtilityGroup(name="utility", description="Reminders and timers"))
bot.tree.add_command(VoiceGroup())
bot.tree.add_command(AlarmGroup())


# ============================================================================
# EVENT HANDLERS
# ============================================================================

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """Handle member updates - delegate to core module"""
    await on_member_update_handler(before, after)

@bot.event
async def on_member_join(member: discord.Member):
    """Handle new members joining - check if they should be auto-kicked/banned"""
    guild = member.guild
    
    # Don't apply to bots
    if member.bot:
        return
    
    # Check if auto-kick for single-server members is enabled
    kick_enabled = db.get_guild_setting(guild.id, 'auto_kick_single_server', 'false').lower() == 'true'
    ban_enabled = db.get_guild_setting(guild.id, 'auto_ban_single_server', 'false').lower() == 'true'
    
    if not kick_enabled and not ban_enabled:
        return  # Feature disabled
    
    # Check if member is only in this server (and no other mutual servers with bot)
    mutual_guilds = member.mutual_guilds
    if len(mutual_guilds) == 1:  # Only in this server
        try:
            if ban_enabled:
                await member.ban(reason="Auto-ban: Member is only in this server with bot")
                print(f"Auto-banned {member} ({member.id}) from {guild.name} - single server member")
            elif kick_enabled:
                await member.kick(reason="Auto-kick: Member is only in this server with bot")
                print(f"Auto-kicked {member} ({member.id}) from {guild.name} - single server member")
        except discord.Forbidden:
            print(f"Failed to kick/ban {member} - insufficient permissions")
        except Exception as e:
            print(f"Error auto-kicking/banning {member}: {e}")

@bot.event
async def on_ready():
    print(f'{bot.user} has logged in!')
    
    # Initialize database connection pool
    try:
        db.init_pool()
        # Test the connection with a simple query
        result = db.execute_query("SELECT 1")
        print(f"✅ Database connected successfully")
        
        # Initialize all database tables
        try:
            db.init_conditional_roles_tables()
            print(f"✅ Initialized conditional roles tables")
        except Exception as table_error:
            print(f"⚠️  Could not initialize conditional roles tables: {table_error}")

        # Initialize alarms table and schedule persisted alarms
        try:
            db.init_alarms_table()
            from commands.alarm_commands import schedule_all_existing_alarms
            schedule_all_existing_alarms(bot)
            print("✅ alarms initialized and scheduled")
        except Exception as e:
            print(f"⚠️  Could not initialize/schedule alarms: {e}")

        # Ensure ffmpeg is available (try auto-download on Linux if missing)
        try:
            ff = which_ffmpeg()
            if ff:
                print(f"✅ ffmpeg found at: {ff}")
            else:
                print("⚠️ ffmpeg not found on PATH — attempting to download static build (Linux only)")
                installed = ensure_ffmpeg()
                if installed:
                    print(f"✅ ffmpeg installed for runtime at: {installed}")
                else:
                    print("⚠️ ffmpeg not available. Please install ffmpeg on the host (apt/dnf/brew) or place binary in PATH.")
        except Exception as e:
            print(f"⚠️ ffmpeg check/install failed: {e}")
        
        # Grant admin permissions on all tables
        try:
            db.execute_query("""
                GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA main TO admin
            """, fetch=False)
            print(f"✅ Granted admin privileges on all tables")
        except Exception as perm_error:
            print(f"⚠️  Could not grant admin privileges: {perm_error}")
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

    # Re-register persistent panels (admin + issues)
    try:
        db.init_persistent_panels_table()
        stored_panels = db.get_persistent_panels()
        restored_counts = {}
        for panel in stored_panels:
            metadata = panel.get('metadata') or {}
            custom_prefix = metadata.get('custom_id_prefix')
            guild = bot.get_guild(panel['guild_id'])
            if not guild:
                db.delete_persistent_panel(panel['message_id'])
                continue
            channel = guild.get_channel(panel['channel_id'])
            if not channel:
                db.delete_persistent_panel(panel['message_id'])
                continue
            try:
                await channel.fetch_message(panel['message_id'])
            except discord.NotFound:
                db.delete_persistent_panel(panel['message_id'])
                continue
            except Exception as fetch_error:
                print(f"⚠️  Could not verify panel message {panel['message_id']}: {fetch_error}")
                continue

            if panel['panel_type'] == 'admin_settings':
                view = AdminSettingsView(
                    guild_id=panel['guild_id'],
                    persistent=True,
                    custom_id_prefix=custom_prefix
                )
            elif panel['panel_type'] == 'issue_panel':
                view = IssuePanelView(
                    guild_id=panel['guild_id'],
                    custom_id_prefix=custom_prefix
                )
            else:
                print(f"⚠️  Unknown panel type {panel['panel_type']}, skipping.")
                continue

            bot.add_view(view, message_id=panel['message_id'])
            restored_counts[panel['panel_type']] = restored_counts.get(panel['panel_type'], 0) + 1

        if restored_counts:
            summary = ", ".join(f"{ptype}: {count}" for ptype, count in restored_counts.items())
            print(f"✅ Registered persistent panels ({summary})")
        else:
            print("ℹ️ No persistent panels to restore")
    except Exception as e:
        print(f"⚠️  Failed to register persistent panels: {e}")
    
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

    # Start poll results refresh task
    bot.loop.create_task(poll_results_refresh(bot))
    
    # Start reminder check task
    bot.loop.create_task(reminder_check(bot))
    
    # Start timer check task
    bot.loop.create_task(timer_check(bot))
    
@bot.event
async def on_message(message):
    """Process messages for link replacement, reply notifications, and mirroring"""
    if message.author.bot:
        return
    await bot.process_commands(message)
    
    # Handle replies to bot's messages - ping the original poster if they have notifications enabled
    await handle_reply_notification(message, bot)
    
    # Process message links for replacement and embeds
    processed_result = await process_message_links(message)
    
    # Send processed message if content was changed
    await send_processed_message(message, processed_result, bot)
    
    # Handle message mirroring to configured target channels
    await handle_message_mirror(message)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    """Handle message edits for mirrored messages"""
    try:
        print(f"[DEBUG] on_message_edit event: before_id={getattr(before, 'id', None)} after_id={getattr(after, 'id', None)} author_id={getattr(after.author, 'id', None)} guild_id={getattr(after.guild, 'id', None)} channel_id={getattr(after.channel, 'id', None)}")
    except Exception:
        # Defensive logging - ensure we never crash event handling
        print("[DEBUG] on_message_edit event fired (could not introspect message objects)")

    await handle_message_edit(before, after)


@bot.event
async def on_raw_message_edit(payload: discord.RawMessageUpdateEvent):
    """Fallback for message edits when the message isn't in the cache.

    This will fetch the edited message and call the same handler used by
    `on_message_edit`. `before` will be passed as `None` since we don't have
    the cached previous state.
    """
    try:
        print(f"[DEBUG] on_raw_message_edit fired: message_id={payload.message_id} channel_id={payload.channel_id} guild_id={payload.guild_id}")
        # Try to resolve channel and fetch the message
        channel = None
        if payload.guild_id:
            guild = bot.get_guild(payload.guild_id)
            if guild:
                channel = guild.get_channel(payload.channel_id)
        if not channel:
            channel = bot.get_channel(payload.channel_id)

        if not channel:
            print(f"[DEBUG] Could not resolve channel for raw edit: {payload.channel_id}")
            return

        try:
            after = await channel.fetch_message(payload.message_id)
        except Exception as e:
            print(f"[DEBUG] Failed to fetch edited message {payload.message_id}: {e}")
            return

        await handle_message_edit(None, after)
    except Exception as e:
        print(f"[DEBUG] on_raw_message_edit handler error: {e}")

@bot.event
async def on_message_delete(message: discord.Message):
    """Handle message deletions for mirrored messages"""
    await handle_message_delete(message)

@bot.event
async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent):
    """Clean up persistent panels when their source message is deleted."""
    try:
        if payload.message_id not in getattr(db, 'persistent_panel_ids', set()):
            return
        db.delete_persistent_panel(payload.message_id)
        print(f"🗑️ Removed persistent panel record for message {payload.message_id}")
    except Exception as e:
        print(f"⚠️  Error cleaning up persistent panel {payload.message_id}: {e}")

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


@bot.command(name="resync")
@commands.has_permissions(administrator=True)
async def resync_commands(ctx, scope: Literal["global", "guild"] = "global"):
    """Manual text-command sync for admins when slash syncs lag."""
    if scope == "guild" and not ctx.guild:
        await ctx.send("❌ Guild-only sync must be run inside a server.")
        return

    async with ctx.typing():
        try:
            if scope == "guild":
                synced = await bot.tree.sync(guild=ctx.guild)
                await ctx.send(f"✅ Synced {len(synced)} command(s) for **{ctx.guild.name}**.")
            else:
                synced = await bot.tree.sync()
                await ctx.send(f"✅ Globally synced {len(synced)} command(s).")
        except Exception as e:
            await ctx.send(f"❌ Failed to sync commands: {e}")


# ============================================================================
# STANDALONE SLASH COMMANDS  
# ============================================================================
@bot.tree.command(name="echo", description="Have the bot repeat a message in this channel")
@app_commands.describe(
    message="What should the bot say?",
    allow_mentions="Allow mentions in the echoed message (default: disabled)"
)
async def echo(
    interaction: discord.Interaction,
    message: str,
    allow_mentions: bool = False
):
    """Echo helper."""
    await echo_command(interaction, message, allow_mentions)


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
