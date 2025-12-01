"""
Message purge/deletion utilities with advanced date/time filtering
"""
import discord
import datetime as dt
import re
from typing import Literal


async def parse_purge_dates(
    start_date: str | None,
    end_date: str | None,
    start_time: str | None,
    end_time: str | None,
    timezone_offset: int
) -> tuple[dt.datetime | None, dt.datetime | None, str | None]:
    """
    Parse and validate date/time inputs for purge command.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format  
        start_time: Start time in HH:MM format
        end_time: End time in HH:MM format
        timezone_offset: Hours offset from UTC
        
    Returns:
        Tuple of (start_datetime, end_datetime, error_message)
        error_message is None if parsing succeeds
    """
    try:
        # Parse start datetime
        if start_date:
            start_dt_str = f"{start_date} {start_time or '00:00'}"
            start_dt = dt.datetime.strptime(start_dt_str, "%Y-%m-%d %H:%M")
            # Adjust for timezone
            start_dt = start_dt - dt.timedelta(hours=timezone_offset)
            start_dt = start_dt.replace(tzinfo=dt.timezone.utc)
        else:
            start_dt = None
            
        # Parse end datetime
        if end_date:
            end_dt_str = f"{end_date} {end_time or '23:59'}"
            end_dt = dt.datetime.strptime(end_dt_str, "%Y-%m-%d %H:%M")
            # Adjust for timezone
            end_dt = end_dt - dt.timedelta(hours=timezone_offset)
            end_dt = end_dt.replace(tzinfo=dt.timezone.utc)
        else:
            end_dt = None
            
        return start_dt, end_dt, None
        
    except ValueError as e:
        return None, None, f"Invalid date/time format: {e}"


async def purge_messages_in_range(
    channel: discord.TextChannel,
    user: discord.User | None = None,
    start_datetime: dt.datetime | None = None,
    end_datetime: dt.datetime | None = None,
    scope: Literal["channel", "server"] = "channel",
    interaction: discord.Interaction = None
) -> dict[str, int]:
    """
    Delete messages matching the specified criteria.
    
    Args:
        channel: Channel to delete messages from
        user: Only delete messages from this user (None = all users)
        start_datetime: Delete messages after this time
        end_datetime: Delete messages before this time
        scope: "channel" or "server" (search all channels)
        interaction: Discord interaction for updates
        
    Returns:
        Dictionary with deletion statistics
    """
    deleted_count = 0
    channels_checked = 0
    
    # Determine which channels to check
    if scope == "server" and interaction:
        channels_to_check = [ch for ch in interaction.guild.text_channels 
                            if ch.permissions_for(interaction.guild.me).read_message_history]
    else:
        channels_to_check = [channel]
    
    for ch in channels_to_check:
        channels_checked += 1
        
        # Build message filter
        def check_message(msg: discord.Message) -> bool:
            # Check user filter
            if user and msg.author.id != user.id:
                return False
                
            # Check time range
            if start_datetime and msg.created_at < start_datetime:
                return False
            if end_datetime and msg.created_at > end_datetime:
                return False
                
            return True
        
        try:
            # Fetch and filter messages
            async for message in ch.history(limit=None, oldest_first=False):
                if check_message(message):
                    try:
                        await message.delete()
                        deleted_count += 1
                        
                        # Update status every 10 deletions
                        if deleted_count % 10 == 0 and interaction:
                            await interaction.edit_original_response(
                                content=f"🗑️ Deleting messages... ({deleted_count} deleted so far)"
                            )
                    except discord.Forbidden:
                        pass  # Skip messages we can't delete
                    except discord.HTTPException:
                        pass  # Skip messages that error
                        
        except discord.Forbidden:
            continue  # Skip channels we can't access
    
    return {
        "deleted": deleted_count,
        "channels_checked": channels_checked
    }


def generate_timezone_choices(current: str) -> list[str]:
    """Generate timezone offset autocomplete choices"""
    # Common timezone offsets
    timezones = {
        "-12": "Baker Island Time (UTC-12)",
        "-11": "Samoa Standard Time (UTC-11)",
        "-10": "Hawaii-Aleutian Standard Time (UTC-10)",
        "-9": "Alaska Standard Time (UTC-9)",
        "-8": "Pacific Standard Time (UTC-8)",
        "-7": "Mountain Standard Time (UTC-7)",
        "-6": "Central Standard Time (UTC-6)",
        "-5": "Eastern Standard Time (UTC-5)",
        "-4": "Atlantic Standard Time (UTC-4)",
        "-3": "Argentina Time (UTC-3)",
        "-2": "South Georgia Time (UTC-2)",
        "-1": "Azores Time (UTC-1)",
        "0": "UTC / GMT (UTC+0)",
        "1": "Central European Time (UTC+1)",
        "2": "Eastern European Time (UTC+2)",
        "3": "Moscow Time (UTC+3)",
        "4": "Gulf Standard Time (UTC+4)",
        "5": "Pakistan Standard Time (UTC+5)",
        "6": "Bangladesh Standard Time (UTC+6)",
        "7": "Indochina Time (UTC+7)",
        "8": "China Standard Time (UTC+8)",
        "9": "Japan Standard Time (UTC+9)",
        "10": "Australian Eastern Standard Time (UTC+10)",
        "11": "Solomon Islands Time (UTC+11)",
        "12": "New Zealand Standard Time (UTC+12)",
    }
    
    # Filter based on current input
    if current:
        return [tz for tz in timezones.keys() if tz.startswith(current)]
    return list(timezones.keys())


def generate_date_autocomplete(current: str) -> list[str]:
    """Generate date autocomplete suggestions"""
    today = dt.datetime.now().date()
    suggestions = []
    
    # Add common date suggestions
    suggestions.append(today.strftime("%Y-%m-%d"))  # Today
    suggestions.append((today - dt.timedelta(days=1)).strftime("%Y-%m-%d"))  # Yesterday
    suggestions.append((today - dt.timedelta(weeks=1)).strftime("%Y-%m-%d"))  # 1 week ago
    suggestions.append((today - dt.timedelta(days=30)).strftime("%Y-%m-%d"))  # 1 month ago
    
    # Filter based on current input
    if current:
        return [date for date in suggestions if date.startswith(current)]
    return suggestions
