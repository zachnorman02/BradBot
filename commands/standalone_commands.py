"""
Standalone utility commands and their helpers
"""
import discord
from discord import app_commands
from database import db
from utils.timestamp_helpers import TimestampStyle, create_discord_timestamp, format_timestamp_examples

async def echo_command(
    interaction: discord.Interaction,
    message: str,
    allow_mentions: bool = False,
):
    """Echo a message to the current channel."""
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        return

    if db.is_command_disabled(interaction.guild.id, 'echo') and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Echo is disabled in this server.", ephemeral=True)
        return

    banned, ban_reason = db.is_user_banned_for_command(interaction.guild.id, interaction.user.id, 'echo')
    if banned:
        reason_note = f" Reason: {ban_reason}" if ban_reason else ""
        await interaction.response.send_message(f"❌ You are banned from using echo in this server.{reason_note}", ephemeral=True)
        return

    allowed = discord.AllowedMentions.all() if allow_mentions else discord.AllowedMentions.none()
    await interaction.response.defer(ephemeral=True)
    try:
        sent_message = await interaction.channel.send(
            message,
            allowed_mentions=allowed,
            silent=not allow_mentions
        )
        try:
            db.log_echo_message(
                interaction.guild.id,
                interaction.user.id,
                interaction.user.name,
                interaction.channel.id,
                message,
                sent_message.id
            )
        except Exception as log_error:
            print(f"Failed to log echo message: {log_error}")
        await interaction.followup.send("✅ Message sent.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to send message: {e}", ephemeral=True)


# ============================================================================
# STANDALONE COMMANDS
# ============================================================================
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
