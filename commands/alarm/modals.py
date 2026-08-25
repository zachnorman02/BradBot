"""Modal for the free-text fields of /alarm set. Channel/tts/tone/alternate/
repeat stay as native slash params (Discord-typed or simple bool/int with
good defaults); only time/message/interval/tz -- all free text -- move here.
"""
import uuid
import datetime as dt

import discord

from database import db
from utils.logger import logger
from utils.interaction_helpers import send_error, send_success
from commands.alarm.helpers import parse_relative_or_absolute_time, parse_interval, schedule_alarm_task


class AlarmSetModal(discord.ui.Modal, title="Set Alarm"):
    time = discord.ui.Label(
        text="Time",
        description='Relative ("in 10m") or absolute (YYYY-MM-DD HH:MM).',
        component=discord.ui.TextInput(style=discord.TextStyle.short, max_length=40),
    )
    message = discord.ui.Label(
        text="Message",
        description="Message to send when the alarm fires.",
        component=discord.ui.TextInput(style=discord.TextStyle.paragraph, required=False, max_length=500),
    )
    interval = discord.ui.Label(
        text="Repeat Interval",
        description='Optional recurrence: "daily", "hourly", or "in 1h30m".',
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=40),
    )
    tz = discord.ui.Label(
        text="Timezone",
        description='For absolute times only, e.g. "Europe/London" or "+02:00".',
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=40),
    )

    def __init__(self, channel: discord.TextChannel, tts: bool, tone: bool, alternate: bool, repeat: int):
        super().__init__()
        self.channel = channel
        self.tts = tts
        self.tone = tone
        self.alternate = alternate
        self.repeat = repeat

    async def on_submit(self, interaction: discord.Interaction):
        time_str = self.time.component.value.strip()
        message = self.message.component.value.strip() or None
        interval_str = self.interval.component.value.strip() or None
        tz = self.tz.component.value.strip() or None

        delay, error = parse_relative_or_absolute_time(time_str, tz)
        if error:
            await send_error(interaction, error)
            return

        now = dt.datetime.utcnow()
        fire_dt = now + dt.timedelta(seconds=delay)
        fire_at_iso = fire_dt.astimezone(dt.timezone.utc).isoformat()
        aid = uuid.uuid4().hex[:8]

        repeat_val = max(0, min(self.repeat, 10))

        interval_seconds = None
        if interval_str:
            interval_seconds = parse_interval(interval_str)
            if interval_seconds is None:
                await send_error(interaction, 'Could not parse interval. Use "daily", "hourly", or formats like "in 1h30m".')
                return

        try:
            db.add_alarm(aid, interaction.guild.id, interaction.user.id, self.channel.id, message, self.tts, self.tone, self.alternate, repeat_val, interval_seconds, fire_at_iso)
        except Exception as e:
            logger.error(f"Failed to save alarm: {e}")
            await send_error(interaction, f'Failed to save alarm: {e}')
            return

        schedule_alarm_task(interaction.client, (aid, interaction.guild.id, interaction.user.id, self.channel.id, message, self.tts, self.tone, self.alternate, repeat_val, interval_seconds, fire_at_iso))

        await send_success(interaction, f'Alarm set (id: `{aid}`) to fire <t:{int(fire_dt.timestamp())}:F>.')
