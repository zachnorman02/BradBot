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
