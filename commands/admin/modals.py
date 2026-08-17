"""Modals for the admin ops domain -- SQL/audit-log queries used to be
single-line slash-command string params; both are effectively small
query languages, so they're better served by a paragraph text box."""
import discord

from database import db
from utils.logger import logger
from utils.interaction_helpers import require_bot_owner, require_guild, has_permission_or_owner

from commands.admin.helpers import parse_audit_query, ban_user_for_command


class BanAuthorModal(discord.ui.Modal, title="Ban Author From Command"):
    command = discord.ui.Label(
        text="Command",
        description="Which command to ban this user from.",
        component=discord.ui.Select(options=[
            discord.SelectOption(label="Echo", value="echo"),
            discord.SelectOption(label="TTS", value="tts"),
        ]),
    )
    reason = discord.ui.Label(
        text="Reason",
        description="Optional reason for the ban.",
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=200),
    )

    def __init__(self, target_member: discord.Member):
        super().__init__()
        self.target_member = target_member

    async def on_submit(self, interaction: discord.Interaction):
        command_value = self.command.component.values[0]
        reason = self.reason.component.value.strip() or None
        await ban_user_for_command(interaction, self.target_member, command_value, reason)


class SqlQueryModal(discord.ui.Modal, title="Execute SQL Query"):
    query = discord.ui.Label(
        text="SQL Query",
        description="BOT OWNER ONLY. SELECT queries return rows; anything else runs as a write.",
        component=discord.ui.TextInput(style=discord.TextStyle.paragraph, max_length=4000),
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not await require_bot_owner(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        sql = self.query.component.value

        try:
            if not db.connection_pool:
                db.init_pool()

            logger.info(f"🔍 SQL Query executed by {interaction.user} (ID: {interaction.user.id}):")
            logger.info(f"   Query: {sql}")

            is_select = sql.strip().upper().startswith('SELECT')

            if is_select:
                results = db.execute_query(sql)

                if not results:
                    await interaction.followup.send("✅ Query executed successfully. No results returned.", ephemeral=True)
                    return

                response = f"✅ Query returned {len(results)} row(s):\n```\n"
                max_rows = 20
                for i, row in enumerate(results[:max_rows]):
                    response += f"{i+1}. {row}\n"
                if len(results) > max_rows:
                    response += f"... and {len(results) - max_rows} more row(s)\n"
                response += "```"

                if len(response) > 1900:
                    response = response[:1900] + "\n...\n```\n⚠️ Output truncated due to length"

                await interaction.followup.send(response, ephemeral=True)
            else:
                db.execute_query(sql, fetch=False)
                await interaction.followup.send("✅ Query executed successfully.", ephemeral=True)

            logger.info("   ✅ Query completed successfully")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"   ❌ Query failed: {error_msg}")
            await interaction.followup.send(f"❌ Error executing query:\n```\n{error_msg[:1800]}\n```", ephemeral=True)


class AuditLogQueryModal(discord.ui.Modal, title="Query Audit Log"):
    query = discord.ui.Label(
        text="Query",
        description="SQL-like: WHERE action='kick' AND user='@User' LIMIT 10",
        component=discord.ui.TextInput(style=discord.TextStyle.paragraph, max_length=1000),
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not await require_guild(interaction):
            return

        if not await has_permission_or_owner(interaction, view_audit_log=True):
            await interaction.response.send_message(
                "❌ You need the View Audit Log permission to use this command.", ephemeral=True
            )
            return

        bot_member = interaction.guild.get_member(interaction.client.user.id)
        if not bot_member.guild_permissions.view_audit_log:
            await interaction.response.send_message(
                "❌ I don't have permission to view the audit log. Please grant me the `View Audit Log` permission.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        query = self.query.component.value

        try:
            parsed = parse_audit_query(query)

            if "error" in parsed:
                await interaction.followup.send(f"❌ Query error: {parsed['error']}", ephemeral=True)
                return

            audit_params = {'limit': parsed.get('limit', 100)}

            action_map = {
                'kick': discord.AuditLogAction.kick,
                'ban': discord.AuditLogAction.ban,
                'unban': discord.AuditLogAction.unban,
                'member_update': discord.AuditLogAction.member_update,
                'member_role_update': discord.AuditLogAction.member_role_update,
                'channel_create': discord.AuditLogAction.channel_create,
                'channel_delete': discord.AuditLogAction.channel_delete,
                'channel_update': discord.AuditLogAction.channel_update,
                'role_create': discord.AuditLogAction.role_create,
                'role_delete': discord.AuditLogAction.role_delete,
                'role_update': discord.AuditLogAction.role_update,
                'message_delete': discord.AuditLogAction.message_delete,
                'message_bulk_delete': discord.AuditLogAction.message_bulk_delete,
                'message_pin': discord.AuditLogAction.message_pin,
                'message_unpin': discord.AuditLogAction.message_unpin,
            }

            if parsed.get('action'):
                action_key = parsed['action'].strip("'\"").lower()
                if action_key in action_map:
                    audit_params['action'] = action_map[action_key]
                else:
                    await interaction.followup.send(
                        f"❌ Unknown action type: `{parsed['action']}`\nAvailable: {', '.join(action_map.keys())}",
                        ephemeral=True,
                    )
                    return

            user_obj = None
            if parsed.get('user_id'):
                user_obj = interaction.guild.get_member(parsed['user_id'])
            elif parsed.get('user_raw'):
                user_obj = discord.utils.get(interaction.guild.members, name=parsed['user_raw'])
                if not user_obj:
                    user_obj = discord.utils.find(
                        lambda m: m.display_name.lower() == parsed['user_raw'].lower(),
                        interaction.guild.members,
                    )
                if user_obj:
                    parsed['user_id'] = user_obj.id

            if user_obj:
                audit_params['user'] = user_obj

            if parsed.get('target_raw') and not parsed.get('target_id'):
                raw = parsed['target_raw'].lower()
                member = discord.utils.find(
                    lambda m: m.name.lower() == raw or m.display_name.lower() == raw, interaction.guild.members
                )
                if member:
                    parsed['target_id'] = member.id
                else:
                    channel = discord.utils.find(
                        lambda c: getattr(c, "name", "").lower() == raw, interaction.guild.channels
                    )
                    if channel:
                        parsed['target_id'] = channel.id
                    else:
                        role = discord.utils.find(lambda r: r.name.lower() == raw, interaction.guild.roles)
                        if role:
                            parsed['target_id'] = role.id

            entries = []
            async for entry in interaction.guild.audit_logs(**audit_params):
                if parsed.get('user_id') and (not entry.user or entry.user.id != parsed['user_id']):
                    continue
                if parsed.get('target_id') and (not hasattr(entry.target, 'id') or entry.target.id != parsed['target_id']):
                    continue
                if parsed.get('before') and entry.created_at >= parsed['before']:
                    continue
                if parsed.get('after') and entry.created_at <= parsed['after']:
                    continue

                entries.append(entry)
                if len(entries) >= parsed.get('limit', 100):
                    break

            if not entries:
                await interaction.followup.send("📋 No audit log entries found matching your query.", ephemeral=True)
                return

            embed = discord.Embed(
                title="📋 Audit Log Query Results",
                description=f"Found {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}",
                color=discord.Color.blue(),
            )
            embed.add_field(name="🔍 Query", value=f"```{query[:200]}```", inline=False)

            for i, entry in enumerate(entries[:10]):
                action_name = str(entry.action).replace('AuditLogAction.', '')
                user_str = entry.user.mention if entry.user else "Unknown"
                target_str = entry.target.mention if hasattr(entry.target, 'mention') else str(entry.target) if entry.target else "N/A"
                reason_str = entry.reason if entry.reason else "No reason provided"
                timestamp = f"<t:{int(entry.created_at.timestamp())}:R>"
                value = f"**User:** {user_str}\n**Target:** {target_str}\n**Reason:** {reason_str[:50]}\n**When:** {timestamp}"
                embed.add_field(name=f"{i+1}. {action_name}", value=value, inline=False)

            if len(entries) > 10:
                embed.set_footer(text=f"Showing 10 of {len(entries)} entries. Refine your query to see specific results.")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to access the audit log.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in audit log query: {e}")
            await interaction.followup.send(f"❌ Error executing query: {str(e)[:200]}", ephemeral=True)
