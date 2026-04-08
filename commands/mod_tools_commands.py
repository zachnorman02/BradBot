"""Moderation-focused admin tooling command group."""

import discord
from discord import app_commands

from database import db
from utils.logger import logger


class ModToolsGroup(app_commands.Group):
    """Moderation tools split from /admin to stay under Discord payload limits."""

    def __init__(self):
        super().__init__(name="modtools", description="Moderation tooling for role/channel restrictions")

    @app_commands.command(name="channeldeny_user", description="Deny a specific user from a specific channel")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="Channel to deny access to",
        user="User to deny",
        deny_view="Also deny viewing the channel (recommended)",
    )
    async def channeldeny_user(
        self,
        interaction: discord.Interaction,
        channel: discord.abc.GuildChannel,
        user: discord.Member,
        deny_view: bool = True,
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            me = interaction.guild.me
            if not me or not channel.permissions_for(me).manage_channels:
                await interaction.followup.send(
                    "❌ I need `Manage Channels` permission in that channel to edit overwrites.",
                    ephemeral=True,
                )
                return

            overwrite = channel.overwrites_for(user)
            if deny_view:
                overwrite.view_channel = False
            overwrite.send_messages = False
            overwrite.send_messages_in_threads = False
            overwrite.add_reactions = False
            overwrite.speak = False
            overwrite.connect = False
            overwrite.stream = False
            overwrite.use_application_commands = False
            overwrite.create_public_threads = False
            overwrite.create_private_threads = False

            await channel.set_permissions(
                user,
                overwrite=overwrite,
                reason=f"Channel deny set by {interaction.user}",
            )

            await interaction.followup.send(
                (
                    f"✅ Deny overwrite applied for {user.mention} in {channel.mention}.\n"
                    f"• View denied: {'Yes' if deny_view else 'No'}\n"
                    "• Send/reactions/voice/connect/app commands denied"
                ),
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Error in modtools channeldeny_user command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="channelallow_user", description="Remove channel-specific deny restrictions for a user")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="Channel to clear restrictions in",
        user="User to allow",
    )
    async def channelallow_user(
        self,
        interaction: discord.Interaction,
        channel: discord.abc.GuildChannel,
        user: discord.Member,
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            me = interaction.guild.me
            if not me or not channel.permissions_for(me).manage_channels:
                await interaction.followup.send(
                    "❌ I need `Manage Channels` permission in that channel to edit overwrites.",
                    ephemeral=True,
                )
                return

            overwrite = channel.overwrites_for(user)
            overwrite.view_channel = None
            overwrite.send_messages = None
            overwrite.send_messages_in_threads = None
            overwrite.add_reactions = None
            overwrite.speak = None
            overwrite.connect = None
            overwrite.stream = None
            overwrite.use_application_commands = None
            overwrite.create_public_threads = None
            overwrite.create_private_threads = None

            if overwrite.is_empty():
                await channel.set_permissions(
                    user,
                    overwrite=None,
                    reason=f"Channel deny cleared by {interaction.user}",
                )
            else:
                await channel.set_permissions(
                    user,
                    overwrite=overwrite,
                    reason=f"Channel deny cleared by {interaction.user}",
                )

            await interaction.followup.send(
                f"✅ Cleared deny overwrite fields for {user.mention} in {channel.mention}.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Error in modtools channelallow_user command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="roledeny_user", description="Manage per-user denies for a specific role")
    @app_commands.describe(
        action="What action to perform",
        user="User to target",
        role="Role to deny/allow/check/list",
        notes="Optional reason when adding a deny",
        channel="Channel for role-deny attempt logs (used with set-log-channel)",
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="add - Deny role for user", value="add"),
        app_commands.Choice(name="remove - Remove deny", value="remove"),
        app_commands.Choice(name="check - Check if denied", value="check"),
        app_commands.Choice(name="list - List deny entries", value="list"),
        app_commands.Choice(name="set-log-channel - Send deny attempts to a channel", value="set_log_channel"),
        app_commands.Choice(name="clear-log-channel - Disable channel logging", value="clear_log_channel"),
    ])
    @app_commands.checks.has_permissions(manage_roles=True)
    async def roledeny_user(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        user: discord.Member = None,
        role: discord.Role = None,
        notes: str = None,
        channel: discord.TextChannel = None,
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            if not db.connection_pool:
                db.init_pool()

            action_value = action.value

            if action_value in ("add", "remove", "check") and (not user or not role):
                await interaction.followup.send("❌ Please provide both `user` and `role` for this action.", ephemeral=True)
                return

            if action_value == "set_log_channel":
                if not channel:
                    await interaction.followup.send("❌ Please provide a channel for `set-log-channel`.", ephemeral=True)
                    return
                db.set_guild_setting(interaction.guild.id, "role_deny_log_channel_id", str(channel.id))
                await interaction.followup.send(
                    f"✅ Role deny attempt logs will be posted in {channel.mention}.",
                    ephemeral=True,
                )
                return

            if action_value == "clear_log_channel":
                db.set_guild_setting(interaction.guild.id, "role_deny_log_channel_id", "")
                await interaction.followup.send("✅ Role deny channel logging disabled.", ephemeral=True)
                return

            if action_value == "add":
                if db.is_role_denied(interaction.guild.id, user.id, role.id):
                    await interaction.followup.send(
                        f"ℹ️ {user.mention} is already denied from receiving {role.mention}.",
                        ephemeral=True,
                    )
                    return

                db.add_role_deny(interaction.guild.id, user.id, role.id, interaction.user.id, notes)

                response = f"✅ Added deny: {user.mention} cannot receive {role.mention}."
                if notes:
                    response += f"\n📝 Notes: {notes}"
                await interaction.followup.send(response, ephemeral=True)
                return

            if action_value == "remove":
                if not db.is_role_denied(interaction.guild.id, user.id, role.id):
                    await interaction.followup.send(
                        f"ℹ️ No deny entry exists for {user.mention} and {role.mention}.",
                        ephemeral=True,
                    )
                    return

                db.remove_role_deny(interaction.guild.id, user.id, role.id)
                await interaction.followup.send(
                    f"✅ Removed deny: {user.mention} can receive {role.mention} again.",
                    ephemeral=True,
                )
                return

            if action_value == "check":
                denied = db.is_role_denied(interaction.guild.id, user.id, role.id)
                await interaction.followup.send(
                    (
                        f"🚫 {user.mention} is denied from {role.mention}."
                        if denied
                        else f"✅ {user.mention} is not denied from {role.mention}."
                    ),
                    ephemeral=True,
                )
                return

            entries = db.get_role_denies(
                interaction.guild.id,
                user_id=user.id if user else None,
                role_id=role.id if role else None,
            )

            if not entries:
                await interaction.followup.send("📋 No role deny entries found for this filter.", ephemeral=True)
                return

            embed = discord.Embed(
                title="🚫 Role Deny Entries",
                description=f"Found {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}",
                color=discord.Color.orange(),
            )

            for entry in entries[:20]:
                member = interaction.guild.get_member(entry['user_id'])
                role_obj = interaction.guild.get_role(entry['role_id'])
                actor = interaction.guild.get_member(entry['created_by_user_id']) if entry['created_by_user_id'] else None

                user_text = member.mention if member else f"<@{entry['user_id']}>"
                role_text = role_obj.mention if role_obj else f"<@&{entry['role_id']}>"
                actor_text = actor.mention if actor else (f"<@{entry['created_by_user_id']}>" if entry['created_by_user_id'] else "Unknown")
                updated_at = entry['updated_at'].strftime('%Y-%m-%d %H:%M UTC') if entry.get('updated_at') else "Unknown"
                notes_text = entry['notes'][:120] if entry.get('notes') else "None"

                embed.add_field(
                    name=f"{user_text} -> {role_text}",
                    value=f"By: {actor_text}\nUpdated: {updated_at}\nNotes: {notes_text}",
                    inline=False,
                )

            if len(entries) > 20:
                embed.set_footer(text=f"Showing first 20 of {len(entries)} entries")

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in modtools roledeny_user command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)
