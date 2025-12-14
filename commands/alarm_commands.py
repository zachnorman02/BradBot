import asyncio
import uuid
import datetime as dt
import tempfile
import subprocess
from zoneinfo import ZoneInfo
import os
from typing import Dict

import discord
from discord import app_commands
import shutil
import logging

from database import db

logger = logging.getLogger('bradbot.alarm')

# In-process scheduled tasks for alarms: alarm_id -> asyncio.Task
ALARM_TASKS: Dict[str, asyncio.Task] = {}


def _seconds_until(fire_at_str: str) -> float:
    try:
        then = dt.datetime.fromisoformat(fire_at_str)
    except Exception:
        try:
            then = dt.datetime.strptime(fire_at_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            # give up
            return -1
    # normalize to UTC-aware
    if isinstance(then, dt.datetime) and then.tzinfo is None:
        then = then.replace(tzinfo=dt.timezone.utc)
    now = dt.datetime.now(dt.timezone.utc)
    return (then - now).total_seconds()


async def _alarm_worker(bot: discord.Client, alarm_id: str, guild_id: int, creator_id: int, channel_id: int, message: str, tts: bool, tone: bool, alternate: bool, repeat: int = 1, interval_seconds: int = None):
    try:
        # fetch the alarm row to get the fire_at
        rows = db.execute_query("SELECT fire_at FROM main.alarms WHERE id = %s", (alarm_id,))
        if not rows:
            return
        fire_at = rows[0][0]
        # compute delay
        # use timezone-aware UTC 'now'
        now = dt.datetime.now(dt.timezone.utc)

        if isinstance(fire_at, str):
            try:
                fire_dt = dt.datetime.fromisoformat(fire_at)
            except Exception:
                fire_dt = dt.datetime.strptime(fire_at, "%Y-%m-%d %H:%M:%S")
        else:
            fire_dt = fire_at

        # normalize fire_dt to UTC-aware
        if isinstance(fire_dt, dt.datetime) and fire_dt.tzinfo is None:
            fire_dt = fire_dt.replace(tzinfo=dt.timezone.utc)

        # Main loop: fire, then if interval_seconds is set, update fire_at and loop for next occurrence.
        while True:
            delay = (fire_dt - dt.datetime.now(dt.timezone.utc)).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)

            # Send message to channel
            guild = bot.get_guild(guild_id)
            channel = None
            if guild:
                channel = guild.get_channel(channel_id)
            if not channel:
                channel = bot.get_channel(channel_id)

            content = f"⏰ Alarm: {message or '(no message)'}"
            try:
                if creator_id:
                    content = f"<@{creator_id}> - " + content
            except Exception:
                pass

            try:
                if channel:
                    await channel.send(content)
            except Exception:
                pass

            # Play TTS or tone in voice if requested and bot is connected
            if guild and guild.voice_client and guild.voice_client.is_connected():
                vc = guild.voice_client

                async def _play_and_wait(path: str):
                    try:
                        from discord import FFmpegPCMAudio
                        # prefer system ffmpeg if available
                        ffmpeg_exec = shutil.which('ffmpeg') or 'ffmpeg'
                        try:
                            # log ffmpeg version for diagnostics
                            ver = subprocess.run([ffmpeg_exec, '-version'], check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=5)
                            logger.info('Using ffmpeg: %s', ver.stdout.splitlines()[0] if ver and ver.stdout else ffmpeg_exec)
                        except Exception as e:
                            logger.warning('Could not run ffmpeg -version: %s', e)

                        # Respect optional runtime volume multiplier via env var
                        vol_str = os.getenv('BRADBOT_FFMPEG_VOLUME', '1.0')
                        try:
                            vol = float(vol_str)
                        except Exception:
                            vol = 1.0
                        # FFmpeg options: force 48kHz, stereo PCM and apply volume filter
                        ffmpeg_options = f"-f s16le -ar 48000 -ac 2 -af volume={vol}"
                        audio = FFmpegPCMAudio(path, executable=ffmpeg_exec, options=ffmpeg_options)

                        # Log bot voice state (muted/deafened) for diagnostics
                        try:
                            me = guild.me
                            if me and me.voice:
                                logger.info('Bot voice state: self_mute=%s self_deaf=%s server_mute=%s server_deaf=%s', me.voice.self_mute, me.voice.self_deaf, me.voice.mute, me.voice.deaf)
                        except Exception:
                            pass
                        # stop any current playback and play immediately
                        try:
                            vc.stop()
                        except Exception:
                            pass
                        logger.info('Starting playback: guild=%s channel=%s path=%s', guild_id, channel_id, path)
                        vc.play(audio)
                        # small delay to let playback start, then log state
                        await asyncio.sleep(0.1)
                        logger.info('Playback started? is_playing=%s is_paused=%s', vc.is_playing(), vc.is_paused())
                        # wait for playback to finish
                        while vc.is_playing() or vc.is_paused():
                            await asyncio.sleep(0.2)
                        logger.info('Playback finished: guild=%s channel=%s', guild_id, channel_id)
                    finally:
                        try:
                            os.remove(path)
                        except Exception:
                            pass

                try:
                    # Repeat the chosen playback pattern 'repeat' times (small pause between iterations)
                    for i in range(max(1, int(repeat or 1))):
                        # Alternate pattern: tone -> TTS -> tone
                        if alternate and tone and tts:
                            # initial tone
                            try:
                                tmp_fd, tmp_tone1 = tempfile.mkstemp(suffix='.wav')
                                os.close(tmp_fd)
                                subprocess.run([
                                    'ffmpeg', '-f', 'lavfi', '-i', 'sine=frequency=880:duration=2', '-ar', '48000', '-ac', '2', '-y', tmp_tone1
                                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                await _play_and_wait(tmp_tone1)
                            except Exception:
                                try:
                                    os.remove(tmp_tone1)
                                except Exception:
                                    pass

                            # TTS
                            try:
                                from gtts import gTTS
                                tmp_fd, tmp_tts = tempfile.mkstemp(suffix='.mp3')
                                os.close(tmp_fd)
                                t = gTTS(text=message or 'Alarm', lang='en')
                                t.save(tmp_tts)
                                await _play_and_wait(tmp_tts)
                            except Exception:
                                try:
                                    os.remove(tmp_tts)
                                except Exception:
                                    pass

                            # final tone (short)
                            try:
                                tmp_fd, tmp_tone2 = tempfile.mkstemp(suffix='.wav')
                                os.close(tmp_fd)
                                subprocess.run([
                                    'ffmpeg', '-f', 'lavfi', '-i', 'sine=frequency=880:duration=1', '-ar', '48000', '-ac', '2', '-y', tmp_tone2
                                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                await _play_and_wait(tmp_tone2)
                            except Exception:
                                try:
                                    os.remove(tmp_tone2)
                                except Exception:
                                    pass

                        else:
                            # fallback: tone or tts only
                            if tone:
                                try:
                                    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.wav')
                                    os.close(tmp_fd)
                                    subprocess.run([
                                        'ffmpeg', '-f', 'lavfi', '-i', 'sine=frequency=880:duration=4', '-ar', '48000', '-ac', '2', '-y', tmp_path
                                    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                    await _play_and_wait(tmp_path)
                                except Exception:
                                    try:
                                        os.remove(tmp_path)
                                    except Exception:
                                        pass
                            elif tts:
                                try:
                                    from gtts import gTTS
                                    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.mp3')
                                    os.close(tmp_fd)
                                    t = gTTS(text=message or 'Alarm', lang='en')
                                    t.save(tmp_path)
                                    await _play_and_wait(tmp_path)
                                except Exception:
                                    try:
                                        os.remove(tmp_path)
                                    except Exception:
                                        pass

                        # small pause between repeats
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

            # After firing: if interval_seconds provided, reschedule; otherwise mark fired and exit.
            try:
                if interval_seconds and int(interval_seconds) > 0:
                    # compute next fire time and update DB
                    try:
                        next_fire = fire_dt + dt.timedelta(seconds=int(interval_seconds))
                        next_fire_iso = next_fire.astimezone(dt.timezone.utc).isoformat() if next_fire.tzinfo else next_fire.replace(tzinfo=dt.timezone.utc).isoformat()
                        db.execute_query('UPDATE main.alarms SET fire_at = %s WHERE id = %s', (next_fire_iso, alarm_id), fetch=False)
                        # prepare for next loop
                        fire_dt = next_fire
                        continue
                    except Exception:
                        # if updating DB fails, just mark as fired and exit
                        try:
                            db.mark_alarm_fired(alarm_id)
                        except Exception:
                            pass
                        break
                else:
                    try:
                        db.mark_alarm_fired(alarm_id)
                    except Exception:
                        pass
                    break
            finally:
                # ensure we clean up mapping only when truly finished
                pass

    finally:
        # remove scheduled task mapping
        ALARM_TASKS.pop(alarm_id, None)


def schedule_alarm_task(bot: discord.Client, alarm_row: tuple):
    """Schedule an alarm given a DB row: (id, guild_id, creator_id, channel_id, message, tts, tone, alternate, repeat, interval_seconds, fire_at)"""
    aid, guild_id, creator_id, channel_id, message, tts, tone, alternate, repeat, interval_seconds, fire_at = alarm_row
    # compute delay; if negative, schedule to fire immediately
    try:
        if isinstance(fire_at, str):
            fire_dt = dt.datetime.fromisoformat(fire_at)
        else:
            fire_dt = fire_at
    except Exception:
        try:
            fire_dt = dt.datetime.strptime(str(fire_at), "%Y-%m-%d %H:%M:%S")
        except Exception:
            fire_dt = dt.datetime.now(dt.timezone.utc)

    # normalize to UTC-aware
    if isinstance(fire_dt, dt.datetime) and fire_dt.tzinfo is None:
        fire_dt = fire_dt.replace(tzinfo=dt.timezone.utc)

    delay = (fire_dt - dt.datetime.now(dt.timezone.utc)).total_seconds()
    if delay < 0:
        delay = 0

    # create task
    task = asyncio.create_task(_alarm_worker(bot, aid, guild_id, creator_id, channel_id, message, tts, tone, alternate, repeat, interval_seconds))
    ALARM_TASKS[aid] = task


def schedule_all_existing_alarms(bot: discord.Client):
    rows = db.get_all_pending_alarms()
    for row in rows:
        # row: id, guild_id, creator_id, channel_id, message, tts, tone, alternate, repeat, fire_at
        schedule_alarm_task(bot, row)


class AlarmGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name='alarm', description='Set simple alarms (message or TTS)')

    @app_commands.command(name='set', description='Set an alarm. Example: "in 10m" or "2025-12-31 08:00"')
    @app_commands.describe(time='Relative (e.g. "in 10m") or absolute (YYYY-MM-DD HH:MM)', message='Message to send when alarm fires', channel='Channel to send the alarm to (defaults to current channel)', tts='If true, try to speak the message in voice if connected', tone='If true, play a loud tone in voice instead of TTS', alternate='If true and both tone+tts are set, alternate tone and TTS (tone->tts->tone)', repeat='Number of times to play the alarm audio (default 1, max 10)', interval='Optional recurrence interval (e.g. "daily", "hourly", or "in 1h30m")', tz='Optional timezone for absolute times (e.g. "Europe/London" or "+02:00")')
    async def set(self, interaction: discord.Interaction, time: str, message: str = None, channel: discord.TextChannel = None, tts: bool = False, tone: bool = False, alternate: bool = False, repeat: int = 1, interval: str = None, tz: str = None):
        if not interaction.guild:
            await interaction.response.send_message('❌ Alarms must be set in a server.', ephemeral=True)
            return

        # Parse 'in X' basic format or absolute YYYY-MM-DD HH:MM
        # Support relative 'in 10m' or 'in 1h30m'
        now = dt.datetime.utcnow()
        delay = None
        if time.startswith('in '):
            spec = time[3:]
            total = 0
            num = ''
            for ch in spec:
                if ch.isdigit():
                    num += ch
                    continue
                if ch in ('s', 'm', 'h', 'd') and num:
                    n = int(num)
                    if ch == 's':
                        total += n
                    elif ch == 'm':
                        total += n * 60
                    elif ch == 'h':
                        total += n * 3600
                    elif ch == 'd':
                        total += n * 86400
                    num = ''
            if num:
                total += int(num)
            delay = total
        else:
                # absolute
                try:
                    # parse naive local time first
                    if 'T' in time:
                        naive_dt = dt.datetime.fromisoformat(time)
                    else:
                        naive_dt = dt.datetime.strptime(time, '%Y-%m-%d %H:%M')

                    # apply timezone if provided
                    if tz:
                        try:
                            if tz.startswith('+') or tz.startswith('-'):
                                # parse offset like +02:00
                                sign = 1 if tz[0] == '+' else -1
                                parts = tz[1:].split(':')
                                hh = int(parts[0])
                                mm = int(parts[1]) if len(parts) > 1 else 0
                                offset = dt.timedelta(hours=hh, minutes=mm) * sign
                                tzinfo = dt.timezone(offset)
                            else:
                                tzinfo = ZoneInfo(tz)
                            aware = naive_dt.replace(tzinfo=tzinfo)
                            fire_dt = aware.astimezone(dt.timezone.utc)
                        except Exception:
                            # failed to apply zoneinfo - consider input invalid
                            await interaction.response.send_message('❌ Invalid timezone provided. Use IANA zone name like "Europe/London" or offset like "+02:00".', ephemeral=True)
                            return
                    else:
                        # no timezone - assume UTC for absolute times
                        if isinstance(naive_dt, dt.datetime) and naive_dt.tzinfo is None:
                            fire_dt = naive_dt.replace(tzinfo=dt.timezone.utc)
                        else:
                            # if it already has tzinfo, normalize to UTC
                            fire_dt = naive_dt.astimezone(dt.timezone.utc)

                    delay = (fire_dt - now).total_seconds()
                except Exception:
                    delay = None

        if delay is None or delay <= 0:
            await interaction.response.send_message('❌ Could not parse time. Use "in 10m" or "YYYY-MM-DD HH:MM".', ephemeral=True)
            return

        if channel is None:
            channel = interaction.channel

        fire_dt = now + dt.timedelta(seconds=delay)
        # store as ISO in UTC (fire_dt is already UTC-aware)
        fire_at_iso = fire_dt.astimezone(dt.timezone.utc).isoformat()
        aid = uuid.uuid4().hex[:8]
        try:
            # sanitize repeat
            try:
                repeat_val = int(repeat)
            except Exception:
                repeat_val = 1
            if repeat_val < 1:
                repeat_val = 1
            if repeat_val > 10:
                repeat_val = 10

            # parse interval into seconds if provided
            interval_seconds = None
            if interval:
                def _parse_interval(spec: str):
                    s = spec.strip().lower()
                    if s in ('daily', 'day'):
                        return 86400
                    if s in ('hourly', 'hour'):
                        return 3600
                    # support formats like 'in 1h30m' or '1h30m' or '30m'
                    if s.startswith('in '):
                        s = s[3:]
                    total = 0
                    num = ''
                    for ch in s:
                        if ch.isdigit():
                            num += ch
                            continue
                        if ch in ('s', 'm', 'h', 'd') and num:
                            n = int(num)
                            if ch == 's':
                                total += n
                            elif ch == 'm':
                                total += n * 60
                            elif ch == 'h':
                                total += n * 3600
                            elif ch == 'd':
                                total += n * 86400
                            num = ''
                    if num:
                        total += int(num)
                    return total if total > 0 else None

                try:
                    interval_seconds = _parse_interval(interval)
                    if interval_seconds is None:
                        await interaction.response.send_message('❌ Could not parse interval. Use "daily", "hourly", or formats like "in 1h30m".', ephemeral=True)
                        return
                except Exception:
                    await interaction.response.send_message('❌ Could not parse interval. Use "daily", "hourly", or formats like "in 1h30m".', ephemeral=True)
                    return

            db.add_alarm(aid, interaction.guild.id, interaction.user.id, channel.id, message, tts, tone, alternate, repeat_val, interval_seconds, fire_at_iso)
        except Exception as e:
            await interaction.response.send_message(f'❌ Failed to save alarm: {e}', ephemeral=True)
            return

        # schedule
        schedule_alarm_task(interaction.client, (aid, interaction.guild.id, interaction.user.id, channel.id, message, tts, tone, alternate, repeat_val, interval_seconds, fire_at_iso))

        await interaction.response.send_message(f'✅ Alarm set (id: `{aid}`) to fire <t:{int((now + dt.timedelta(seconds=delay)).timestamp())}:F>.', ephemeral=True)

    @app_commands.command(name='list', description='List scheduled alarms for this server')
    async def list(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message('❌ Use this in a server.', ephemeral=True)
            return

        try:
            rows = db.get_alarms_for_guild(interaction.guild.id)
        except Exception as e:
            await interaction.response.send_message(f'❌ Failed to query alarms: {e}', ephemeral=True)
            return

        if not rows:
            await interaction.response.send_message('No alarms scheduled.', ephemeral=True)
            return

        lines = []
        for r in rows:
            # rows: id, guild_id, creator_id, channel_id, message, tts, tone, alternate, repeat, interval_seconds, fire_at
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
        if not interaction.guild:
            await interaction.response.send_message('❌ Use this in a server.', ephemeral=True)
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

        # single id
        try:
            row = db.execute_query('SELECT id FROM main.alarms WHERE id = %s AND guild_id = %s', (id, interaction.guild.id))
            if not row:
                await interaction.response.send_message('Alarm id not found.', ephemeral=True)
                return
        except Exception as e:
            await interaction.response.send_message(f'❌ DB error: {e}', ephemeral=True)
            return

        t = ALARM_TASKS.pop(id, None)
        if t:
            t.cancel()
        try:
            db.delete_alarm(id)
        except Exception:
            pass

        await interaction.response.send_message(f'Cancelled alarm `{id}`.', ephemeral=True)
