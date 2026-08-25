"""Business logic for the admin domain: SQL-like audit log query parsing,
the "Mirror This Message" context menu's mirroring logic, the booster-role
diagnostic test, and the command-ban action shared with its context menu."""
import re
from datetime import datetime, timedelta

import asyncio

import discord

from utils.logger import logger
from database import db
from utils.interaction_helpers import send_error, send_success, error_response


def parse_audit_query(query: str) -> dict:
    """Parse SQL-like query syntax for audit log filtering.

    Syntax: SELECT * WHERE action='kick' AND user='@User' AND target='@Target' AND after='2024-01-01' LIMIT 10

    Returns dict with: action, user_id, target_id, before, after, limit
    """
    result = {}
    query_upper = query.upper()

    limit_match = re.search(r'LIMIT\s+(\d+)', query_upper)
    if limit_match:
        result['limit'] = min(int(limit_match.group(1)), 100)
    else:
        result['limit'] = 10

    where_match = re.search(r'WHERE\s+(.+?)(?:LIMIT|$)', query, re.IGNORECASE)
    if not where_match:
        return result

    where_clause = where_match.group(1).strip()
    conditions = re.split(r'\s+AND\s+', where_clause, flags=re.IGNORECASE)

    for condition in conditions:
        cond = condition.strip()
        if "=" not in cond:
            continue
        key, value = cond.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
            value = value[1:-1]

        if key == 'action':
            result['action'] = value

        elif key == 'user':
            user_id_match = re.search(r'<@!?(\d+)>|^(\d+)$', value)
            if user_id_match:
                result['user_id'] = int(user_id_match.group(1) or user_id_match.group(2))
            else:
                result['user_raw'] = value

        elif key == 'target':
            target_id_match = re.search(r'<@!?(\d+)>|<#(\d+)>|<@&(\d+)>|^(\d+)$', value)
            if target_id_match:
                result['target_id'] = int(
                    target_id_match.group(1) or target_id_match.group(2)
                    or target_id_match.group(3) or target_id_match.group(4)
                )
            else:
                result['target_raw'] = value

        elif key in ('after', 'before'):
            try:
                relative_match = re.match(r'(\d+)([dhm])', value.lower())
                if relative_match:
                    amount = int(relative_match.group(1))
                    unit = relative_match.group(2)
                    delta = {
                        'd': timedelta(days=amount),
                        'h': timedelta(hours=amount),
                        'm': timedelta(minutes=amount),
                    }[unit]
                    result[key] = datetime.now() - delta
                else:
                    result[key] = datetime.fromisoformat(value)
            except Exception:
                result['error'] = f"Invalid date format for '{key}': {value}"
                return result

    return result


async def mirror_message_to_channel(
    interaction: discord.Interaction,
    original_msg: discord.Message,
    target_channel: discord.TextChannel,
) -> None:
    """Mirror one already-resolved message into target_channel and track it
    for auto-sync on future edits/deletes. Shared by the messagemirror
    'mirror-one' flow and the 'Mirror This Message' context menu, both of
    which already have the discord.Message in hand -- no link parsing here."""
    bot_member = interaction.guild.get_member(interaction.client.user.id)
    target_perms = target_channel.permissions_for(bot_member)
    if not target_perms.send_messages or not target_perms.embed_links:
        await send_error(interaction, f"I don't have permission to send messages in {target_channel.mention}.")
        return

    content = original_msg.content or ""
    embed = discord.Embed(
        description=content if content else "*[No text content]*",
        color=original_msg.author.color if original_msg.author.color != discord.Color.default() else discord.Color.blue(),
        timestamp=original_msg.created_at,
    )
    embed.set_author(name=original_msg.author.display_name, icon_url=original_msg.author.display_avatar.url)
    embed.set_footer(text=f"Mirrored from #{original_msg.channel.name}")

    if original_msg.attachments:
        attachment_text = "\n\n**Attachments:**\n" + "\n".join(
            f"[{att.filename}]({att.url})" for att in original_msg.attachments
        )
        if len(embed.description + attachment_text) <= 4096:
            embed.description += attachment_text
        else:
            embed.add_field(
                name="📎 Attachments",
                value="\n".join(f"[{att.filename}]({att.url})" for att in original_msg.attachments[:10]),
                inline=False,
            )

    embeds_to_send = [embed] + list(original_msg.embeds[:9])

    try:
        mirror_msg = await target_channel.send(embeds=embeds_to_send)
        db.track_mirrored_message(
            original_msg.id, original_msg.channel.id, mirror_msg.id, target_channel.id, interaction.guild.id
        )
        await send_success(
            interaction,
            f"Mirrored message to {target_channel.mention}\n[Jump to mirror]({mirror_msg.jump_url})\n\n"
            f"The mirror will automatically update if the original message is edited or deleted.",
            ephemeral=True,
        )
    except Exception as e:
        await error_response(interaction, e, context="mirror_message_to_channel")


async def run_booster_role_test(interaction: discord.Interaction, target_user: discord.Member, cleanup: bool) -> None:
    """Create a throwaway role and exercise the booster-role positioning
    logic against it, for diagnosing hierarchy issues (bot owner only)."""
    from commands.booster.helpers import _ensure_role_position

    try:
        test_role = await interaction.guild.create_role(
            name=f"🧪 TEST - {target_user.display_name}",
            reason=f"Test booster role positioning (by {interaction.user})",
        )
        initial_position = test_role.position

        role_assigned = True
        assignment_error = None
        try:
            await target_user.add_roles(test_role, reason=f"Test booster role positioning (by {interaction.user})")
        except discord.Forbidden:
            role_assigned = False
            assignment_error = "Bot lacks permission to assign roles"
        except Exception as e:
            role_assigned = False
            assignment_error = str(e)

        await _ensure_role_position(test_role, interaction.guild.me, target_user)

        fetched_roles = await interaction.guild.fetch_roles()
        refreshed_test_role = discord.utils.get(fetched_roles, id=test_role.id)
        final_position = refreshed_test_role.position if refreshed_test_role else test_role.position
        bot_top_position = interaction.guild.me.top_role.position if interaction.guild.me and interaction.guild.me.top_role else None

        # Anchor is the member's highest OTHER role (matches _ensure_role_position's
        # own logic), not a fixed "server booster role" position.
        user_roles = [r for r in target_user.roles if not r.is_default() and r.id != test_role.id]
        highest_user_role = max(user_roles, key=lambda r: r.position) if user_roles else None
        anchor_role = highest_user_role or interaction.guild.premium_subscriber_role

        expected_target = anchor_role.position + 1 if anchor_role else None
        if expected_target is not None and bot_top_position is not None and expected_target >= bot_top_position:
            expected_target = bot_top_position - 1
        skipped_for_hierarchy = (
            expected_target is not None and bot_top_position is not None and expected_target >= bot_top_position
        )
        anchor_label = "user's highest role" if highest_user_role else "server booster role"

        response = [
            "✅ **Booster Role Test Complete**",
            "",
            f"**Target User:** {target_user.mention}",
            f"**Test Role:** {test_role.mention}",
            "",
            "**Role Assignment:**",
            f"• {'✅ Role assigned to user' if role_assigned else f'❌ Failed: {assignment_error}'}",
            "",
            "**Position Changes:**",
            f"• Initial: `{initial_position}` (bottom)",
            f"• Final: `{final_position}`",
            f"• Moved: `{final_position - initial_position}` positions",
            f"• Expected target (above {anchor_label}): `{expected_target if expected_target is not None else 'N/A'}`",
            "",
        ]

        if skipped_for_hierarchy:
            response.append(
                f"⚠️ Move likely skipped: target `{expected_target}` (above {anchor_label}) is at/above bot top role `{bot_top_position}`."
            )
            response.append("")

        if highest_user_role:
            response.append(f"**User's Highest Role:** {highest_user_role.mention} (position `{highest_user_role.position}`)")
            response.append(
                "✅ Test role is above user's highest role"
                if final_position > highest_user_role.position
                else "⚠️ Test role is NOT above user's highest role"
            )
        else:
            response.append("ℹ️ User has no roles to compare against")

        response.append("")
        response.append(f"**Bot's Top Role:** {interaction.guild.me.top_role.mention} (position `{interaction.guild.me.top_role.position}`)")
        response.append(
            "✅ Test role is below bot's top role"
            if final_position < interaction.guild.me.top_role.position
            else "❌ Test role is NOT below bot's top role"
        )

        if cleanup:
            response.append("")
            response.append("🧹 Test role will be deleted in 10 seconds...")
        else:
            response.append("")
            response.append(f"⚠️ **Manual cleanup required** - delete {test_role.mention} when done testing")

        await interaction.followup.send("\n".join(response), ephemeral=True)

        if cleanup:
            await asyncio.sleep(10)
            try:
                await test_role.delete(reason="Test booster role cleanup")
            except Exception as e:
                logger.warning(f"Could not delete test role: {e}")

    except Exception as e:
        logger.error(f"Error testing booster role: {e}")
        await interaction.followup.send(f"❌ Error during test: {e}", ephemeral=True)


async def ban_user_for_command(interaction: discord.Interaction, target_member: discord.Member, command_value: str, reason: str | None) -> None:
    """Shared by the `command_ban` slash command and the "Ban Author From
    Command" message context menu."""
    db.ban_user_for_command(interaction.guild.id, target_member.id, command_value, reason or "", interaction.user.id)
    await send_success(interaction, f"Banned {target_member.display_name} from using {command_value} in this server.")
