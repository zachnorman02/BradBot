"""Birthday commands for users and servers.

Bug fix: the old `list_month_birthdays` method had no @app_commands.command
decorator, so it was dead/unregistered code. It's registered here as `month`.
"""
import calendar
import datetime as dt
from typing import Optional

import discord
from discord import app_commands

from database import db
from utils.interaction_helpers import send_error, send_success, send_info, require_guild, has_permission_or_owner
from commands.birthday.helpers import validate_birthday, format_birthday


class BirthdayChannelGroup(app_commands.Group):
    """Manage birthday announcement channels."""

    def __init__(self):
        super().__init__(name="channel", description="Manage birthday announcement channel")

    @app_commands.command(name="set", description="Set the channel for birthday announcements")
    @app_commands.describe(channel="Channel where birthday pings will be sent")
    @app_commands.default_permissions(manage_guild=True)
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await require_guild(interaction):
            return
        if not await has_permission_or_owner(interaction, manage_guild=True):
            await send_error(interaction, "You need Manage Server to do that.")
            return

        db.set_guild_setting(interaction.guild.id, 'birthday_channel_id', str(channel.id))
        await send_success(interaction, f"Birthday channel set to {channel.mention}.")

    @app_commands.command(name="clear", description="Clear the birthday announcement channel")
    @app_commands.default_permissions(manage_guild=True)
    async def clear_channel(self, interaction: discord.Interaction):
        if not await require_guild(interaction):
            return
        if not await has_permission_or_owner(interaction, manage_guild=True):
            await send_error(interaction, "You need Manage Server to do that.")
            return

        db.set_guild_setting(interaction.guild.id, 'birthday_channel_id', '')
        await send_success(interaction, "Birthday channel cleared.")


class BirthdayGroup(app_commands.Group):
    """Birthday commands for users and servers."""

    def __init__(self):
        super().__init__(name="birthday", description="Birthday settings")
        self.add_command(BirthdayChannelGroup())

    @app_commands.command(name="set", description="Set your birthday for this server")
    @app_commands.describe(year="Optional year (e.g., 1995)", month="Month number (1-12)", day="Day of month (1-31)")
    async def set_birthday(
        self, interaction: discord.Interaction,
        year: Optional[app_commands.Range[int, 1900, 2100]] = None,
        month: Optional[app_commands.Range[int, 1, 12]] = None,
        day: Optional[app_commands.Range[int, 1, 31]] = None,
    ):
        if not await require_guild(interaction):
            return

        valid, error = validate_birthday(year, month, day)
        if not valid:
            await send_error(interaction, error)
            return

        db.set_birthday(interaction.guild.id, interaction.user.id, year, month, day)
        date_text = format_birthday(year, month, day)
        if day is None:
            await send_success(interaction, f"Birthday set to {date_text} (no day set, so no announcements).")
            return
        await send_success(interaction, f"Birthday set to {date_text}.")

    @app_commands.command(name="clear", description="Clear your birthday for this server")
    async def clear_birthday(self, interaction: discord.Interaction):
        if not await require_guild(interaction):
            return
        db.clear_birthday(interaction.guild.id, interaction.user.id)
        await send_success(interaction, "Birthday cleared.")

    @app_commands.command(name="set_for", description="Set a birthday for another user")
    @app_commands.describe(user="User whose birthday you want to set", year="Optional year (e.g., 1995)", month="Month number (1-12)", day="Day of month (1-31)")
    @app_commands.default_permissions(manage_guild=True)
    async def set_birthday_for(
        self, interaction: discord.Interaction, user: discord.Member,
        year: Optional[app_commands.Range[int, 1900, 2100]] = None,
        month: Optional[app_commands.Range[int, 1, 12]] = None,
        day: Optional[app_commands.Range[int, 1, 31]] = None,
    ):
        if not await require_guild(interaction):
            return
        if not await has_permission_or_owner(interaction, manage_guild=True):
            await send_error(interaction, "You need Manage Server to do that.")
            return

        valid, error = validate_birthday(year, month, day)
        if not valid:
            await send_error(interaction, error)
            return

        db.set_birthday(interaction.guild.id, user.id, year, month, day)
        date_text = format_birthday(year, month, day)
        if day is None:
            await send_success(interaction, f"Birthday set for {user.mention}: {date_text} (no day set, so no announcements).")
            return
        await send_success(interaction, f"Birthday set for {user.mention}: {date_text}.")

    @app_commands.command(name="month", description="List birthdays in a given month (defaults to this month)")
    @app_commands.describe(month="Month number (1-12), defaults to the current month")
    async def month(self, interaction: discord.Interaction, month: Optional[app_commands.Range[int, 1, 12]] = None):
        if not await require_guild(interaction):
            return

        target_month = month or dt.datetime.now(dt.timezone.utc).month
        entries = db.get_birthdays_for_month(interaction.guild.id, target_month)

        lines = []
        for entry in entries:
            member = interaction.guild.get_member(entry['user_id'])
            if not member:
                continue
            day = entry.get('day')
            if day is None:
                lines.append(f"- {member.mention} — {calendar.month_name[target_month]} (day unknown)")
            else:
                lines.append(f"- {member.mention} — {calendar.month_name[target_month]} {day:02d}")

        if not lines:
            await send_info(interaction, f"No birthdays recorded for {calendar.month_name[target_month]}.")
            return

        response = f"🎂 Birthdays in {calendar.month_name[target_month]}\n" + "\n".join(lines)
        if len(response) > 1900:
            response = response[:1900] + "\n... (truncated)"
        await interaction.response.send_message(response, ephemeral=True)

    @app_commands.command(name="age", description="List users by current age")
    @app_commands.describe(age="Age to look up")
    async def list_by_age(self, interaction: discord.Interaction, age: app_commands.Range[int, 1, 120]):
        if not await require_guild(interaction):
            return

        today = dt.datetime.now(dt.timezone.utc).date()
        entries = db.get_birthdays_with_year_and_day(interaction.guild.id)
        matches = []
        for entry in entries:
            member = interaction.guild.get_member(entry['user_id'])
            if not member:
                continue
            year, month, day = entry.get('year'), entry.get('month'), entry.get('day')
            if year is None or day is None:
                continue
            computed_age = today.year - year
            if (month, day) > (today.month, today.day):
                computed_age -= 1
            if computed_age == age:
                matches.append(member.mention)

        if not matches:
            await send_info(interaction, f"No users with age {age} found.")
            return

        response = f"🎉 Users with age {age}:\n" + "\n".join(f"- {m}" for m in matches)
        if len(response) > 1900:
            response = response[:1900] + "\n... (truncated)"
        await interaction.response.send_message(response, ephemeral=True)

    @app_commands.command(name="list", description="List all birthdays in this server")
    async def list_all_birthdays(self, interaction: discord.Interaction):
        if not await require_guild(interaction):
            return

        entries = db.get_birthdays_for_guild(interaction.guild.id)
        lines = []
        for entry in entries:
            member = interaction.guild.get_member(entry['user_id'])
            if not member:
                continue
            month, day = entry.get('month'), entry.get('day')
            if day is None:
                lines.append(f"- {member.mention} — {calendar.month_name[month]} (day unknown)")
            else:
                lines.append(f"- {member.mention} — {calendar.month_name[month]} {day:02d}")

        if not lines:
            await send_info(interaction, "No birthdays recorded.")
            return

        response = "🎂 All birthdays\n" + "\n".join(lines)
        if len(response) > 1900:
            response = response[:1900] + "\n... (truncated)"
        await interaction.response.send_message(response, ephemeral=True)
