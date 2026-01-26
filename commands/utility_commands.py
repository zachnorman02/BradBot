"""
Utility command group for reminders and timers
"""
import discord
from discord import app_commands
import datetime as dt
import asyncio
import re
from typing import Optional
from dateutil import parser
from database import db
from utils.cookie_helper import fetch_youtube_cookies


class UtilityGroup(app_commands.Group):
    """Utility commands for reminders and timers"""
    
    def _parse_message_link(self, link: str) -> tuple[int | None, int | None, int | None]:
        """Return (guild_id, channel_id, message_id) from a Discord message link."""
        try:
            parts = link.strip().split("/")
            guild_id = int(parts[-3])
            channel_id = int(parts[-2])
            message_id = int(parts[-1])
            return guild_id, channel_id, message_id
        except Exception:
            return None, None, None
    
    @app_commands.command(name="remind", description="Set a reminder for yourself")
    @app_commands.describe(
        time="Duration (5m, 2h, 1d) OR date/time (2025-12-25, Dec 25 3pm, tomorrow 2pm)",
        message="What to remind you about",
        timezone_offset="Hours behind UTC (e.g., -5 for EST, -8 for PST, default: 0)"
    )
    async def remind(self, interaction: discord.Interaction, time: str, message: str, timezone_offset: int = 0):
        """Set a reminder that will ping you after the specified duration or at a specific time"""
        try:
            # Try to parse as duration first
            seconds = self._parse_duration(time)
            
            if seconds is not None:
                # Duration format
                if seconds < 10:
                    await interaction.response.send_message(
                        "❌ Duration must be at least 10 seconds",
                        ephemeral=True
                    )
                    return
                
                if seconds > 31536000:  # 1 year
                    await interaction.response.send_message(
                        "❌ Duration cannot exceed 1 year",
                        ephemeral=True
                    )
                    return
                
                remind_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)
            else:
                # Try to parse as date/time
                remind_at = self._parse_datetime(time, timezone_offset)
                if remind_at is None:
                    await interaction.response.send_message(
                        "❌ Invalid time format. Use:\n"
                        "• Duration: `5m`, `2h`, `1d`, `30s`\n"
                        "• Date: `2025-12-25`, `Dec 25`, `tomorrow`\n"
                        "• Date + Time: `Dec 25 3pm`, `tomorrow 2pm`, `2025-12-25 14:30`",
                        ephemeral=True
                    )
                    return
                
                # Check if time is in the past
                now = dt.datetime.now(dt.timezone.utc)
                if remind_at <= now:
                    await interaction.response.send_message(
                        "❌ The specified time is in the past",
                        ephemeral=True
                    )
                    return
                
                # Check if time is too far in the future (1 year)
                if (remind_at - now).total_seconds() > 31536000:
                    await interaction.response.send_message(
                        "❌ Reminder time cannot be more than 1 year in the future",
                        ephemeral=True
                    )
                    return
                
                seconds = (remind_at - now).total_seconds()
            
            # Store reminder in database
            try:
                if not db.connection_pool:
                    db.init_pool()
                
                reminder_id = db.create_reminder(
                    user_id=interaction.user.id,
                    guild_id=interaction.guild.id if interaction.guild else None,
                    channel_id=interaction.channel.id,
                    message=message,
                    remind_at=remind_at
                )
                
                # Confirm reminder set
                await interaction.response.send_message(
                    f"⏰ Reminder set! I'll remind you <t:{int(remind_at.timestamp())}:R> (<t:{int(remind_at.timestamp())}:F>)\n"
                    f"**Message:** {message}",
                    ephemeral=True
                )
            except Exception as e:
                print(f"Error storing reminder: {e}")
                await interaction.response.send_message(
                    "❌ An error occurred while setting the reminder.",
                    ephemeral=True
                )
            
        except Exception as e:
            print(f"Error setting reminder: {e}")
            try:
                await interaction.response.send_message(
                    "❌ An error occurred while setting the reminder.",
                    ephemeral=True
                )
            except:
                pass
    
    @app_commands.command(name="refresh_cookies", description="Refresh YouTube cookies for video downloads")
    async def refresh_cookies(self, interaction: discord.Interaction):
        """Refresh YouTube authentication cookies"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Run cookie fetch in thread pool to avoid blocking
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(fetch_youtube_cookies)
                cookie_file = future.result(timeout=60)  # 60 second timeout
            
            if cookie_file:
                await interaction.followup.send("✅ YouTube cookies refreshed successfully!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to refresh YouTube cookies. Check logs for details.", ephemeral=True)
                
        except concurrent.futures.TimeoutError:
            await interaction.followup.send("⏰ Cookie refresh timed out. The process may still be running.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error refreshing cookies: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="timer", description="Start a countdown timer visible to everyone")
    @app_commands.describe(
        duration="Duration (e.g., '5m', '2h', '1d', '30s')",
        label="Optional label for the timer"
    )
    async def timer(self, interaction: discord.Interaction, duration: str, label: Optional[str] = None):
        """Start a countdown timer that updates in the channel"""
        try:
            # Parse duration
            seconds = self._parse_duration(duration)
            if seconds is None:
                await interaction.response.send_message(
                    "❌ Invalid duration format. Use formats like: `5m`, `2h`, `1d`, `30s`",
                    ephemeral=True
                )
                return
            
            if seconds < 10:
                await interaction.response.send_message(
                    "❌ Duration must be at least 10 seconds",
                    ephemeral=True
                )
                return
            
            if seconds > 86400:  # 24 hours
                await interaction.response.send_message(
                    "❌ Timer duration cannot exceed 24 hours",
                    ephemeral=True
                )
                return
            
            # Calculate end time
            end_time = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)
            
            # Store timer in database
            if not db.connection_pool:
                db.init_pool()
            
            timer_id = db.create_timer(
                user_id=interaction.user.id,
                guild_id=interaction.guild.id,
                channel_id=interaction.channel.id,
                label=label,
                end_time=end_time
            )
            
            # Create initial embed
            embed = discord.Embed(
                title=f"⏱️ Timer{f': {label}' if label else ''}",
                description=f"Started by {interaction.user.mention}",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Ends",
                value=f"<t:{int(end_time.timestamp())}:R> (<t:{int(end_time.timestamp())}:T>)",
                inline=False
            )
            embed.set_footer(text=f"Timer ID: {timer_id}")
            
            await interaction.response.send_message(embed=embed)
            message = await interaction.original_response()
            
            # Update database with message ID
            db.update_timer_message_id(timer_id, message.id)
            
            print(f"⏱️ Timer {timer_id} created by {interaction.user} for {duration}")
            
        except Exception as e:
            print(f"Error creating timer: {e}")
            try:
                await interaction.response.send_message(
                    "❌ An error occurred while creating the timer.",
                    ephemeral=True
                )
            except:
                pass
    
    def _parse_duration(self, duration: str) -> Optional[int]:
        """Parse a duration string like '5m', '2h', '1d' into seconds"""
        duration = duration.strip().lower()
        
        # Extract number and unit
        match = re.match(r'^(\d+)([smhd])$', duration)
        if not match:
            return None
        
        value = int(match.group(1))
        unit = match.group(2)
        
        multipliers = {
            's': 1,
            'm': 60,
            'h': 3600,
            'd': 86400
        }
        
        return value * multipliers[unit]
    
    def _parse_datetime(self, time_str: str, timezone_offset: int = 0) -> Optional[dt.datetime]:
        """Parse a date/time string into a UTC datetime object"""
        time_str = time_str.strip().lower()
        now = dt.datetime.now(dt.timezone.utc)
        
        # Handle relative dates
        if time_str in ['tomorrow', 'tmr']:
            base_date = now + dt.timedelta(days=1)
            # Default to 9 AM in user's timezone
            user_time = base_date.replace(hour=9, minute=0, second=0, microsecond=0)
            return user_time - dt.timedelta(hours=timezone_offset)
        
        if time_str == 'today':
            base_date = now
            user_time = base_date.replace(hour=9, minute=0, second=0, microsecond=0)
            return user_time - dt.timedelta(hours=timezone_offset)
        
        try:
            # Try to parse with dateutil
            parsed = parser.parse(time_str, fuzzy=True, default=now.replace(hour=9, minute=0, second=0, microsecond=0))
            
            # Convert from user's timezone to UTC
            utc_time = parsed - dt.timedelta(hours=timezone_offset)
            
            return utc_time
        except:
            return None

    @app_commands.command(name="check_reaction", description="Check if a user reacted to a specific message")
    @app_commands.describe(
        message_link="Link to the message",
        user="User to check (default: you)",
        emoji_filter="Optional: only consider this emoji (e.g., ✅ or :custom:)"
    )
    async def check_reaction(
        self,
        interaction: discord.Interaction,
        message_link: str,
        user: Optional[discord.User] = None,
        emoji_filter: Optional[str] = None
    ):
        """Quickly verify whether a user reacted to a message (optionally with a specific emoji)."""
        target_user = user or interaction.user

        guild_id, channel_id, message_id = self._parse_message_link(message_link)
        if not guild_id or guild_id != interaction.guild.id:
            await interaction.response.send_message("❌ Invalid or out-of-guild message link.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message("❌ Could not find that channel or message.", ephemeral=True)
            return

        try:
            message = await channel.fetch_message(message_id)
        except Exception:
            await interaction.response.send_message("❌ Could not fetch that message.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        def _normalize_emoji(e):
            if e is None:
                return None
            if isinstance(e, str):
                return e
            if hasattr(e, "id") and e.id:
                prefix = "<a" if getattr(e, "animated", False) else "<"
                return f"{prefix}:{e.name}:{e.id}>"
            return str(e)

        normalized_filter = _normalize_emoji(emoji_filter) if emoji_filter else None
        found = False
        matched_emoji = None

        try:
            for reaction in message.reactions:
                if normalized_filter and _normalize_emoji(reaction.emoji) != normalized_filter:
                    continue
                async for reactor in reaction.users(limit=None):
                    if reactor.id == target_user.id:
                        found = True
                        matched_emoji = _normalize_emoji(reaction.emoji)
                        break
                if found:
                    break
        except Exception as e:
            await interaction.followup.send(f"❌ Error scanning reactions: {e}", ephemeral=True)
            return

        if found:
            await interaction.followup.send(
                f"✅ {target_user.mention} reacted on that message"
                + (f" with {matched_emoji}" if matched_emoji else "")
                + ".",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"❌ No reaction from {target_user.mention} found on that message"
                + (f" for emoji {normalized_filter}" if normalized_filter else "")
                + ".",
                ephemeral=True
            )
