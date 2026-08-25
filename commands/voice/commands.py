"""Voice channel controls and TTS. `voice` and `language` on `/voice tts` now
use live autocomplete (voice_autocomplete existed before but was never wired
to the command -- a real bug); `engine` is now a proper Choice instead of a
free-text guess. Autocomplete can't run inside a Modal, so `tts` stays a
slash command rather than moving to one -- the autocomplete fix gives better
discoverability than a Modal would here anyway."""
import asyncio
import os
import tempfile
import traceback

import boto3
import discord
from discord import app_commands, FFmpegPCMAudio

from database import db
from utils.logger import logger
from utils.interaction_helpers import has_permission_or_owner
from utils.tts_helper import synthesize_tts_to_file
import utils.tts_helper as tts_helper
from commands.voice.helpers import (
    PLAYERS, GuildPlayer, AVAILABLE_VOICES, TTS_ENGINES, TTS_LANGUAGES,
    voice_autocomplete, language_autocomplete,
)


class VoiceGroup(app_commands.Group):
    """Voice controls: join/leave and simple playback + TTS."""

    def __init__(self):
        super().__init__(name="voice", description="Voice channel controls")

    @app_commands.command(name="join", description="Make the bot join your current voice channel or a specified one")
    @app_commands.describe(channel="Optional: Voice channel to join")
    async def join(self, interaction: discord.Interaction, channel: discord.VoiceChannel = None):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        if channel is None:
            if not interaction.user or not getattr(interaction.user, 'voice', None) or not interaction.user.voice.channel:
                await interaction.response.send_message("❌ You must be in a voice channel or specify one to use this command.", ephemeral=True)
                return
            channel = interaction.user.voice.channel

        user_perms = channel.permissions_for(interaction.user)
        if not user_perms.connect:
            await interaction.response.send_message("❌ You don't have permission to connect to that voice channel.", ephemeral=True)
            return

        bot_member = interaction.guild.get_member(interaction.client.user.id)
        perms = channel.permissions_for(bot_member)
        if not perms.connect:
            await interaction.response.send_message("❌ I don't have permission to connect to that voice channel.", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            vc = interaction.guild.voice_client
            if vc and vc.is_connected():
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
            if any(token in err_str for token in ["PyNaCl", "pynacl", "PyNaCl library", "davey", "davey library"]):
                await interaction.followup.send(
                    "❌ Missing voice dependency (PyNaCl/Davey). Install dependencies with `pip install -r requirements.txt` and restart the bot.",
                    ephemeral=True,
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

        bot_channel = vc.channel
        if bot_channel:
            user_perms = bot_channel.permissions_for(interaction.user)
            if not user_perms.connect and not (getattr(interaction.user, 'voice', None) and getattr(interaction.user.voice, 'channel', None) and interaction.user.voice.channel.id == bot_channel.id):
                await interaction.response.send_message("❌ You don't have permission to manage the voice channel the bot is connected to.", ephemeral=True)
                return

        try:
            await interaction.response.defer(ephemeral=True)
            await vc.disconnect()
            await interaction.followup.send("✅ Disconnected from voice.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to disconnect: {e}", ephemeral=True)

    @app_commands.command(name="tts", description="Speak text via TTS into the voice channel")
    @app_commands.describe(
        text="Text to speak", voice="Voice to use (e.g., 'Joanna')", engine="Engine to use",
        language="Language code to use (e.g., 'en-US')", announce_author="Say who submitted the TTS before speaking the text",
        post_text="Also post the spoken text in this channel",
    )
    @app_commands.choices(engine=[app_commands.Choice(name=e, value=e) for e in TTS_ENGINES])
    @app_commands.autocomplete(voice=voice_autocomplete, language=language_autocomplete)
    async def tts(
        self, interaction: discord.Interaction, text: str, voice: str = None, engine: str = None,
        language: str = None, announce_author: bool = False, post_text: bool = True,
    ):
        logger.debug(f"text={text}, voice={voice}, engine={engine}, language={language}, announce_author={announce_author}, post_text={post_text}")

        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        if db.is_command_disabled(interaction.guild.id, 'tts') and not await has_permission_or_owner(interaction, administrator=True):
            await interaction.response.send_message("❌ TTS is disabled in this server.", ephemeral=True)
            return

        banned, ban_reason = db.is_user_banned_for_command(interaction.guild.id, interaction.user.id, 'tts')
        if banned:
            reason_note = f" Reason: {ban_reason}" if ban_reason else ""
            await interaction.response.send_message(f"❌ You are banned from using TTS in this server.{reason_note}", ephemeral=True)
            return

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

        await interaction.response.defer(ephemeral=True)
        try:
            fd, temp_audio_path = tempfile.mkstemp(suffix=".mp3", prefix="bradbot_tts_")
            os.close(fd)
            spoken_text = text
            if announce_author:
                spoken_text = f"{interaction.user.display_name} says: {text}"

            provider = (os.getenv('BRADBOT_TTS_PROVIDER') or 'polly').strip().lower() or 'polly'
            if provider != 'polly':
                provider = 'polly'

            engine_to_use = (engine or os.getenv('BRADBOT_TTS_ENGINE') or 'standard').strip().lower() or 'standard'
            voice_to_use = voice or os.getenv('BRADBOT_TTS_VOICE')
            language_to_use = language or os.getenv('BRADBOT_TTS_LANGUAGE', 'en-US')

            try:
                synthesize_tts_to_file(text=spoken_text, out_path=temp_audio_path, voice=voice_to_use, engine=engine_to_use, language=language_to_use)
            except Exception as synth_err:
                try:
                    os.remove(temp_audio_path)
                except FileNotFoundError:
                    pass
                logger.error(f"Synthesis failed: {synth_err}")
                traceback.print_exc()
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

            await player.enqueue({'audio': audio_source, 'title': f"TTS from {interaction.user.display_name}", 'cleanup': _cleanup})

            sent_message_id = None
            if post_text:
                spoken_preview = spoken_text if announce_author else text
                sent_message = await interaction.channel.send(f"🗣️ {interaction.user.mention}: {spoken_preview}", silent=True)
                sent_message_id = sent_message.id
            await interaction.followup.send("✅ Added to the TTS queue.", ephemeral=True)

            try:
                db.log_tts_message(
                    interaction.guild.id, interaction.user.id, interaction.user.name, interaction.channel.id,
                    target_channel.id if target_channel else None, sent_message_id, text, voice_to_use,
                    engine_to_use, language_to_use, provider, announce_author, post_text,
                )
            except Exception as log_error:
                logger.error(f"Failed to log TTS message: {log_error}")
        except Exception as e:
            await interaction.followup.send(f"❌ TTS failed: {e}", ephemeral=True)

    @app_commands.command(name="debug_tts", description="(Admin) Synthesize a test TTS file and upload it for debugging")
    @app_commands.describe(text="Text to synthesize (optional)")
    async def debug_tts(self, interaction: discord.Interaction, text: str = "Debug TTS test"):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        if not await has_permission_or_owner(interaction, administrator=True):
            await interaction.response.send_message("❌ Only server administrators may run this debug command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.mp3', prefix='bradbot_debug_')
        os.close(tmp_fd)
        try:
            try:
                synthesize_tts_to_file(text, tmp_path)
            except Exception as e:
                await interaction.followup.send(f"❌ TTS synthesis failed: {e}", ephemeral=True)
                raise

            provider = os.getenv('BRADBOT_TTS_PROVIDER', 'polly')
            voice = os.getenv('BRADBOT_TTS_VOICE')
            module_file = getattr(tts_helper, '__file__', 'unknown')
            boto3_avail = getattr(tts_helper, '_boto3', None) is not None

            info_lines = [
                f"Provider: {provider}",
                f"Voice: {voice}",
                f"Helper module: {module_file}",
                f"boto3 available: {boto3_avail}",
            ]

            discord_file = discord.File(tmp_path, filename='bradbot_debug_tts.mp3')
            await interaction.followup.send(content="\n".join(info_lines), file=discord_file, ephemeral=False)
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    @app_commands.command(name="show_tts_options", description="Show all available options for TTS parameters")
    async def show_tts_options(self, interaction: discord.Interaction):
        options_message = (
            "**TTS Parameter Options:**\n\n"
            f"**Engines:** {', '.join(TTS_ENGINES)}\n"
            f"**Languages:** {', '.join(TTS_LANGUAGES)}\n"
            f"**Voices:** {', '.join(AVAILABLE_VOICES)}"
        )
        await interaction.response.send_message(options_message, ephemeral=True)

    @app_commands.command(name="filter_voices", description="Filter available voices by language, engine, or gender")
    @app_commands.describe(language="Optional: Language code to filter by (e.g., 'en-GB')", engine="Optional: Engine to filter by (e.g., 'neural')", gender="Optional: Voice gender to filter by (male/female)")
    @app_commands.choices(gender=[
        app_commands.Choice(name="Male", value="Male"),
        app_commands.Choice(name="Female", value="Female"),
    ])
    async def filter_voices(self, interaction: discord.Interaction, language: str = None, engine: str = None, gender: app_commands.Choice[str] = None):
        try:
            polly_client = boto3.client('polly', region_name='us-east-1')

            params = {}
            if engine:
                params['Engine'] = engine
            response = polly_client.describe_voices(**params)
            voices = response.get('Voices', [])

            if language:
                voices = [voice for voice in voices if voice['LanguageCode'] == language]
            if gender:
                voices = [voice for voice in voices if voice.get('Gender') == gender.value]

            if not voices:
                await interaction.response.send_message("❌ No voices found for the given parameters.", ephemeral=True)
                return

            filtered_voices = [f"{voice['Name']} ({voice['Gender']}) - {voice['LanguageName']}" for voice in voices]
            await interaction.response.send_message("**Available Voices:**\n" + "\n".join(filtered_voices), ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to fetch voices: {e}", ephemeral=True)
