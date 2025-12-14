import asyncio
import os
import tempfile
import discord
from discord import app_commands
from discord import FFmpegPCMAudio


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

        # Require the user to be in voice or specify channel via /voice join first
        if not (getattr(interaction.user, 'voice', None) and getattr(interaction.user.voice, 'channel', None)) and not interaction.guild.voice_client:
            await interaction.response.send_message("❌ You must be in a voice channel or the bot must already be connected.", ephemeral=True)
            return

        # Ensure bot is connected to the user's channel if not already
        target_channel = None
        if interaction.guild.voice_client and interaction.guild.voice_client.is_connected():
            target_channel = interaction.guild.voice_client.channel
        else:
            if getattr(interaction.user, 'voice', None) and getattr(interaction.user.voice, 'channel', None):
                target_channel = interaction.user.voice.channel

        # Permissions check for user
        if target_channel and not target_channel.permissions_for(interaction.user).connect:
            await interaction.response.send_message("❌ You don't have permission to use voice in the target channel.", ephemeral=True)
            return

        # No permission gating: any user who can invoke the command may enqueue

        await interaction.response.defer(ephemeral=True)

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
                try:
                    from yt_dlp import YoutubeDL
                except Exception:
                    await interaction.followup.send("❌ `yt-dlp` is required to play YouTube links. Add it to requirements and install.", ephemeral=True)
                    return

                ydl_opts = {'format': 'bestaudio', 'noplaylist': True, 'quiet': True}
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
    @app_commands.command(name="tts", description="Speak text via TTS into the voice channel")
    @app_commands.describe(text="Text to speak")
    async def tts(self, interaction: discord.Interaction, text: str):
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

        # No permission gating on TTS

        # Generate TTS audio file
        try:
            try:
                from gtts import gTTS
            except Exception:
                await interaction.response.send_message("❌ `gTTS` is required for TTS. Add it to requirements and install.", ephemeral=True)
                return

            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.mp3')
            os.close(tmp_fd)
            t = gTTS(text=text, lang='en')
            t.save(tmp_path)

            audio = FFmpegPCMAudio(tmp_path)

            # Play immediately (do not enqueue)
            def _after_play(err):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

            vc.play(audio, after=_after_play)
            await interaction.response.send_message("🔊 Speaking now.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ TTS failed: {e}", ephemeral=True)

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
