"""
Standalone utility commands and their helpers
"""
import discord
from discord import app_commands
from timestamp_helpers import TimestampStyle, create_discord_timestamp, format_timestamp_examples
from conversion_helpers import ConversionType, convert_testosterone


# ============================================================================
# STANDALONE COMMANDS
# ============================================================================

async def clear_command(interaction: discord.Interaction):
    """Delete all messages in the current channel"""
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ You need 'Manage Messages' permission to use this command.", ephemeral=True)
        return
    
    if not interaction.guild.me.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ I don't have 'Manage Messages' permission to delete messages.", ephemeral=True)
        return
    
    # Defer the response since this will take a while
    await interaction.response.defer(ephemeral=True)
    
    # Delete all messages
    deleted = 0
    async for message in interaction.channel.history(limit=None):
        try:
            await message.delete()
            deleted += 1
        except Exception:
            pass
    await interaction.followup.send(f"Deleted {deleted} messages in this channel.", ephemeral=True)


async def tconvert_command(
    interaction: discord.Interaction,
    starting_type: str,
    dose: float,
    frequency: int
):
    """Converts between testosterone cypionate and gel doses."""
    response = convert_testosterone(starting_type, dose, frequency)
    await interaction.response.send_message(response)


async def timestamp_command(
    interaction: discord.Interaction,
    date: str = None,
    time: str = None,
    style: TimestampStyle = None,
    timezone_offset: int = 0
):
    """Creates a Discord timestamp that shows relative time and adapts to user's timezone."""
    try:
        # Use helper to create timestamp
        result = create_discord_timestamp(date, time, timezone_offset)
        
        # Check if there was an error
        if result[0] is None:
            await interaction.response.send_message(f"❌ {result[2]}", ephemeral=True)
            return
        
        unix_timestamp, combined_datetime, combined_datetime_utc = result
        
        # Build response
        input_info = f"**Input:** {combined_datetime.date()} {combined_datetime.time().strftime('%H:%M:%S')}"
        if timezone_offset != 0:
            input_info += f" (UTC{timezone_offset:+d})"
            input_info += f"\n**Converted to UTC:** {combined_datetime_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        
        response = f"{input_info}\n"
        response += f"**Unix timestamp:** {unix_timestamp}\n"
        
        if style is not None:
            # Generate Discord timestamp
            discord_timestamp = f"<t:{unix_timestamp}:{style.value}>"
            response += f"**Your timestamp:** `{discord_timestamp}`\n"
            response += f"**Preview:** {discord_timestamp}\n\n"
        else:
            response += "**All format examples:**\n" + "\n".join(format_timestamp_examples(unix_timestamp))
        
        await interaction.response.send_message(response)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)
