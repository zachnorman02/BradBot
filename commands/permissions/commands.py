"""Top-level /permissions command group. Composes channel/role/conditional/
automation/deny as subgroups and holds the `mute` command directly. This
replaces the old scattered permission commands from admin_commands.py
(channelrestriction, globalmute_role, autorole, conditionalrole, setrole,
temporole, schedule_role) and the entire mod_tools_commands.py."""
import discord
from discord import app_commands

from commands.common import GuildOnlyGroup
from commands.permissions.channel_commands import PermissionsChannelGroup
from commands.permissions.role_commands import PermissionsRoleGroup
from commands.permissions.conditional_commands import PermissionsConditionalGroup
from commands.permissions.automation_commands import PermissionsAutomationGroup
from commands.permissions.deny_commands import PermissionsDenyGroup
from database import db
from utils.logger import logger
from utils.interaction_helpers import send_error, error_response


class PermissionsGroup(GuildOnlyGroup):
    """Access-control commands: channels, roles, and conditional/automated grants."""

    def __init__(self):
        super().__init__(name="permissions", description="Channel access, role grants, and conditional roles")
        self.add_command(PermissionsChannelGroup())
        self.add_command(PermissionsRoleGroup())
        self.add_command(PermissionsConditionalGroup())
        self.add_command(PermissionsAutomationGroup())
        self.add_command(PermissionsDenyGroup())

    @app_commands.command(name="mute", description="Create or configure a role that mutes users in all channels")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        role="Existing role to use as the global mute role (optional)",
        name="Name for a new mute role (if role not provided)",
        apply_to_all_channels="Apply deny send/add_react/speak overwrites to all channels now",
        disable="Disable the global mute role and clear its configuration",
    )
    async def mute(
        self,
        interaction: discord.Interaction,
        role: discord.Role | None = None,
        name: str = "Muted",
        apply_to_all_channels: bool = True,
        disable: bool = False,
    ):
        """Create or reuse a mute role and apply deny overwrites to all channels."""
        await interaction.response.defer(ephemeral=True)
        try:
            guild = interaction.guild

            if disable:
                db.set_guild_setting(guild.id, "global_mute_role_id", "")
                await interaction.followup.send("🛑 Global mute role disabled; config cleared.", ephemeral=True)
                return

            mute_role = role
            if not mute_role:
                mute_role = await guild.create_role(name=name, reason="Create global mute role")

            db.set_guild_setting(guild.id, "global_mute_role_id", str(mute_role.id))

            updated_channels = 0
            skipped_tickets = 0
            errors = []

            if apply_to_all_channels:
                for channel in guild.channels:
                    try:
                        if isinstance(channel, discord.TextChannel) and channel.name.startswith("ticket-"):
                            skipped_tickets += 1
                            continue
                        await channel.set_permissions(
                            mute_role,
                            send_messages=False, add_reactions=False, speak=False,
                            send_messages_in_threads=False, create_public_threads=False, create_private_threads=False,
                            send_tts_messages=False, use_application_commands=False, stream=False,
                            embed_links=False, attach_files=False,
                            reason="Apply global mute role permissions",
                        )
                        updated_channels += 1
                    except Exception as e:
                        errors.append(f"{getattr(channel, 'name', str(channel.id))}: {str(e)[:80]}")

            summary = [
                f"✅ Global mute role ready: {mute_role.mention}",
                f"Applied overwrites to {updated_channels} channel(s)." if apply_to_all_channels else "Skipped channel overwrites.",
            ]
            if skipped_tickets:
                summary.append(f"Skipped {skipped_tickets} ticket channel(s).")
            if errors:
                summary.append(f"⚠️ Errors on {len(errors)} channel(s): " + "; ".join(errors[:3]))
            await interaction.followup.send("\n".join(summary), ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating/applying mute role: {e}")
            await error_response(interaction, e, context="permissions_mute")
