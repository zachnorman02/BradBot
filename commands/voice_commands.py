import asyncio
import os
import tempfile
import discord
from discord import app_commands, FFmpegPCMAudio
from yt_dlp import YoutubeDL
from utils.cookie_helper import fetch_youtube_cookies
from utils.tts_helper import synthesize_tts_to_file
import utils.tts_helper as tts_helper


# Simple per-guild audio player
PLAYERS: dict[int, 'GuildPlayer'] = {}


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
        # record pending for inspection and then put into the async queue
        try:
            self._pending.append(source)
        except Exception:
            pass

        await self.queue.put(source)
        if not self.playing:
            # schedule playback without blocking the enqueuer
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

        # pop pending if recorded
        if self._pending:
            try:
                self._pending.pop(0)
            except Exception:
                pass

        # store as current for nowplaying
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
            # try to wait a short while for a reconnect
            attempts = 0
            while attempts < 5:
                await asyncio.sleep(1)
                vc = guild.voice_client
                if vc and vc.is_connected():
                    break
                attempts += 1

            if not vc or not vc.is_connected():
                # cannot play now; mark as not playing but keep queue
                self.playing = False
                self.current = None
                return

        try:
            audio = source.get('audio')
            volume = source.get('volume', 0.5)
            player = discord.PCMVolumeTransformer(audio, volume=volume)

            def _after(err):
                if err:
                    print(f"[VOICE] Playback error: {err}")
                # schedule next
                try:
                    asyncio.run_coroutine_threadsafe(self._play_next(), self.bot.loop)
                except Exception as e:
                    print(f"[VOICE] Failed to schedule next track: {e}")

            vc.play(player, after=_after)
        except Exception as e:
            print(f"[VOICE] Error playing source: {e}")
            # clear current and try next
            self.current = None
            try:
                asyncio.create_task(self._play_next())
            except Exception:
                pass


class VoiceGroup(app_commands.Group):
    """Voice controls: join/leave and simple playback + TTS."""

    def __init__(self):
        super().__init__(name="voice", description="Voice channel controls")
    pass

    # -------------------- Join / Leave --------------------
    @app_commands.command(name="join", description="Make the bot join your current voice channel or a specified one")
    @app_commands.describe(channel="Optional: Voice channel to join")
    async def join(self, interaction: discord.Interaction, channel: discord.VoiceChannel = None):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        # Determine target channel: explicit argument takes precedence, otherwise the user's current voice channel
        if channel is None:
            if not interaction.user or not getattr(interaction.user, 'voice', None) or not interaction.user.voice.channel:
                await interaction.response.send_message("❌ You must be in a voice channel or specify one to use this command.", ephemeral=True)
                return
            channel = interaction.user.voice.channel

        # Verify the invoking user can access/connect to the channel
        user_perms = channel.permissions_for(interaction.user)
        if not user_perms.connect:
            await interaction.response.send_message("❌ You don't have permission to connect to that voice channel.", ephemeral=True)
            return

        # Check bot permissions
        bot_member = interaction.guild.get_member(interaction.client.user.id)
        perms = channel.permissions_for(bot_member)
        if not perms.connect:
            await interaction.response.send_message("❌ I don't have permission to connect to that voice channel.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            vc = interaction.guild.voice_client
            if vc and vc.is_connected():
                # If already connected to a different channel, move
                if vc.channel.id != channel.id:
                    await vc.move_to(channel)
                    await interaction.followup.send(f"✅ Moved to {channel.mention}", ephemeral=True)
                else:
                    await interaction.followup.send(f"✅ I'm already connected to {channel.mention}", ephemeral=True)
                return

            await channel.connect()
            await interaction.followup.send(f"✅ Joined {channel.mention}", ephemeral=True)
        except Exception as e:
            err_str = str(e)
            # Common error when PyNaCl is missing
            if "PyNaCl" in err_str or "pynacl" in err_str or "PyNaCl library" in err_str:
                await interaction.followup.send(
                    "❌ PyNaCl is required for voice functionality. Install it with `pip install pynacl` and restart the bot.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(f"❌ Failed to join voice channel: {e}", ephemeral=True)

    @app_commands.command(name="leave", description="Make the bot leave the current voice channel")
    async def leave(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            await interaction.response.send_message("ℹ️ I'm not connected to a voice channel.", ephemeral=True)
            return

        # Ensure the invoking user has access to the channel the bot is in
        bot_channel = vc.channel
        if bot_channel:
            user_perms = bot_channel.permissions_for(interaction.user)
            # Allow if user can connect (they're allowed to access the channel) OR user is in the same voice channel
            if not user_perms.connect and not (getattr(interaction.user, 'voice', None) and getattr(interaction.user.voice, 'channel', None) and interaction.user.voice.channel.id == bot_channel.id):
                await interaction.response.send_message("❌ You don't have permission to manage the voice channel the bot is connected to.", ephemeral=True)
                return

        try:
            await interaction.response.defer(ephemeral=True)
            await vc.disconnect()
            await interaction.followup.send("✅ Disconnected from voice.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to disconnect: {e}", ephemeral=True)

    # -------------------- Playback --------------------
    @app_commands.command(name="play", description="Play audio from a URL (YouTube or direct audio).")
    @app_commands.describe(source="URL to play (YouTube link or direct audio URL)")
    async def play(self, interaction: discord.Interaction, source: str):
        """Enqueue and play an audio source. Uses yt-dlp for YouTube URLs if available."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Require the user to be in voice or specify channel via /voice join first
        if not (getattr(interaction.user, 'voice', None) and getattr(interaction.user.voice, 'channel', None)) and not interaction.guild.voice_client:
            await interaction.followup.send("❌ You must be in a voice channel or the bot must already be connected.", ephemeral=True)
            return

        # Ensure bot is connected to the user's channel if not already
        target_channel = None
        if interaction.guild.voice_client and interaction.guild.voice_client.is_connected():
            target_channel = interaction.guild.voice_client.channel
        else:
            if getattr(interaction.user, 'voice', None) and getattr(interaction.user.voice, 'channel', None):
                target_channel = interaction.user.voice.channel

        # No permission gating: any user who can invoke the command may enqueue

        # Ensure connected
        try:
            if not interaction.guild.voice_client or not interaction.guild.voice_client.is_connected():
                await target_channel.connect()
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to connect: {e}", ephemeral=True)
            return

        # Extract direct audio URL if yt-dlp available and URL looks like YouTube
        direct_url = source
        info_title = None
        try:
            if 'youtube.com' in source or 'youtu.be' in source:
                # Try to get cookies for age-restricted content
                cookie_file = await fetch_youtube_cookies()

                ydl_opts = {
                    'format': 'bestaudio',
                    'noplaylist': True,
                    'quiet': False
                }

                if cookie_file:
                    ydl_opts['cookiefile'] = cookie_file

                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(source, download=False)
                    direct_url = info.get('url')
                    info_title = info.get('title')

        except Exception as e:
            print(f"[VOICE] yt-dlp extract error: {e}")

        # Prepare ffmpeg audio source
        ff_opts = "-vn -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        try:
            audio = FFmpegPCMAudio(direct_url, options=ff_opts)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to prepare audio source: {e}", ephemeral=True)
            return

        guild_id = interaction.guild.id
        player = PLAYERS.get(guild_id)
        if not player:
            player = GuildPlayer(guild_id, interaction.client)
            PLAYERS[guild_id] = player

        await player.enqueue({'audio': audio, 'title': info_title or source})

        await interaction.followup.send(f"✅ Queued: {info_title or source}", ephemeral=True)

    @app_commands.command(name="skip", description="Skip the current track")
    async def skip(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            await interaction.response.send_message("ℹ️ I'm not connected to voice.", ephemeral=True)
            return

        # No permission gating on skip

        vc.stop()
        await interaction.response.send_message("⏭️ Skipped.", ephemeral=True)

    @app_commands.command(name="stop", description="Stop playback and clear the queue")
    async def stop(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            await interaction.response.send_message("ℹ️ I'm not connected to voice.", ephemeral=True)
            return

        # No permission gating on stop

        # Clear queue
        player = PLAYERS.get(interaction.guild.id)
        if player:
            while not player.queue.empty():
                try:
                    player.queue.get_nowait()
                except Exception:
                    break

        vc.stop()
        await interaction.response.send_message("⏹️ Stopped and cleared queue.", ephemeral=True)

    # -------------------- TTS --------------------
    # Define a list of available voices
    AVAILABLE_VOICES = [
        "Aditi", "Amy", "Astrid", "Bianca", "Brian", "Camila", "Carla", "Carmen", "Celine", "Chantal", "Conchita", "Cristiano", "Dora", "Emma", "Enrique", "Ewa", "Filiz", "Gabrielle", "Geraint", "Giorgio", "Gwyneth", "Hans", "Ines", "Ivy", "Jacek", "Jan", "Joanna", "Joey", "Justin", "Karl", "Kendra", "Kevin", "Kimberly", "Lea", "Liv", "Lotte", "Lucia", "Lupe", "Mads", "Maja", "Marlene", "Mathieu", "Matthew", "Maxim", "Mia", "Miguel", "Mizuki", "Naja", "Nicole", "Olivia", "Penelope", "Raveena", "Ricardo", "Ruben", "Russell", "Salli", "Seoyeon", "Takumi", "Tatyana", "Vicki", "Vitoria", "Zeina", "Zhiyu", "Aria", "Ayanda", "Arlet", "Hannah", "Arthur", "Daniel", "Liam", "Pedro", "Kajal", "Hiujin", "Laura", "Elin", "Ida", "Suvi", "Ola", "Hala", "Andres", "Sergio", "Remi", "Adriano", "Thiago", "Ruth", "Stephen", "Kazuha", "Tomoko", "Niamh", "Sofie", "Lisa", "Isabelle", "Zayd", "Danielle", "Gregory", "Burcu", "Jitka", "Sabrina", "Jasmine", "Jihye"
    ]

    # Autocomplete handler for voice parameter
    async def voice_autocomplete(interaction: discord.Interaction, current: str):
        # Filter voices based on user input
        return [
            app_commands.Choice(name=voice, value=voice)
            for voice in VoiceGroup.AVAILABLE_VOICES  # Reference the class attribute
            if current.lower() in voice.lower()
        ][:25]  # Limit to 25 results

    @app_commands.command(name="tts", description="Speak text via TTS into the voice channel")
    @app_commands.describe(
        text="Text to speak",
        voice="Voice to use (optional, e.g., 'Joanna')",
        engine="Engine to use (optional, e.g., 'Neural')",
        language="Language code to use (optional, e.g., 'en-US')"
    )
    @app_commands.autocomplete(voice=voice_autocomplete)
    @app_commands.choices(
        engine=[
            app_commands.Choice(name=engine, value=engine) for engine in ["standard", "neural", "long-form", "generative"]
        ],
        language=[
            app_commands.Choice(name=lang, value=lang) for lang in [
                "arb", "cmn-CN", "cy-GB", "da-DK", "de-DE", "en-AU", "en-GB", "en-GB-WLS", "en-IN", "en-US", "es-ES", "es-MX", "es-US", "fr-CA", "fr-FR", "is-IS", "it-IT", "ja-JP", "hi-IN", "ko-KR", "nb-NO", "nl-NL", "pl-PL", "pt-BR", "pt-PT", "ro-RO", "ru-RU", "sv-SE", "tr-TR", "en-NZ", "en-ZA", "ca-ES", "de-AT", "yue-CN", "ar-AE", "fi-FI", "en-IE", "nl-BE", "fr-BE", "cs-CZ", "de-CH", "en-SG"
            ]
        ]
    )
    async def tts(self, interaction: discord.Interaction, text: str, voice: str = None, engine: app_commands.Choice[str] = None, language: app_commands.Choice[str] = None):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        # Ensure bot is connected or user's in voice
        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            if not (getattr(interaction.user, 'voice', None) and getattr(interaction.user.voice, 'channel', None)):
                await interaction.response.send_message("❌ You must be in a voice channel or the bot must be connected.", ephemeral=True)
                return
            try:
                await interaction.user.voice.channel.connect()
                vc = interaction.guild.voice_client
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to connect: {e}", ephemeral=True)
                return

        # Process TTS request
        await interaction.response.defer(ephemeral=True)
        try:
            # Call TTS helper function (assume it handles voice, engine, and language)
            audio_source = await tts_helper.generate_tts_audio(text, voice, engine.value if engine else None, language.value if language else None)
            vc.play(audio_source)
            await interaction.followup.send(f"✅ Speaking: {text}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ TTS failed: {e}", ephemeral=True)

    @app_commands.command(name="debug_tts", description="(Admin) Synthesize a test TTS file and upload it for debugging")
    @app_commands.describe(text="Text to synthesize (optional)")
    async def debug_tts(self, interaction: discord.Interaction, text: str = "Debug TTS test"):
        # Admin-only debug utility to synthesize TTS using the configured provider and upload the result.
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        # Restrict to administrators to avoid abuse
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only server administrators may run this debug command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Prepare temp file
        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.mp3', prefix='bradbot_debug_')
        os.close(tmp_fd)
        try:
            # Synthesize
            try:
                synthesize_tts_to_file(text, tmp_path)
            except Exception as e:
                await interaction.followup.send(f"❌ TTS synthesis failed: {e}", ephemeral=True)
                raise

            # Build info about provider and module
            provider = os.getenv('BRADBOT_TTS_PROVIDER', 'gtts')
            voice = os.getenv('BRADBOT_TTS_VOICE', 'Matthew')
            module_file = getattr(tts_helper, '__file__', 'unknown')
            boto3_avail = getattr(tts_helper, '_boto3', None) is not None
            gtts_avail = getattr(tts_helper, '_gTTS', None) is not None

            info_lines = [
                f"Provider: {provider}",
                f"Voice: {voice}",
                f"Helper module: {module_file}",
                f"boto3 available: {boto3_avail}",
                f"gTTS available: {gtts_avail}",
            ]

            # Send file back to the channel (not ephemeral) so admins can listen
            discord_file = discord.File(tmp_path, filename='bradbot_debug_tts.mp3')
            await interaction.followup.send(content="\n".join(info_lines), file=discord_file, ephemeral=False)

        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    @app_commands.command(name="queue", description="Show the upcoming queue")
    async def queue(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        player = PLAYERS.get(interaction.guild.id)
        if not player or (not player._pending and not player.current):
            await interaction.response.send_message("Queue is empty.", ephemeral=True)
            return

        lines = []
        if player.current:
            lines.append(f"Now playing: {player.current.get('title', 'Unknown')}")

        if player._pending:
            lines.append("Upcoming:")
            for i, item in enumerate(player._pending[:25], start=1):
                lines.append(f"{i}. {item.get('title', 'Unknown')}")

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="nowplaying", description="Show the currently playing track")
    async def nowplaying(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        player = PLAYERS.get(interaction.guild.id)
        if not player or not player.current:
            await interaction.response.send_message("Nothing is playing right now.", ephemeral=True)
            return

        await interaction.response.send_message(f"Now playing: {player.current.get('title', 'Unknown')}")
