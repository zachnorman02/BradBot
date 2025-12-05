"""
Timestamp generation and parsing utilities for Discord
"""
import enum
import datetime as dt


class TimestampStyle(str, enum.Enum):
    """Discord timestamp format styles"""
    SHORT_TIME = "t"          # 16:20
    LONG_TIME = "T"           # 16:20:30
    SHORT_DATE = "d"          # 20/04/2021
    LONG_DATE = "D"           # 20 April 2021
    SHORT_DATETIME = "f"      # 20 April 2021 16:20
    LONG_DATETIME = "F"       # Tuesday, 20 April 2021 16:20
    RELATIVE = "R"            # 2 months ago


def parse_time(time_str: str) -> dt.time | None:
    """
    Parse a time string in various formats.
    
    Args:
        time_str: Time string to parse
        
    Returns:
        Parsed time object or None if parsing fails
        
    Supported formats:
        - 24-hour: 13:00, 13:00:30
        - 12-hour: 1 PM, 1:00 PM, 1:00:30 PM
    """
    time_clean = time_str.strip().upper()
    
    time_formats = [
        "%H:%M:%S",      # 13:00:30 (24-hour with seconds)
        "%H:%M",         # 13:00 (24-hour)
        "%I:%M:%S %p",   # 1:00:30 PM (12-hour with seconds)
        "%I:%M %p",      # 1:00 PM (12-hour)
        "%I %p",         # 1 PM (12-hour, no minutes)
    ]
    
    for fmt in time_formats:
        try:
            return dt.datetime.strptime(time_clean, fmt).time()
        except ValueError:
            continue
    
    return None


def create_discord_timestamp(
    date: str | None = None,
    time: str | None = None,
    timezone_offset: int = 0
) -> tuple[int, dt.datetime, dt.datetime] | tuple[None, None, str]:
    """
    Create a Discord timestamp from date/time components.
    
    Args:
        date: Date string in YYYY-MM-DD format (defaults to today)
        time: Time string in various formats (defaults to now)
        timezone_offset: Hours behind UTC (e.g., -6 for CST)
        
    Returns:
        Tuple of (unix_timestamp, input_datetime, utc_datetime) on success
        Tuple of (None, None, error_message) on failure
    """
    now = dt.datetime.now()
    
    # Parse date (use today if not provided)
    if date:
        try:
            parsed_date = dt.datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return None, None, "Invalid date format. Use 'YYYY-MM-DD'"
    else:
        parsed_date = now.date()
    
    # Parse time (use current time if not provided)
    if time:
        parsed_time = parse_time(time)
        if parsed_time is None:
            return None, None, (
                "Invalid time format. Supported formats:\n"
                "• 24-hour: `13:00`, `13:00:30`\n"
                "• 12-hour: `1 PM`, `1:00 PM`, `1:00:30 PM`"
            )
    else:
        parsed_time = now.time()
    
    # Combine date and time
    combined_datetime = dt.datetime.combine(parsed_date, parsed_time)
    
    # Apply timezone offset to convert to UTC
    # timezone_offset represents hours behind UTC, so we SUBTRACT it to get UTC time
    combined_datetime_utc = combined_datetime - dt.timedelta(hours=timezone_offset)
    
    # Convert to Unix timestamp using UTC timezone explicitly
    utc_with_timezone = combined_datetime_utc.replace(tzinfo=dt.timezone.utc)
    unix_timestamp = int(utc_with_timezone.timestamp())
    
    return unix_timestamp, combined_datetime, combined_datetime_utc


def format_timestamp_examples(unix_timestamp: int) -> list[str]:
    """
    Generate examples of all Discord timestamp formats.
    
    Args:
        unix_timestamp: Unix timestamp in seconds
        
    Returns:
        List of formatted example strings
    """
    return [
        f"**Short Time (t)**: `<t:{unix_timestamp}:t>` <t:{unix_timestamp}:t>",
        f"**Long Time (T)**: `<t:{unix_timestamp}:T>` <t:{unix_timestamp}:T>",
        f"**Short Date (d)**: `<t:{unix_timestamp}:d>` <t:{unix_timestamp}:d>",
        f"**Long Date (D)**: `<t:{unix_timestamp}:D>` <t:{unix_timestamp}:D>",
        f"**Short DateTime (f)**: `<t:{unix_timestamp}:f>` <t:{unix_timestamp}:f>",
        f"**Long DateTime (F)**: `<t:{unix_timestamp}:F>` <t:{unix_timestamp}:F>",
        f"**Relative (R)**: `<t:{unix_timestamp}:R>` <t:{unix_timestamp}:R>"
    ]
