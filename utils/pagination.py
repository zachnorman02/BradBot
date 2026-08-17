"""Shared paginated-embed builder for list-style commands."""
from typing import Sequence

import discord


def build_paginated_embed(
    title: str,
    items: Sequence[str],
    *,
    page_size: int = 20,
    color: discord.Color = discord.Color.blurple(),
    description: str = "",
    footer_prefix: str = "",
    empty_message: str = "Nothing to show.",
) -> discord.Embed:
    """Build an embed listing `items`, capped at page_size with an
    '...and N more' footer for overflow. Replaces the cap-at-20 pattern
    that was duplicated across admin/mod_tools list commands."""
    embed = discord.Embed(title=title, description=description, color=color)

    if not items:
        embed.add_field(name="​", value=empty_message, inline=False)
        return embed

    shown = items[:page_size]
    embed.add_field(name="​", value="\n".join(shown), inline=False)

    remaining = len(items) - len(shown)
    if remaining > 0:
        footer = f"{footer_prefix}...and {remaining} more" if footer_prefix else f"...and {remaining} more"
        embed.set_footer(text=footer)

    return embed
