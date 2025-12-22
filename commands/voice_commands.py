import asyncio
import os
import tempfile
import discord
from discord import app_commands, FFmpegPCMAudio
from yt_dlp import YoutubeDL
from utils.cookie_helper import fetch_youtube_cookies
from utils.tts_helper import synthesize_tts_to_file
import utils.tts_helper as tts_helper
from database import db
import boto3


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
            cleanup = source.get('cleanup')

            def _after(err):
                if cleanup:
                    try:
                        cleanup()
                    except Exception as cleanup_error:
                        print(f"[VOICE] Cleanup error: {cleanup_error}")
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

        await interaction.response.defer()

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

    # -------------------- TTS --------------------
    # Define a list of available voices
    AVAILABLE_VOICES = [
        "Aditi", "Amy", "Astrid", "Bianca", "Brian", "Camila", "Carla", "Carmen", "Celine", "Chantal", "Conchita", "Cristiano", "Dora", "Emma", "Enrique", "Ewa", "Filiz", "Gabrielle", "Geraint", "Giorgio", "Gwyneth", "Hans", "Ines", "Ivy", "Jacek", "Jan", "Joanna", "Joey", "Justin", "Karl", "Kendra", "Kevin", "Kimberly", "Lea", "Liv", "Lotte", "Lucia", "Lupe", "Mads", "Maja", "Marlene", "Mathieu", "Matthew", "Maxim", "Mia", "Miguel", "Mizuki", "Naja", "Nicole", "Olivia", "Penelope", "Raveena", "Ricardo", "Ruben", "Russell", "Salli", "Seoyeon", "Takumi", "Tatyana", "Vicki", "Vitoria", "Zeina", "Zhiyu", "Aria", "Ayanda", "Arlet", "Hannah", "Arthur", "Daniel", "Liam", "Pedro", "Kajal", "Hiujin", "Laura", "Elin", "Ida", "Suvi", "Ola", "Hala", "Andres", "Sergio", "Remi", "Adriano", "Thiago", "Ruth", "Stephen", "Kazuha", "Tomoko", "Niamh", "Sofie", "Lisa", "Isabelle", "Zayd", "Danielle", "Gregory", "Burcu", "Jitka", "Sabrina", "Jasmine", "Jihye"
    ]

    # Autocomplete handler for voice parameter
    async def voice_autocomplete(interaction: discord.Interaction, current: str, parameter=None):
        # Filter voices based on user input
        return [
            app_commands.Choice(name=voice, value=voice)
            for voice in VoiceGroup.AVAILABLE_VOICES  # Reference the class attribute
            if current.lower() in voice.lower()
        ][:25]  # Limit to 25 results

    # Ensure the voice parameter is properly defined with autocomplete
    @app_commands.command(name="tts", description="Speak text via TTS into the voice channel")
    @app_commands.describe(
        text="Text to speak",
        voice="Voice to use (e.g., 'Joanna')",
        engine="Engine to use (e.g., 'Neural')",
        language="Language code to use (e.g., 'en-US')",
        announce_author="Say who submitted the TTS before speaking the text",
        post_text="Also post the spoken text in this channel"
    )
    async def tts(
        self,
        interaction: discord.Interaction,
        text: str,
        voice: str = None,
        engine: str = None,
        language: str = None,
        announce_author: bool = False,
        post_text: bool = True
    ):
        print(f"DEBUG: text={text}, voice={voice}, engine={engine}, language={language}, announce_author={announce_author}, post_text={post_text}")

        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        if db.is_command_disabled(interaction.guild.id, 'tts') and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ TTS is disabled in this server.", ephemeral=True)
            return

        banned, ban_reason = db.is_user_banned_for_command(interaction.guild.id, interaction.user.id, 'tts')
        if banned:
            reason_note = f" Reason: {ban_reason}" if ban_reason else ""
            await interaction.response.send_message(f"❌ You are banned from using TTS in this server.{reason_note}", ephemeral=True)
            return

        # Ensure bot is connected or user's in voice
        vc = interaction.guild.voice_client
        target_channel = None
        if vc and vc.is_connected():
            target_channel = vc.channel
        else:
            if getattr(interaction.user, 'voice', None) and getattr(interaction.user.voice, 'channel', None):
                target_channel = interaction.user.voice.channel
            else:
                await interaction.response.send_message("❌ You must be in a voice channel or the bot must be connected.", ephemeral=True)
                return
            try:
                await target_channel.connect()
                vc = interaction.guild.voice_client
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to connect: {e}", ephemeral=True)
                return

        # Process TTS request
        await interaction.response.defer(ephemeral=True)
        try:
            fd, temp_audio_path = tempfile.mkstemp(suffix=".mp3", prefix="bradbot_tts_")
            os.close(fd)
            spoken_text = text
            if announce_author:
                spoken_text = f"{interaction.user.display_name} says: {text}"

            provider = (os.getenv('BRADBOT_TTS_PROVIDER') or 'gtts').strip().lower() or 'gtts'
            engine_to_use_raw = engine or os.getenv('BRADBOT_TTS_ENGINE') or 'standard'
            engine_to_use = engine_to_use_raw.strip().lower() or 'standard'
            if provider == 'polly':
                voice_to_use = voice or os.getenv('BRADBOT_TTS_VOICE', 'Matthew')
                language_to_use = language or os.getenv('BRADBOT_TTS_LANGUAGE', 'en-US')
                engine_for_log = engine_to_use
            else:
                voice_to_use = voice  # gTTS does not use a named voice
                language_to_use = language or 'en'
                engine_for_log = None

            try:
                synthesize_tts_to_file(
                    text=spoken_text,
                    out_path=temp_audio_path,
                    voice=voice_to_use,
                    engine=engine_to_use,
                    language=language_to_use
                )
            except Exception:
                try:
                    os.remove(temp_audio_path)
                except FileNotFoundError:
                    pass
                raise

            try:
                audio_source = FFmpegPCMAudio(temp_audio_path)
            except Exception:
                try:
                    os.remove(temp_audio_path)
                except FileNotFoundError:
                    pass
                raise

            def _cleanup():
                try:
                    audio_source.cleanup()
                except Exception:
                    pass
                try:
                    os.remove(temp_audio_path)
                except FileNotFoundError:
                    pass

            guild_id = interaction.guild.id
            player = PLAYERS.get(guild_id)
            if not player:
                player = GuildPlayer(guild_id, interaction.client)
                PLAYERS[guild_id] = player

            await player.enqueue({
                'audio': audio_source,
                'title': f"TTS from {interaction.user.display_name}",
                'cleanup': _cleanup
            })
            provider_for_log = provider or 'gtts'

            sent_message_id = None
            if post_text:
                spoken_preview = spoken_text if announce_author else text
                sent_message = await interaction.channel.send(
                    f"🗣️ {interaction.user.mention}: {spoken_preview}",
                    silent=True
                )
                sent_message_id = sent_message.id
                await interaction.followup.send("✅ Added to the TTS queue.", ephemeral=True)
            else:
                await interaction.followup.send("✅ Added to the TTS queue.", ephemeral=True)

            try:
                db.log_tts_message(
                    interaction.guild.id,
                    interaction.user.id,
                    interaction.user.name,
                    interaction.channel.id,
                    target_channel.id if target_channel else None,
                    sent_message_id,
                    text,
                    voice_to_use,
                    engine_for_log,
                    language_to_use,
                    provider_for_log,
                    announce_author,
                    post_text
                )
            except Exception as log_error:
                print(f"Failed to log TTS message: {log_error}")
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

    # Add a new command to display all parameter options
    @app_commands.command(name="show_tts_options", description="Show all available options for TTS parameters")
    async def show_tts_options(self, interaction: discord.Interaction):
        engine_options = ["standard", "neural", "long-form", "generative"]
        language_options = [
            "arb", "cmn-CN", "cy-GB", "da-DK", "de-DE", "en-AU", "en-GB", "en-GB-WLS", "en-IN", "en-US", "es-ES", "es-MX", "es-US", "fr-CA", "fr-FR", "is-IS", "it-IT", "ja-JP", "hi-IN", "ko-KR", "nb-NO", "nl-NL", "pl-PL", "pt-BR", "pt-PT", "ro-RO", "ru-RU", "sv-SE", "tr-TR", "en-NZ", "en-ZA", "ca-ES", "de-AT", "yue-CN", "ar-AE", "fi-FI", "en-IE", "nl-BE", "fr-BE", "cs-CZ", "de-CH", "en-SG"
        ]
        voice_options = VoiceGroup.AVAILABLE_VOICES

        options_message = (
            "**TTS Parameter Options:**\n\n"
            f"**Engines:** {', '.join(engine_options)}\n"
            f"**Languages:** {', '.join(language_options)}\n"
            f"**Voices:** {', '.join(voice_options)}"
        )

        await interaction.response.send_message(options_message, ephemeral=True)

    # Add a command to filter voices based on language and engine
    @app_commands.command(name="filter_voices", description="Filter available voices by language, engine, or gender")
    @app_commands.describe(
        language="Optional: Language code to filter by (e.g., 'en-GB')",
        engine="Optional: Engine to filter by (e.g., 'neural')",
        gender="Optional: Voice gender to filter by (male/female)"
    )
    @app_commands.choices(gender=[
        app_commands.Choice(name="Male", value="Male"),
        app_commands.Choice(name="Female", value="Female"),
    ])
    async def filter_voices(self, interaction: discord.Interaction, language: str = None, engine: str = None, gender: app_commands.Choice[str] = None):
        try:
            # Initialize the Polly client with a default region
            polly_client = boto3.client('polly', region_name='us-east-1')

            # Fetch voices from AWS Polly
            params = {}
            if engine:
                params['Engine'] = engine
            response = polly_client.describe_voices(**params)
            voices = response.get('Voices', [])

            # Filter voices by language if provided
            if language:
                voices = [voice for voice in voices if voice['LanguageCode'] == language]

            if gender:
                voices = [voice for voice in voices if voice.get('Gender') == gender.value]

            if not voices:
                await interaction.response.send_message(
                    f"❌ No voices found for the given parameters.",
                    ephemeral=True
                )
                return

            # Format and send the response
            filtered_voices = [
                f"{voice['Name']} ({voice['Gender']}) - {voice['LanguageName']}"
                for voice in voices
            ]
            voices_message = (
                f"**Available Voices:**\n"
                + "\n".join(filtered_voices)
            )
            await interaction.response.send_message(voices_message, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to fetch voices: {e}", ephemeral=True
            )
