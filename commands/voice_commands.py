import discord
from discord import app_commands


class VoiceGroup(app_commands.Group):
    """Simple voice controls: join and leave voice channels."""

    def __init__(self):
        super().__init__(name="voice", description="Voice channel controls")

    @app_commands.command(name="join", description="Make the bot join your current voice channel")
    async def join(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        if not interaction.user or not getattr(interaction.user, 'voice', None) or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ You must be in a voice channel to use this command.", ephemeral=True)
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
