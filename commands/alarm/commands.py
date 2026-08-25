"""Alarm commands. `set` collects channel/tts/tone/alternate/repeat as native
params, then opens AlarmSetModal for the free-text time/message/interval/tz
fields (previously all 9 were slash-command string params)."""
import discord
from discord import app_commands

from database import db
from utils.logger import logger
from utils.interaction_helpers import send_error, require_guild
from commands.alarm.helpers import ALARM_TASKS
from commands.alarm.modals import AlarmSetModal


class AlarmGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name='alarm', description='Set simple alarms (message or TTS)')

    @app_commands.command(name='set', description='Set an alarm (opens a form for time/message/repeat)')
    @app_commands.describe(
        channel='Channel to send the alarm to (defaults to current channel)',
        tts='If true, try to speak the message in voice if connected',
        tone='If true, play a loud tone in voice instead of TTS',
        alternate='If true and both tone+tts are set, alternate tone and TTS (tone->tts->tone)',
        repeat='Number of times to play the alarm audio (default 1, max 10; 0 = hold continuously until cancelled)',
    )
    async def set(self, interaction: discord.Interaction, channel: discord.TextChannel = None, tts: bool = False, tone: bool = False, alternate: bool = False, repeat: int = 1):
        if not await require_guild(interaction):
            return
        await interaction.response.send_modal(AlarmSetModal(channel or interaction.channel, tts, tone, alternate, repeat))

    @app_commands.command(name='list', description='List scheduled alarms for this server')
    async def list(self, interaction: discord.Interaction):
        if not await require_guild(interaction):
            return

        try:
            rows = db.get_alarms_for_guild(interaction.guild.id)
        except Exception as e:
            logger.error(f"Failed to query alarms: {e}")
            await send_error(interaction, f'Failed to query alarms: {e}')
            return

        if not rows:
            await interaction.response.send_message('No alarms scheduled.', ephemeral=True)
            return

        lines = []
        for r in rows:
            aid, guild_id, creator_id, channel_id, msg, tts_flag, tone_flag, alternate_flag, repeat_val, interval_seconds, fire_at = r
            flags = []
            if tts_flag and str(tts_flag).lower() in ('true', 't', '1'):
                flags.append('tts')
            if tone_flag and str(tone_flag).lower() in ('true', 't', '1'):
                flags.append('tone')
            if alternate_flag and str(alternate_flag).lower() in ('true', 't', '1'):
                flags.append('alternate')
            if repeat_val and int(repeat_val) > 1:
                flags.append(f'repeat={int(repeat_val)}')
            if interval_seconds:
                try:
                    iv = int(interval_seconds)
                    if iv % 86400 == 0:
                        flags.append(f'interval={iv // 86400}d')
                    elif iv % 3600 == 0:
                        flags.append(f'interval={iv // 3600}h')
                    elif iv % 60 == 0:
                        flags.append(f'interval={iv // 60}m')
                    else:
                        flags.append(f'interval={iv}s')
                except Exception:
                    flags.append(f'interval={interval_seconds}')
            flagstr = f" [{', '.join(flags)}]" if flags else ''
            lines.append(f'`{aid}` -> {msg or "(no message)"}{flagstr} (fires at {fire_at})')

        await interaction.response.send_message('\n'.join(lines), ephemeral=True)

    @app_commands.command(name='cancel', description='Cancel a scheduled alarm by id')
    @app_commands.describe(id='Alarm id to cancel (use /alarm list to see ids). Use `all` to cancel all alarms for this guild')
    async def cancel(self, interaction: discord.Interaction, id: str):
        if not await require_guild(interaction):
            return

        if id == 'all':
            try:
                rows = db.get_alarms_for_guild(interaction.guild.id)
            except Exception:
                rows = []
            count = 0
            for r in rows:
                aid = r[0]
                t = ALARM_TASKS.pop(aid, None)
                if t:
                    t.cancel()
                try:
                    db.delete_alarm(aid)
                except Exception:
                    pass
                count += 1
            await interaction.response.send_message(f'Cancelled {count} alarm(s).', ephemeral=True)
            return

        try:
            row = db.execute_query('SELECT id FROM main.alarms WHERE id = %s AND guild_id = %s', (id, interaction.guild.id))
            if not row:
                await interaction.response.send_message('Alarm id not found.', ephemeral=True)
                return
        except Exception as e:
            logger.error(f"DB error cancelling alarm: {e}")
            await send_error(interaction, f'DB error: {e}')
            return

        t = ALARM_TASKS.pop(id, None)
        if t:
            t.cancel()
        try:
            db.delete_alarm(id)
        except Exception:
            pass

        await interaction.response.send_message(f'Cancelled alarm `{id}`.', ephemeral=True)
