"""Reminders and timers. `check_reaction` was removed -- it's now the
consolidated "Check Reactions" message context menu in commands/reaction/,
which also absorbed reaction.check and reaction.check_url."""
import datetime as dt
from typing import Optional

import discord
from discord import app_commands

from database import db
from utils.cookie_helper import fetch_youtube_cookies
from utils.logger import logger
from commands.utility.helpers import parse_duration, parse_datetime


class UtilityGroup(app_commands.Group):
    """Utility commands for reminders and timers."""

    def __init__(self):
        super().__init__(name="utility", description="Reminders and timers")

    @app_commands.command(name="remind", description="Set a reminder for yourself")
    @app_commands.describe(
        time="Duration (5m, 2h, 1d) OR date/time (2025-12-25, Dec 25 3pm, tomorrow 2pm)",
        message="What to remind you about",
        timezone_offset="Hours behind UTC (e.g., -5 for EST, -8 for PST, default: 0)",
    )
    async def remind(self, interaction: discord.Interaction, time: str, message: str, timezone_offset: int = 0):
        """Set a reminder that will ping you after the specified duration or at a specific time."""
        try:
            seconds = parse_duration(time)

            if seconds is not None:
                if seconds < 10:
                    await interaction.response.send_message("❌ Duration must be at least 10 seconds", ephemeral=True)
                    return
                if seconds > 31536000:
                    await interaction.response.send_message("❌ Duration cannot exceed 1 year", ephemeral=True)
                    return
                remind_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)
            else:
                remind_at = parse_datetime(time, timezone_offset)
                if remind_at is None:
                    await interaction.response.send_message(
                        "❌ Invalid time format. Use:\n"
                        "• Duration: `5m`, `2h`, `1d`, `30s`\n"
                        "• Date: `2025-12-25`, `Dec 25`, `tomorrow`\n"
                        "• Date + Time: `Dec 25 3pm`, `tomorrow 2pm`, `2025-12-25 14:30`",
                        ephemeral=True,
                    )
                    return

                now = dt.datetime.now(dt.timezone.utc)
                if remind_at <= now:
                    await interaction.response.send_message("❌ The specified time is in the past", ephemeral=True)
                    return
                if (remind_at - now).total_seconds() > 31536000:
                    await interaction.response.send_message("❌ Reminder time cannot be more than 1 year in the future", ephemeral=True)
                    return

            try:
                if not db.connection_pool:
                    db.init_pool()

                db.create_reminder(
                    user_id=interaction.user.id, guild_id=interaction.guild.id if interaction.guild else None,
                    channel_id=interaction.channel.id, message=message, remind_at=remind_at,
                )

                await interaction.response.send_message(
                    f"⏰ Reminder set! I'll remind you <t:{int(remind_at.timestamp())}:R> (<t:{int(remind_at.timestamp())}:F>)\n**Message:** {message}",
                    ephemeral=True,
                )
            except Exception as e:
                logger.error(f"Error storing reminder: {e}")
                await interaction.response.send_message("❌ An error occurred while setting the reminder.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting reminder: {e}")
            try:
                await interaction.response.send_message("❌ An error occurred while setting the reminder.", ephemeral=True)
            except Exception:
                pass

    @app_commands.command(name="refresh_cookies", description="Refresh YouTube cookies for video downloads")
    async def refresh_cookies(self, interaction: discord.Interaction):
        """Refresh YouTube authentication cookies."""
        await interaction.response.defer(ephemeral=True)
        try:
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(fetch_youtube_cookies)
                cookie_file = future.result(timeout=60)

            if cookie_file:
                await interaction.followup.send("✅ YouTube cookies refreshed successfully!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to refresh YouTube cookies. Check logs for details.", ephemeral=True)
        except concurrent.futures.TimeoutError:
            await interaction.followup.send("⏰ Cookie refresh timed out. The process may still be running.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error refreshing cookies: {str(e)}", ephemeral=True)

    @app_commands.command(name="timer", description="Start a countdown timer visible to everyone")
    @app_commands.describe(duration="Duration (e.g., '5m', '2h', '1d', '30s')", label="Optional label for the timer")
    async def timer(self, interaction: discord.Interaction, duration: str, label: Optional[str] = None):
        """Start a countdown timer that updates in the channel."""
        try:
            seconds = parse_duration(duration)
            if seconds is None:
                await interaction.response.send_message("❌ Invalid duration format. Use formats like: `5m`, `2h`, `1d`, `30s`", ephemeral=True)
                return
            if seconds < 10:
                await interaction.response.send_message("❌ Duration must be at least 10 seconds", ephemeral=True)
                return
            if seconds > 86400:
                await interaction.response.send_message("❌ Timer duration cannot exceed 24 hours", ephemeral=True)
                return

            end_time = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)

            if not db.connection_pool:
                db.init_pool()

            timer_id = db.create_timer(user_id=interaction.user.id, guild_id=interaction.guild.id, channel_id=interaction.channel.id, label=label, end_time=end_time)

            embed = discord.Embed(title=f"⏱️ Timer{f': {label}' if label else ''}", description=f"Started by {interaction.user.mention}", color=discord.Color.blue())
            embed.add_field(name="Ends", value=f"<t:{int(end_time.timestamp())}:R> (<t:{int(end_time.timestamp())}:T>)", inline=False)
            embed.set_footer(text=f"Timer ID: {timer_id}")

            await interaction.response.send_message(embed=embed)
            message = await interaction.original_response()
            db.update_timer_message_id(timer_id, message.id)

            logger.info(f"⏱️ Timer {timer_id} created by {interaction.user} for {duration}")
        except Exception as e:
            logger.error(f"Error creating timer: {e}")
            try:
                await interaction.response.send_message("❌ An error occurred while creating the timer.", ephemeral=True)
            except Exception:
                pass
