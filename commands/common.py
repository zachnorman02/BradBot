"""
Shared app_commands.Group base classes.

Centralizes the guild-only guard, Discord `default_permissions` enforcement,
and bot-owner guard that were previously copy-pasted at the top of ~30+
individual command bodies across admin_commands.py and mod_tools_commands.py.
Every domain Group in the reorganized commands/ tree should subclass one of
these instead of writing its own interaction_check or per-command guard.

The bot owner bypasses every permission gate defined here so they can
exercise any command while testing, regardless of their actual permissions
in a given server. Note this only covers checks *this codebase* performs --
Discord's own `default_permissions` also controls whether a command is even
visible to a user in a guild's command picker, which is a per-server setting
(under Integrations) that bot code cannot override.
"""
from typing import Callable, TypeVar

import discord
from discord import app_commands

from utils.interaction_helpers import require_guild, require_bot_owner, is_bot_owner

T = TypeVar('T')


async def _enforce_default_permissions(interaction: discord.Interaction) -> bool:
    """Enforce a command's `default_permissions` (set via
    @app_commands.default_permissions(...)) against the invoking user."""
    command = interaction.command
    if not command:
        return True
    required = getattr(command, "default_permissions", None)
    if required is None:
        return True
    if await is_bot_owner(interaction):
        return True
    if interaction.user.guild_permissions.is_superset(required):
        return True
    if not interaction.response.is_done():
        await interaction.response.send_message(
            "❌ You don't have permission to use this command.",
            ephemeral=True,
        )
    return False


class GuildOnlyGroup(app_commands.Group):
    """Base for any Group whose commands only make sense inside a server.

    Also enforces per-command `default_permissions` set via the standard
    @app_commands.default_permissions decorator, so subclasses don't need
    their own interaction_check for that.
    """

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await require_guild(interaction):
            return False
        return await _enforce_default_permissions(interaction)


class OwnerOnlyGroup(GuildOnlyGroup):
    """Base for Groups restricted to the bot owner (e.g. diagnostics/ops)."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        return await require_bot_owner(interaction)


def owner_or_permissions(**perms: bool) -> Callable[[T], T]:
    """Like @app_commands.checks.has_permissions(**perms), but the bot
    owner always passes regardless of their permissions in this guild.

    Use this instead of app_commands.checks.has_permissions wherever a
    command is gated by permission rather than by Group-level
    default_permissions (has_permissions is a per-command check that runs
    independently of GuildOnlyGroup.interaction_check, so it needs its own
    owner bypass).
    """
    invalid = perms.keys() - discord.Permissions.VALID_FLAGS.keys()
    if invalid:
        raise TypeError(f'Invalid permission(s): {", ".join(invalid)}')

    async def predicate(interaction: discord.Interaction) -> bool:
        if await is_bot_owner(interaction):
            return True
        permissions = interaction.permissions
        missing = [perm for perm, value in perms.items() if getattr(permissions, perm) != value]
        if not missing:
            return True
        raise app_commands.MissingPermissions(missing)

    return app_commands.check(predicate)
