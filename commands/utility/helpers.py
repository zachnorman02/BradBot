"""Pure time-parsing helpers for reminders/timers."""
import datetime as dt
import re
from typing import Optional

from dateutil import parser


def parse_duration(duration: str) -> Optional[int]:
    """Parse a duration string like '5m', '2h', '1d' into seconds."""
    match = re.match(r'^(\d+)([smhd])$', duration.strip().lower())
    if not match:
        return None
    multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    return int(match.group(1)) * multipliers[match.group(2)]


def parse_datetime(time_str: str, timezone_offset: int = 0) -> Optional[dt.datetime]:
    """Parse a date/time string into a UTC datetime object."""
    time_str = time_str.strip().lower()
    now = dt.datetime.now(dt.timezone.utc)

    if time_str in ('tomorrow', 'tmr'):
        user_time = (now + dt.timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        return user_time - dt.timedelta(hours=timezone_offset)

    if time_str == 'today':
        user_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
        return user_time - dt.timedelta(hours=timezone_offset)

    try:
        parsed = parser.parse(time_str, fuzzy=True, default=now.replace(hour=9, minute=0, second=0, microsecond=0))
        return parsed - dt.timedelta(hours=timezone_offset)
    except Exception:
        return None
