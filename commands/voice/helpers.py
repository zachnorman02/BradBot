"""Per-guild audio queue player and TTS option data for the voice domain."""
import asyncio

import discord

from utils.logger import logger

# Simple per-guild audio player
PLAYERS: dict[int, 'GuildPlayer'] = {}

AVAILABLE_VOICES = [
    "Aditi", "Amy", "Astrid", "Bianca", "Brian", "Camila", "Carla", "Carmen", "Celine", "Chantal", "Conchita", "Cristiano", "Dora", "Emma", "Enrique", "Ewa", "Filiz", "Gabrielle", "Geraint", "Giorgio", "Gwyneth", "Hans", "Ines", "Ivy", "Jacek", "Jan", "Joanna", "Joey", "Justin", "Karl", "Kendra", "Kevin", "Kimberly", "Lea", "Liv", "Lotte", "Lucia", "Lupe", "Mads", "Maja", "Marlene", "Mathieu", "Matthew", "Maxim", "Mia", "Miguel", "Mizuki", "Naja", "Nicole", "Olivia", "Penelope", "Raveena", "Ricardo", "Ruben", "Russell", "Salli", "Seoyeon", "Takumi", "Tatyana", "Vicki", "Vitoria", "Zeina", "Zhiyu", "Aria", "Ayanda", "Arlet", "Hannah", "Arthur", "Daniel", "Liam", "Pedro", "Kajal", "Hiujin", "Laura", "Elin", "Ida", "Suvi", "Ola", "Hala", "Andres", "Sergio", "Remi", "Adriano", "Thiago", "Ruth", "Stephen", "Kazuha", "Tomoko", "Niamh", "Sofie", "Lisa", "Isabelle", "Zayd", "Danielle", "Gregory", "Burcu", "Jitka", "Sabrina", "Jasmine", "Jihye",
]

TTS_ENGINES = ["standard", "neural", "long-form", "generative"]

TTS_LANGUAGES = [
    "arb", "cmn-CN", "cy-GB", "da-DK", "de-DE", "en-AU", "en-GB", "en-GB-WLS", "en-IN", "en-US", "es-ES", "es-MX",
    "es-US", "fr-CA", "fr-FR", "is-IS", "it-IT", "ja-JP", "hi-IN", "ko-KR", "nb-NO", "nl-NL", "pl-PL", "pt-BR",
    "pt-PT", "ro-RO", "ru-RU", "sv-SE", "tr-TR", "en-NZ", "en-ZA", "ca-ES", "de-AT", "yue-CN", "ar-AE", "fi-FI",
    "en-IE", "nl-BE", "fr-BE", "cs-CZ", "de-CH", "en-SG",
]


class GuildPlayer:
    def __init__(self, guild_id: int, bot):
        self.guild_id = guild_id
        self.bot = bot
        self.queue: asyncio.Queue = asyncio.Queue()
        self.playing = False
        self._pending: list[dict] = []
        self.current: dict | None = None

    async def ensure_connected(self, channel: discord.VoiceChannel):
        vc = channel.guild.voice_client
        if vc and vc.is_connected():
            if vc.channel.id != channel.id:
                await vc.move_to(channel)
            return vc
        return await channel.connect()

    async def enqueue(self, source):
        try:
            self._pending.append(source)
        except Exception:
            pass

        await self.queue.put(source)
        if not self.playing:
            asyncio.create_task(self._play_next())

    async def _play_next(self):
        if self.queue.empty():
            self.playing = False
            return
        self.playing = True
        try:
            source = await self.queue.get()
        except Exception:
            self.playing = False
            return

        if self._pending:
            try:
                self._pending.pop(0)
            except Exception:
                pass

        try:
            self.current = source
        except Exception:
            self.current = None

        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            self.playing = False
            self.current = None
            return

        vc = guild.voice_client
        if not vc or not vc.is_connected():
            attempts = 0
            while attempts < 5:
                await asyncio.sleep(1)
                vc = guild.voice_client
                if vc and vc.is_connected():
                    break
                attempts += 1

            if not vc or not vc.is_connected():
                self.playing = False
                self.current = None
                return

        try:
            audio = source.get('audio')
            volume = source.get('volume', 0.5)
            player = discord.PCMVolumeTransformer(audio, volume=volume)
            cleanup = source.get('cleanup')

            def _after(err):
                if cleanup:
                    try:
                        cleanup()
                    except Exception as cleanup_error:
                        logger.error(f"Cleanup error: {cleanup_error}")
                if err:
                    logger.error(f"Playback error: {err}")
                try:
                    asyncio.run_coroutine_threadsafe(self._play_next(), self.bot.loop)
                except Exception as e:
                    logger.error(f"Failed to schedule next track: {e}")

            vc.play(player, after=_after)
        except Exception as e:
            logger.error(f"Error playing source: {e}")
            self.current = None
            try:
                asyncio.create_task(self._play_next())
            except Exception:
                pass


async def voice_autocomplete(interaction: discord.Interaction, current: str):
    """Bug fix: this existed in the old voice_commands.py but was never
    actually attached to the `tts` command's `voice` parameter."""
    return [
        discord.app_commands.Choice(name=v, value=v)
        for v in AVAILABLE_VOICES
        if current.lower() in v.lower()
    ][:25]


async def language_autocomplete(interaction: discord.Interaction, current: str):
    return [
        discord.app_commands.Choice(name=lang, value=lang)
        for lang in TTS_LANGUAGES
        if current.lower() in lang.lower()
    ][:25]
