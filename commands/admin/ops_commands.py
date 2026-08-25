"""Bot/command operational tooling: sync, echo/TTS bans, SQL & audit-log
diagnostics (SQL and audit-log queries open a Modal instead of taking a
single-line string param -- see commands/admin/modals.py)."""
import discord
from discord import app_commands

from commands.common import GuildOnlyGroup
from commands.admin.modals import SqlQueryModal, AuditLogQueryModal
from database import db
from utils.logger import logger
from utils.interaction_helpers import send_error, send_success, require_bot_owner, has_permission_or_owner, error_response


class AdminOpsGroup(GuildOnlyGroup):
    """Bot/command operational tooling."""

    def __init__(self):
        super().__init__(name="ops", description="Sync, command bans, and diagnostics")

    @app_commands.command(name="sync", description="Force sync slash commands (bot owner or admin)")
    @app_commands.describe(scope="Sync globally or just this server")
    @app_commands.choices(scope=[
        app_commands.Choice(name="Global (all servers)", value="global"),
        app_commands.Choice(name="This server only", value="guild"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def sync_commands(self, interaction: discord.Interaction, scope: app_commands.Choice[str] = None):
        """Allow admins to trigger a slash-command sync without restarting."""
        await interaction.response.defer(ephemeral=True)
        tree = interaction.client.tree
        try:
            if scope and scope.value == "guild":
                synced = await tree.sync(guild=interaction.guild)
                await interaction.followup.send(f"✅ Synced {len(synced)} command(s) for **{interaction.guild.name}**.", ephemeral=True)
            else:
                synced = await tree.sync()
                await interaction.followup.send(f"✅ Globally synced {len(synced)} command(s).", ephemeral=True)
        except Exception as e:
            await error_response(interaction, e, context="sync_commands")

    @app_commands.command(name="command_ban", description="Ban a user from using a command (echo or tts)")
    @app_commands.describe(user="User to ban", command="Command to ban", reason="Optional reason for the ban")
    @app_commands.choices(command=[
        app_commands.Choice(name="Echo", value="echo"),
        app_commands.Choice(name="TTS", value="tts"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def command_ban(self, interaction: discord.Interaction, user: discord.Member, command: app_commands.Choice[str], reason: str = None):
        """Prevent a member from using echo or TTS commands in this server.
        To ban the author of a specific message, right-click it -> Apps -> Ban Author From Command."""
        from commands.admin.helpers import ban_user_for_command

        await ban_user_for_command(interaction, user, command.value, reason)

    @app_commands.command(name="command_unban", description="Remove a command ban for a user")
    @app_commands.describe(user="User to unban", command="Command to unban")
    @app_commands.choices(command=[
        app_commands.Choice(name="Echo", value="echo"),
        app_commands.Choice(name="TTS", value="tts"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def command_unban(self, interaction: discord.Interaction, user: discord.Member, command: app_commands.Choice[str]):
        """Remove a member's echo or TTS ban in this server."""
        db.unban_user_for_command(interaction.guild.id, user.id, command.value)
        await send_success(interaction, f"Unbanned {user.display_name} for {command.value} in this server.")

    @app_commands.command(name="command_disable", description="Disable a command in this server")
    @app_commands.describe(command="Command to disable")
    @app_commands.choices(command=[
        app_commands.Choice(name="Echo", value="echo"),
        app_commands.Choice(name="TTS", value="tts"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def command_disable(self, interaction: discord.Interaction, command: app_commands.Choice[str]):
        """Disable echo or TTS for everyone in this server."""
        db.set_command_enabled(interaction.guild.id, command.value, False)
        await send_success(interaction, f"Disabled {command.value} in this server.")

    @app_commands.command(name="command_enable", description="Enable a command in this server")
    @app_commands.describe(command="Command to enable")
    @app_commands.choices(command=[
        app_commands.Choice(name="Echo", value="echo"),
        app_commands.Choice(name="TTS", value="tts"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def command_enable(self, interaction: discord.Interaction, command: app_commands.Choice[str]):
        """Enable echo or TTS for everyone in this server."""
        db.set_command_enabled(interaction.guild.id, command.value, True)
        await send_success(interaction, f"Enabled {command.value} in this server.")

    @app_commands.command(name="sql", description="Execute a SQL query (BOT OWNER ONLY)")
    async def execute_sql(self, interaction: discord.Interaction):
        """Open a Modal to execute a SQL query on the database (BOT OWNER ONLY)."""
        if not await require_bot_owner(interaction):
            return
        await interaction.response.send_modal(SqlQueryModal())

    @app_commands.command(name="auditlog", description="Query audit log with SQL-like syntax")
    @app_commands.default_permissions(view_audit_log=True)
    async def audit_log_query(self, interaction: discord.Interaction):
        """Open a Modal to query the audit log using SQL-like syntax."""
        if not await has_permission_or_owner(interaction, view_audit_log=True):
            await send_error(interaction, "You need the View Audit Log permission to use this command.")
            return
        await interaction.response.send_modal(AuditLogQueryModal())

    @app_commands.command(name="tasklogs", description="View recent automated task execution logs (BOT OWNER ONLY)")
    @app_commands.describe(task_name="Filter by task name (optional)", limit="Number of logs to show (default: 10)")
    async def view_task_logs(self, interaction: discord.Interaction, task_name: str = None, limit: int = 10):
        """View recent automated task execution logs (BOT OWNER ONLY)."""
        if not await require_bot_owner(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        try:
            if not db.connection_pool:
                db.init_pool()

            logs = db.get_recent_task_logs(task_name=task_name, limit=min(limit, 50))
            if not logs:
                await interaction.followup.send("📋 No task logs found.", ephemeral=True)
                return

            response = f"📋 **Recent Task Logs** ({len(logs)} entries)\n"
            if task_name:
                response += f"Filtered by: `{task_name}`\n"
            response += "\n"

            for log in logs:
                status_emoji = "✅" if log['status'] == 'success' else "❌" if log['status'] == 'error' else "⏳"
                duration = ""
                if log['completed_at']:
                    delta = log['completed_at'] - log['started_at']
                    duration = f" ({delta.total_seconds():.1f}s)"

                response += f"{status_emoji} **{log['task_name']}**{duration}\n"
                response += f"   Started: <t:{int(log['started_at'].timestamp())}:f>\n"
                if log['guild_id']:
                    response += f"   Guild: {log['guild_id']}\n"
                if log['details']:
                    response += f"   Details: {str(log['details'])[:100]}\n"
                if log['error_message']:
                    response += f"   Error: {log['error_message'][:100]}\n"
                response += "\n"

                if len(response) > 1800:
                    response += "... (output truncated)"
                    break

            await interaction.followup.send(response, ephemeral=True)
        except Exception as e:
            logger.error(f"Error viewing task logs: {e}")
            await interaction.followup.send(f"❌ Error retrieving task logs: {str(e)[:100]}", ephemeral=True)
