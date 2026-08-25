"""Standalone top-level slash commands (not part of any group). Previously
these were wired via raw @bot.tree.command decorators directly in main.py --
a third, inconsistent registration pattern alongside bot.tree.add_command(Group())
and the bespoke setup_reaction_commands(tree). Decorating them here with
@app_commands.command produces ordinary app_commands.Command objects that
register through commands/registry.py like everything else.
"""
import discord
from discord import app_commands

from database import db
from utils.logger import logger
from utils.interaction_helpers import send_error, send_success, require_guild, has_permission_or_owner
from utils.timestamp_helpers import TimestampStyle, create_discord_timestamp, format_timestamp_examples


@app_commands.command(name="echo", description="Have the bot repeat a message in this channel")
@app_commands.describe(message="What should the bot say?", allow_mentions="Allow mentions in the echoed message (default: disabled)")
async def echo(interaction: discord.Interaction, message: str, allow_mentions: bool = False):
    """Echo a message to the current channel."""
    if not await require_guild(interaction):
        return

    if db.is_command_disabled(interaction.guild.id, 'echo') and not await has_permission_or_owner(interaction, administrator=True):
        await send_error(interaction, "Echo is disabled in this server.")
        return

    banned, ban_reason = db.is_user_banned_for_command(interaction.guild.id, interaction.user.id, 'echo')
    if banned:
        reason_note = f" Reason: {ban_reason}" if ban_reason else ""
        await send_error(interaction, f"You are banned from using echo in this server.{reason_note}")
        return

    can_mass_ping = interaction.user.guild_permissions.mention_everyone
    allowed = discord.AllowedMentions(everyone=can_mass_ping, roles=True, users=True) if allow_mentions else discord.AllowedMentions.none()

    await interaction.response.defer(ephemeral=True)
    try:
        sent_message = await interaction.channel.send(message, allowed_mentions=allowed, silent=not allow_mentions)
        try:
            db.log_echo_message(interaction.guild.id, interaction.user.id, interaction.user.name, interaction.channel.id, message, sent_message.id)
        except Exception as log_error:
            logger.error(f"Failed to log echo message: {log_error}")
        await send_success(interaction, "Message sent.")
    except Exception as e:
        await send_error(interaction, f"Failed to send message: {e}")


@app_commands.command(name="timestamp", description="Generate a Discord timestamp")
@app_commands.describe(
    date="Date in YYYY-MM-DD format (optional, defaults to today)",
    time="Time in 24hr (13:00) or 12hr (1 PM, 1:00 PM) format (optional, defaults to current time)",
    style="Display style for the timestamp",
    timezone_offset="Hours behind UTC for the input time (e.g. -6 for CST, -4 for EDT, 1 for CET)",
)
async def timestamp(interaction: discord.Interaction, date: str = None, time: str = None, style: TimestampStyle = None, timezone_offset: int = 0):
    """Creates a Discord timestamp that shows relative time and adapts to user's timezone."""
    try:
        result = create_discord_timestamp(date, time, timezone_offset)
        if result[0] is None:
            await send_error(interaction, result[2])
            return

        unix_timestamp, combined_datetime, combined_datetime_utc = result

        input_info = f"**Input:** {combined_datetime.date()} {combined_datetime.time().strftime('%H:%M:%S')}"
        if timezone_offset != 0:
            input_info += f" (UTC{timezone_offset:+d})"
            input_info += f"\n**Converted to UTC:** {combined_datetime_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC"

        response = f"{input_info}\n**Unix timestamp:** {unix_timestamp}\n"

        if style is not None:
            discord_timestamp = f"<t:{unix_timestamp}:{style.value}>"
            response += f"**Your timestamp:** `{discord_timestamp}`\n**Preview:** {discord_timestamp}\n\n"
        else:
            response += "**All format examples:**\n" + "\n".join(format_timestamp_examples(unix_timestamp))

        await interaction.response.send_message(response)
    except Exception as e:
        logger.error(f"Error in timestamp command: {e}")
        await send_error(interaction, f"An error occurred: {e}")
