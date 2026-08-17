"""Pure validation/formatting helpers for the birthday domain."""
import calendar
import datetime as dt
from typing import Optional, Tuple


def validate_birthday(year: Optional[int], month: Optional[int], day: Optional[int]) -> Tuple[bool, Optional[str]]:
    if month is None:
        return False, "Please provide a month (and day if you want announcements)."
    if day is None and year is None:
        return False, "Please provide day with month, or provide year + month."
    if day is not None:
        year_for_validation = year if year is not None else 2000
        try:
            last_day = calendar.monthrange(year_for_validation, month)[1]
        except calendar.IllegalMonthError:
            return False, "Invalid month."
        if day < 1 or day > last_day:
            return False, f"Invalid day for {dt.date(year_for_validation, month, 1):%B}."
    return True, None


def format_birthday(year: Optional[int], month: int, day: Optional[int]) -> str:
    year_text = f"{year}-" if year is not None else ""
    if day is None:
        return f"{year_text}{month:02d}"
    return f"{year_text}{month:02d}-{day:02d}"
