"""
Common response helpers for Discord interactions
Reduces code duplication across command files
"""
import discord
from typing import Optional


async def send_error(
    interaction: discord.Interaction,
    message: str,
    ephemeral: bool = True
) -> None:
    """
    Send an error message to the user
    
    Args:
        interaction: The Discord interaction
        message: Error message (will be prefixed with ❌)
        ephemeral: Whether the message should be ephemeral (default: True)
    """
    if not message.startswith("❌"):
        message = f"❌ {message}"
    
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(message, ephemeral=ephemeral)


async def send_success(
    interaction: discord.Interaction,
    message: str,
    ephemeral: bool = False
) -> None:
    """
    Send a success message to the user
    
    Args:
        interaction: The Discord interaction
        message: Success message (will be prefixed with ✅)
        ephemeral: Whether the message should be ephemeral (default: False)
    """
    if not message.startswith("✅"):
        message = f"✅ {message}"
    
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(message, ephemeral=ephemeral)


async def send_warning(
    interaction: discord.Interaction,
    message: str,
    ephemeral: bool = True
) -> None:
    """
    Send a warning message to the user
    
    Args:
        interaction: The Discord interaction
        message: Warning message (will be prefixed with ⚠️)
        ephemeral: Whether the message should be ephemeral (default: True)
    """
    if not message.startswith("⚠️"):
        message = f"⚠️ {message}"
    
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(message, ephemeral=ephemeral)


async def send_info(
    interaction: discord.Interaction,
    message: str,
    ephemeral: bool = False
) -> None:
    """
    Send an info message to the user
    
    Args:
        interaction: The Discord interaction
        message: Info message (will be prefixed with ℹ️)
        ephemeral: Whether the message should be ephemeral (default: False)
    """
    if not message.startswith("ℹ️"):
        message = f"ℹ️ {message}"
    
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(message, ephemeral=ephemeral)


def guild_only_check(interaction: discord.Interaction) -> bool:
    """
    Check if interaction is in a guild
    
    Args:
        interaction: The Discord interaction
        
    Returns:
        True if in a guild, False otherwise
    """
    return interaction.guild is not None


async def require_guild(interaction: discord.Interaction) -> bool:
    """
    Check if interaction is in a guild and send error if not

    Args:
        interaction: The Discord interaction

    Returns:
        True if in a guild, False if error was sent
    """
    if not guild_only_check(interaction):
        await send_error(interaction, "This command can only be used in a server.")
        return False
    return True


async def is_bot_owner(interaction: discord.Interaction) -> bool:
    """
    Check if the interacting user is the bot owner (or, for team-owned
    apps, an admin/developer on the team), with no side effects.

    Uses commands.Bot.is_owner(), which caches owner_id/owner_ids after the
    first application_info() lookup instead of re-fetching every call.

    Args:
        interaction: The Discord interaction

    Returns:
        True if the user is the bot owner, False otherwise.
    """
    return await interaction.client.is_owner(interaction.user)


async def require_bot_owner(interaction: discord.Interaction) -> bool:
    """
    Check if the interacting user is the bot owner, and send an error if not.

    Args:
        interaction: The Discord interaction

    Returns:
        True if the user is the bot owner, False if an error was sent.
    """
    if not await is_bot_owner(interaction):
        await send_error(interaction, "This command is restricted to the bot owner only.")
        return False
    return True


async def has_permission_or_owner(interaction: discord.Interaction, **perms: bool) -> bool:
    """
    Check if interaction.user has all the given guild permissions, or is
    the bot owner (who can exercise every command regardless of their
    actual permissions in a given server).

    Usage mirrors discord.Permissions flag names, e.g.:
        await has_permission_or_owner(interaction, manage_guild=True)

    Args:
        interaction: The Discord interaction
        **perms: guild permission flags that must all be True

    Returns:
        True if the user has all the given permissions, or is the bot owner.
    """
    if await is_bot_owner(interaction):
        return True
    permissions = interaction.user.guild_permissions
    return all(getattr(permissions, perm) == value for perm, value in perms.items())


async def error_response(interaction: discord.Interaction, exc: Exception, *, context: str = "") -> None:
    """
    Log an exception and send a truncated, user-facing error message.

    Replaces the dozens of duplicated `except Exception as e:
    await interaction.followup.send(f"Error: {str(e)[:200]}")` blocks
    across command files.

    Args:
        interaction: The Discord interaction
        exc: The caught exception
        context: Optional short label for the log line (e.g. command name)
    """
    from utils.logger import logger

    prefix = f"{context}: " if context else ""
    logger.error(f"{prefix}{exc}", exc_info=exc)
    await send_error(interaction, f"Error: {str(exc)[:200]}")
