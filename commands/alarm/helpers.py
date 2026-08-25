"""Alarm scheduling/playback worker (moved verbatim from the old
commands/alarm_commands.py -- background-task logic, not command-shape) plus
pure time/interval parsing helpers used by the `set` modal.
"""
import asyncio
import uuid
import datetime as dt
import tempfile
import subprocess
from zoneinfo import ZoneInfo
import os
from typing import Dict, Optional, Tuple

import discord

from database import db
from utils.logger import logger
from utils.tts_helper import synthesize_tts_to_file
from utils.ffmpeg_helper import which_ffmpeg

# In-process scheduled tasks for alarms: alarm_id -> asyncio.Task
ALARM_TASKS: Dict[str, asyncio.Task] = {}


def parse_relative_or_absolute_time(time: str, tz: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    """Parse '"in 10m"' or an absolute 'YYYY-MM-DD HH:MM' (optionally with tz)
    into (delay_seconds, error_message). Exactly one of the two is None."""
    now = dt.datetime.utcnow()

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
                total += {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[ch] * n
                num = ''
        if num:
            total += int(num)
        delay = total
    else:
        try:
            naive_dt = dt.datetime.fromisoformat(time) if 'T' in time else dt.datetime.strptime(time, '%Y-%m-%d %H:%M')

            if tz:
                try:
                    if tz.startswith('+') or tz.startswith('-'):
                        sign = 1 if tz[0] == '+' else -1
                        parts = tz[1:].split(':')
                        hh = int(parts[0])
                        mm = int(parts[1]) if len(parts) > 1 else 0
                        tzinfo = dt.timezone(dt.timedelta(hours=hh, minutes=mm) * sign)
                    else:
                        tzinfo = ZoneInfo(tz)
                    fire_dt = naive_dt.replace(tzinfo=tzinfo).astimezone(dt.timezone.utc)
                except Exception:
                    return None, 'Invalid timezone provided. Use IANA zone name like "Europe/London" or offset like "+02:00".'
            else:
                fire_dt = naive_dt.replace(tzinfo=dt.timezone.utc) if naive_dt.tzinfo is None else naive_dt.astimezone(dt.timezone.utc)

            delay = (fire_dt - now).total_seconds()
        except Exception:
            delay = None

    if delay is None or delay <= 0:
        return None, 'Could not parse time. Use "in 10m" or "YYYY-MM-DD HH:MM".'
    return delay, None


def parse_interval(spec: str) -> Optional[int]:
    """Parse 'daily'/'hourly'/'in 1h30m'/'30m' into seconds, or None if invalid."""
    s = spec.strip().lower()
    if s in ('daily', 'day'):
        return 86400
    if s in ('hourly', 'hour'):
        return 3600
    if s.startswith('in '):
        s = s[3:]
    total = 0
    num = ''
    for ch in s:
        if ch.isdigit():
            num += ch
            continue
        if ch in ('s', 'm', 'h', 'd') and num:
            total += {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[ch] * int(num)
            num = ''
    if num:
        total += int(num)
    return total if total > 0 else None


async def _alarm_worker(bot: discord.Client, alarm_id: str, guild_id: int, creator_id: int, channel_id: int, message: str, tts: bool, tone: bool, alternate: bool, repeat: int = 1, interval_seconds: int = None):
    try:
        ffmpeg_exec = which_ffmpeg() or 'ffmpeg'

        rows = db.execute_query("SELECT fire_at FROM main.alarms WHERE id = %s", (alarm_id,))
        if not rows:
            return
        fire_at = rows[0][0]
        now = dt.datetime.now(dt.timezone.utc)

        if isinstance(fire_at, str):
            try:
                fire_dt = dt.datetime.fromisoformat(fire_at)
            except Exception:
                fire_dt = dt.datetime.strptime(fire_at, "%Y-%m-%d %H:%M:%S")
        else:
            fire_dt = fire_at

        if isinstance(fire_dt, dt.datetime) and fire_dt.tzinfo is None:
            fire_dt = fire_dt.replace(tzinfo=dt.timezone.utc)

        while True:
            delay = (fire_dt - dt.datetime.now(dt.timezone.utc)).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)

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

            if guild and guild.voice_client and guild.voice_client.is_connected():
                vc = guild.voice_client

                async def _play_and_wait(path: str):
                    try:
                        from discord import FFmpegOpusAudio
                        try:
                            ver = subprocess.run([ffmpeg_exec, '-version'], check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=5)
                            logger.info('Using ffmpeg: %s', ver.stdout.splitlines()[0] if ver and ver.stdout else ffmpeg_exec)
                        except Exception as e:
                            logger.warning('Could not run ffmpeg -version: %s', e)

                        vol_str = os.getenv('BRADBOT_FFMPEG_VOLUME', '1.0')
                        try:
                            vol = float(vol_str)
                        except Exception:
                            vol = 1.0
                        try:
                            size = os.path.getsize(path)
                        except Exception:
                            size = None
                        logger.info('Playing file size=%s bytes path=%s', size, path)

                        opus_opts = f"-vn -af volume={vol} -ar 48000 -ac 2"
                        audio = FFmpegOpusAudio(path, executable=ffmpeg_exec, options=opus_opts)

                        try:
                            me = guild.me
                            if me and me.voice:
                                logger.info('Bot voice state: self_mute=%s self_deaf=%s server_mute=%s server_deaf=%s', me.voice.self_mute, me.voice.self_deaf, me.voice.mute, me.voice.deaf)
                        except Exception:
                            pass
                        try:
                            vc.stop()
                        except Exception:
                            pass
                        logger.info('Starting playback: guild=%s channel=%s path=%s', guild_id, channel_id, path)
                        vc.play(audio)
                        await asyncio.sleep(0.1)
                        logger.info('Playback started? is_playing=%s is_paused=%s', vc.is_playing(), vc.is_paused())
                        while vc.is_playing() or vc.is_paused():
                            await asyncio.sleep(0.2)
                        logger.info('Playback finished: guild=%s channel=%s', guild_id, channel_id)

                        try:
                            if os.getenv('BRADBOT_DEBUG_UPLOAD_AUDIO', 'false').lower() in ('1', 'true', 'yes') and channel:
                                with open(path, 'rb') as f:
                                    await channel.send('Uploading played audio for debugging:', file=discord.File(f, filename=os.path.basename(path)))
                        except Exception:
                            logger.exception('Failed to upload debug audio')
                    finally:
                        try:
                            os.remove(path)
                        except Exception:
                            pass

                try:
                    rep = int(repeat or 1)
                    if rep == 0:
                        try:
                            while True:
                                if alternate and tone and tts:
                                    try:
                                        tmp_fd, tmp_tone1 = tempfile.mkstemp(suffix='.wav')
                                        os.close(tmp_fd)
                                        try:
                                            subprocess.run([ffmpeg_exec, '-f', 'lavfi', '-i', 'sine=frequency=880:duration=2', '-ar', '48000', '-ac', '2', '-y', tmp_tone1], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                                            size = os.path.getsize(tmp_tone1) if os.path.exists(tmp_tone1) else None
                                            logger.info('Generated tone file %s size=%s', tmp_tone1, size)
                                            await _play_and_wait(tmp_tone1)
                                        except Exception as e:
                                            logger.exception('Failed to generate initial tone (continuous): %s', e)
                                            try:
                                                os.remove(tmp_tone1)
                                            except Exception:
                                                pass
                                    except Exception:
                                        try:
                                            os.remove(tmp_tone1)
                                        except Exception:
                                            pass

                                    try:
                                        tmp_fd, tmp_tts = tempfile.mkstemp(suffix='.mp3')
                                        os.close(tmp_fd)
                                        synthesize_tts_to_file(message or 'Alarm', tmp_tts)
                                        await _play_and_wait(tmp_tts)
                                    except Exception as e:
                                        logger.error(f'TTS generation/playback failed: {e}')
                                        logger.exception('TTS generation/playback failed: %s', e)
                                        try:
                                            os.remove(tmp_tts)
                                        except Exception:
                                            pass

                                    try:
                                        tmp_fd, tmp_tone2 = tempfile.mkstemp(suffix='.wav')
                                        os.close(tmp_fd)
                                        try:
                                            subprocess.run([ffmpeg_exec, '-f', 'lavfi', '-i', 'sine=frequency=880:duration=1', '-ar', '48000', '-ac', '2', '-y', tmp_tone2], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                                            size2 = os.path.getsize(tmp_tone2) if os.path.exists(tmp_tone2) else None
                                            logger.info('Generated final tone file %s size=%s', tmp_tone2, size2)
                                            await _play_and_wait(tmp_tone2)
                                        except Exception as e:
                                            logger.exception('Failed to generate final tone (continuous): %s', e)
                                            try:
                                                os.remove(tmp_tone2)
                                            except Exception:
                                                pass
                                    except Exception:
                                        try:
                                            os.remove(tmp_tone2)
                                        except Exception:
                                            pass
                                else:
                                    if tone:
                                        try:
                                            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.wav')
                                            os.close(tmp_fd)
                                            try:
                                                subprocess.run([ffmpeg_exec, '-f', 'lavfi', '-i', 'sine=frequency=880:duration=4', '-ar', '48000', '-ac', '2', '-y', tmp_path], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                                                sizep = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else None
                                                logger.info('Generated fallback tone file %s size=%s', tmp_path, sizep)
                                                await _play_and_wait(tmp_path)
                                            except Exception as e:
                                                logger.exception('Failed to generate fallback tone (continuous): %s', e)
                                                try:
                                                    os.remove(tmp_path)
                                                except Exception:
                                                    pass
                                        except Exception:
                                            try:
                                                os.remove(tmp_path)
                                            except Exception:
                                                pass
                                    elif tts:
                                        try:
                                            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.mp3')
                                            os.close(tmp_fd)
                                            synthesize_tts_to_file(message or 'Alarm', tmp_path)
                                            await _play_and_wait(tmp_path)
                                        except Exception as e:
                                            logger.error(f'TTS generation/playback failed: {e}')
                                            logger.exception('TTS generation/playback failed: %s', e)
                                            try:
                                                os.remove(tmp_path)
                                            except Exception:
                                                pass

                                await asyncio.sleep(0.5)
                        except asyncio.CancelledError:
                            try:
                                vc.stop()
                            except Exception:
                                pass
                            raise
                    else:
                        for i in range(max(1, rep)):
                            if alternate and tone and tts:
                                try:
                                    tmp_fd, tmp_tone1 = tempfile.mkstemp(suffix='.wav')
                                    os.close(tmp_fd)
                                    try:
                                        subprocess.run(['ffmpeg', '-f', 'lavfi', '-i', 'sine=frequency=880:duration=2', '-ar', '48000', '-ac', '2', '-y', tmp_tone1], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                                        size = os.path.getsize(tmp_tone1) if os.path.exists(tmp_tone1) else None
                                        logger.info('Generated tone file %s size=%s', tmp_tone1, size)
                                        await _play_and_wait(tmp_tone1)
                                    except Exception as e:
                                        logger.exception('Failed to generate initial tone: %s', e)
                                        try:
                                            os.remove(tmp_tone1)
                                        except Exception:
                                            pass
                                except Exception:
                                    try:
                                        os.remove(tmp_tone1)
                                    except Exception:
                                        pass

                                try:
                                    tmp_fd, tmp_tts = tempfile.mkstemp(suffix='.mp3')
                                    os.close(tmp_fd)
                                    synthesize_tts_to_file(message or 'Alarm', tmp_tts)
                                    await _play_and_wait(tmp_tts)
                                except Exception:
                                    try:
                                        os.remove(tmp_tts)
                                    except Exception:
                                        pass

                                try:
                                    tmp_fd, tmp_tone2 = tempfile.mkstemp(suffix='.wav')
                                    os.close(tmp_fd)
                                    try:
                                        subprocess.run(['ffmpeg', '-f', 'lavfi', '-i', 'sine=frequency=880:duration=1', '-ar', '48000', '-ac', '2', '-y', tmp_tone2], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                                        size2 = os.path.getsize(tmp_tone2) if os.path.exists(tmp_tone2) else None
                                        logger.info('Generated final tone file %s size=%s', tmp_tone2, size2)
                                        await _play_and_wait(tmp_tone2)
                                    except Exception as e:
                                        logger.exception('Failed to generate final tone: %s', e)
                                        try:
                                            os.remove(tmp_tone2)
                                        except Exception:
                                            pass
                                except Exception:
                                    try:
                                        os.remove(tmp_tone2)
                                    except Exception:
                                        pass
                            else:
                                if tone:
                                    try:
                                        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.wav')
                                        os.close(tmp_fd)
                                        try:
                                            subprocess.run(['ffmpeg', '-f', 'lavfi', '-i', 'sine=frequency=880:duration=4', '-ar', '48000', '-ac', '2', '-y', tmp_path], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                                            sizep = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else None
                                            logger.info('Generated fallback tone file %s size=%s', tmp_path, sizep)
                                            await _play_and_wait(tmp_path)
                                        except Exception as e:
                                            logger.exception('Failed to generate fallback tone: %s', e)
                                            try:
                                                os.remove(tmp_path)
                                            except Exception:
                                                pass
                                    except Exception:
                                        try:
                                            os.remove(tmp_path)
                                        except Exception:
                                            pass
                                elif tts:
                                    try:
                                        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.mp3')
                                        os.close(tmp_fd)
                                        synthesize_tts_to_file(message or 'Alarm', tmp_path)
                                        await _play_and_wait(tmp_path)
                                    except Exception:
                                        try:
                                            os.remove(tmp_path)
                                        except Exception:
                                            pass

                            await asyncio.sleep(0.5)
                except Exception:
                    pass

            try:
                if interval_seconds and int(interval_seconds) > 0:
                    try:
                        next_fire = fire_dt + dt.timedelta(seconds=int(interval_seconds))
                        next_fire_iso = next_fire.astimezone(dt.timezone.utc).isoformat() if next_fire.tzinfo else next_fire.replace(tzinfo=dt.timezone.utc).isoformat()
                        db.execute_query('UPDATE main.alarms SET fire_at = %s WHERE id = %s', (next_fire_iso, alarm_id), fetch=False)
                        fire_dt = next_fire
                        continue
                    except Exception:
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
                pass

    finally:
        ALARM_TASKS.pop(alarm_id, None)


def schedule_alarm_task(bot: discord.Client, alarm_row: tuple):
    """Schedule an alarm given a DB row: (id, guild_id, creator_id, channel_id, message, tts, tone, alternate, repeat, interval_seconds, fire_at)"""
    aid, guild_id, creator_id, channel_id, message, tts, tone, alternate, repeat, interval_seconds, fire_at = alarm_row
    try:
        fire_dt = dt.datetime.fromisoformat(fire_at) if isinstance(fire_at, str) else fire_at
    except Exception:
        try:
            fire_dt = dt.datetime.strptime(str(fire_at), "%Y-%m-%d %H:%M:%S")
        except Exception:
            fire_dt = dt.datetime.now(dt.timezone.utc)

    if isinstance(fire_dt, dt.datetime) and fire_dt.tzinfo is None:
        fire_dt = fire_dt.replace(tzinfo=dt.timezone.utc)

    delay = (fire_dt - dt.datetime.now(dt.timezone.utc)).total_seconds()
    if delay < 0:
        delay = 0

    task = asyncio.create_task(_alarm_worker(bot, aid, guild_id, creator_id, channel_id, message, tts, tone, alternate, repeat, interval_seconds))
    ALARM_TASKS[aid] = task


def schedule_all_existing_alarms(bot: discord.Client):
    rows = db.get_all_pending_alarms()
    for row in rows:
        schedule_alarm_task(bot, row)
