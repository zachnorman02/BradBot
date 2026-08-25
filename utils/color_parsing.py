"""Shared hex-color parsing for role color commands (booster, admin)."""
import discord


def parse_hex_color(value: str, *, field_label: str = "color") -> discord.Color:
    """Parse a '#RRGGBB' or 'RRGGBB' string into a discord.Color.

    Raises ValueError with a user-facing message on failure.
    """
    try:
        return discord.Color(int(value.strip().lstrip('#'), 16))
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid {field_label} hex format. Use a format like #FF0000.")
