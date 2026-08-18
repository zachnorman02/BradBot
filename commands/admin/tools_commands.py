"""Non-access-control admin tools: booster-role bootstrapping, role
housekeeping, and message mirroring configuration. (Permission/access-control
commands -- autorole, channelrestriction, globalmute_role, conditionalrole --
live in commands/permissions/, not here.)"""
import datetime as dt
from collections import defaultdict

import discord
from discord import app_commands

from commands.common import GuildOnlyGroup, owner_or_permissions
from database import db
from utils.logger import logger
from utils.interaction_helpers import send_error, send_success, error_response
from utils.role_permissions import check_role_hierarchy


class AdminToolsGroup(GuildOnlyGroup):
    """Admin tools: booster role management, role housekeeping, message mirroring."""

    def __init__(self):
        super().__init__(name="tools", description="Booster role, role housekeeping, and mirroring tools")

    @app_commands.command(name="loadboosterroles", description="Load existing booster roles into the database")
    @app_commands.default_permissions(administrator=True)
    async def load_booster_roles(self, interaction: discord.Interaction):
        """Scan server for existing booster roles and save them to database."""
        await interaction.response.defer(ephemeral=True)
        try:
            if not db.connection_pool:
                db.init_pool()

            guild = interaction.guild
            roles_found = 0
            roles_saved = 0
            errors = 0
            report_lines = []

            from commands.booster.helpers import find_personal_roles

            for member in guild.members:
                if not member.premium_since:
                    continue
                personal_roles = find_personal_roles(member)
                if not personal_roles:
                    continue
                role = max(personal_roles, key=lambda r: r.position)
                roles_found += 1

                try:
                    color_hex = f"#{role.color.value:06x}"
                    secondary_color_hex = f"#{role.secondary_color.value:06x}" if role.secondary_color else None
                    tertiary_color_hex = f"#{role.tertiary_color.value:06x}" if role.tertiary_color else None
                    icon_hash = role.icon.key if role.icon else None
                    icon_data = None

                    existing_role = db.get_booster_role(member.id, guild.id)
                    color_type = existing_role['color_type'] if existing_role else 'solid'

                    if role.icon:
                        try:
                            icon_data = await role.icon.read()
                        except Exception as e:
                            logger.error(f"Could not read icon for {member.display_name}: {e}")

                    db.store_booster_role(
                        user_id=member.id, guild_id=guild.id, role_id=role.id, role_name=role.name,
                        color_hex=color_hex, color_type=color_type, icon_hash=icon_hash, icon_data=icon_data,
                        secondary_color_hex=secondary_color_hex, tertiary_color_hex=tertiary_color_hex,
                    )
                    roles_saved += 1
                    icon_status = " (with icon)" if icon_data else ""
                    report_lines.append(f"✅ {member.display_name}: `{role.name}`{icon_status}")
                except Exception as e:
                    errors += 1
                    report_lines.append(f"❌ {member.display_name}: Error - {str(e)[:50]}")
                    logger.error(f"Error saving role for {member.display_name}: {e}")

            summary = (
                f"**Booster Roles Scan Complete**\n\n📊 **Summary:**\n"
                f"• Found: {roles_found} role(s)\n• Saved: {roles_saved} role(s)\n• Errors: {errors}\n\n"
            )
            if report_lines:
                summary += "**Details:**\n" + "\n".join(report_lines[:20])
                if len(report_lines) > 20:
                    summary += f"\n... and {len(report_lines) - 20} more"
            else:
                summary += "ℹ️ No custom booster roles found in this server."

            await interaction.followup.send(summary, ephemeral=True)
        except Exception as e:
            await error_response(interaction, e, context="load_booster_roles")

    @app_commands.command(name="saveboosterrole", description="Manually save a booster role to the database")
    @app_commands.describe(
        role="The role to save",
        user="The user who owns the role (select from dropdown)",
        user_id="Alternative: Manually enter user ID (for users not in server)",
    )
    @app_commands.default_permissions(administrator=True)
    async def save_booster_role(
        self, interaction: discord.Interaction, role: discord.Role, user: discord.User = None, user_id: str = None
    ):
        """Manually save a specific booster role to the database."""
        if not user and not user_id:
            await send_error(interaction, "Please provide either a user (from dropdown) or a user_id.")
            return

        await interaction.response.defer(ephemeral=True)
        try:
            if user:
                uid = user.id
            else:
                try:
                    uid = int(user_id)
                except ValueError:
                    await send_error(interaction, "Invalid user ID format. Please provide a numeric user ID.")
                    return

            member = interaction.guild.get_member(uid)
            booster_warning = ""
            if member and not member.premium_since:
                booster_warning = f"\n⚠️ Note: <@{uid}> is not currently a server booster."
            elif not member:
                booster_warning = "\n⚠️ Note: User is not currently in the server."

            if not db.connection_pool:
                db.init_pool()

            color_hex = f"#{role.color.value:06x}"
            secondary_color_hex = f"#{role.secondary_color.value:06x}" if role.secondary_color else None
            tertiary_color_hex = f"#{role.tertiary_color.value:06x}" if role.tertiary_color else None
            icon_hash = role.icon.key if role.icon else None
            icon_data = None

            if tertiary_color_hex:
                color_type = "holographic"
            elif secondary_color_hex:
                color_type = "gradient"
            else:
                color_type = "solid"

            if role.icon:
                try:
                    icon_data = await role.icon.read()
                except Exception as e:
                    logger.error(f"Could not read icon for role {role.name}: {e}")

            db.store_booster_role(
                user_id=uid, guild_id=interaction.guild.id, role_id=role.id, role_name=role.name,
                color_hex=color_hex, color_type=color_type, icon_hash=icon_hash, icon_data=icon_data,
                secondary_color_hex=secondary_color_hex, tertiary_color_hex=tertiary_color_hex,
            )

            icon_status = " with icon" if icon_data else ""
            color_info = color_hex
            if secondary_color_hex:
                color_info += f", {secondary_color_hex}"
            if tertiary_color_hex:
                color_info += f", {tertiary_color_hex}"

            await send_success(
                interaction,
                f"Saved booster role for <@{uid}>\n• Role: `{role.name}`\n"
                f"• Colors: {color_info} ({color_type}){icon_status}{booster_warning}",
            )
        except Exception as e:
            await error_response(interaction, e, context="save_booster_role")

    @app_commands.command(name="shiftrole", description="Move a role up or down by one position")
    @app_commands.describe(role="The role to move", direction="Move the role one step up or down")
    @app_commands.choices(direction=[
        app_commands.Choice(name="Up", value="up"),
        app_commands.Choice(name="Down", value="down"),
    ])
    @owner_or_permissions(manage_roles=True)
    async def shift_role(self, interaction: discord.Interaction, role: discord.Role, direction: app_commands.Choice[str]):
        """Move a role by exactly one position in the role hierarchy."""
        await interaction.response.defer(ephemeral=True)
        try:
            guild = interaction.guild
            bot_member = guild.me

            if role.managed:
                await send_error(interaction, "That role is managed by an integration/bot and cannot be moved.")
                return
            error = check_role_hierarchy(interaction.user, bot_member, role)
            if error:
                await send_error(interaction, error)
                return

            current_pos = role.position
            if direction.value == "up":
                target_pos = current_pos + 1
                max_pos = bot_member.top_role.position - 1
                if target_pos > max_pos:
                    await send_error(interaction, f"Can't move {role.mention} higher because it would be at/above my top role.")
                    return
            else:
                target_pos = current_pos - 1
                if target_pos < 1:
                    await send_error(interaction, f"Can't move {role.mention} lower; it's already at the bottom.")
                    return

            await guild.edit_role_positions(positions={role: target_pos}, reason=f"Role shifted {direction.value} by {interaction.user}")
            await send_success(interaction, f"Shifted {role.mention} **{direction.value}** from `{current_pos}` to `{target_pos}`.")
        except Exception as e:
            await error_response(interaction, e, context="shift_role")

    @app_commands.command(name="kick_inactive_level", description="Kick members with a level role who haven't chatted in N days")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        role="Level role to check (e.g., @lvl 5)",
        days="Kick if last message older than this many days (or never)",
        dry_run="If true, report only without kicking",
    )
    async def kick_inactive_level(self, interaction: discord.Interaction, role: discord.Role, days: int, dry_run: bool = True):
        """Kick members with the specified level role and no recent messages."""
        if days < 1:
            await send_error(interaction, "Days must be at least 1.")
            return

        await interaction.response.defer(ephemeral=True)
        if not db.connection_pool:
            db.init_pool()

        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        candidates = []
        errors = []

        for member in interaction.guild.members:
            if member.bot or role not in member.roles:
                continue
            last_seen = db.get_member_last_activity(interaction.guild.id, member.id)
            if not last_seen or last_seen < cutoff:
                candidates.append((member, last_seen))

        kicked = 0
        if not dry_run:
            for member, _ in candidates:
                try:
                    await member.kick(reason=f"Inactive {days}d with role {role.name}")
                    kicked += 1
                except Exception as e:
                    errors.append(f"{member.display_name}: {str(e)[:80]}")

        lines = [
            f"🔍 Found {len(candidates)} member(s) with {role.mention} inactive ≥ {days}d.",
            "Dry run; no kicks performed." if dry_run else f"Kicked {kicked} member(s).",
        ]
        if errors:
            lines.append(f"⚠️ Errors on {len(errors)} member(s): " + "; ".join(errors[:3]))

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name="mirror_add", description="Start mirroring messages from one channel to another")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(source_channel="Channel to mirror messages from", target_channel="Channel to mirror messages to")
    async def mirror_add(self, interaction: discord.Interaction, source_channel: discord.TextChannel, target_channel: discord.TextChannel):
        if source_channel.id == target_channel.id:
            await send_error(interaction, "Source and target channels cannot be the same.")
            return

        await interaction.response.defer(ephemeral=True)
        bot_member = interaction.guild.get_member(interaction.client.user.id)

        source_perms = source_channel.permissions_for(bot_member)
        if not source_perms.read_messages or not source_perms.read_message_history:
            await send_error(
                interaction,
                f"I don't have permission to read messages in {source_channel.mention}.\n"
                f"Please grant me `Read Messages` and `Read Message History` permissions.",
            )
            return

        target_perms = target_channel.permissions_for(bot_member)
        if not target_perms.send_messages or not target_perms.embed_links:
            await send_error(
                interaction,
                f"I don't have permission to send messages in {target_channel.mention}.\n"
                f"Please grant me `Send Messages` and `Embed Links` permissions.",
            )
            return

        db.add_message_mirror(interaction.guild.id, source_channel.id, target_channel.id)
        await send_success(
            interaction,
            f"Added message mirror\n• Source: {source_channel.mention}\n• Target: {target_channel.mention}\n\n"
            f"Messages sent in {source_channel.mention} will now be copied to {target_channel.mention}.\n"
            f"When the original message is edited or deleted, all mirrors will update automatically.",
        )

    @app_commands.command(name="mirror_remove", description="Stop mirroring messages between two channels")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(source_channel="Mirror source channel", target_channel="Mirror target channel")
    async def mirror_remove(self, interaction: discord.Interaction, source_channel: discord.TextChannel, target_channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        db.remove_message_mirror(interaction.guild.id, source_channel.id, target_channel.id)
        await send_success(
            interaction, f"Removed message mirror\n• Source: {source_channel.mention}\n• Target: {target_channel.mention}"
        )

    @app_commands.command(name="mirror_list", description="Show all message mirror configurations")
    @app_commands.default_permissions(administrator=True)
    async def mirror_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        mirrors = db.get_message_mirrors(interaction.guild.id)
        if not mirrors:
            await interaction.followup.send("📋 No message mirrors configured for this server.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🪞 Message Mirror Configurations", description=f"Found {len(mirrors)} mirror(s)", color=discord.Color.blue()
        )
        by_source = defaultdict(list)
        for m in mirrors:
            by_source[m['source_channel_id']].append(m)

        for source_id, source_mirrors in by_source.items():
            source_ch = interaction.guild.get_channel(source_id)
            source_name = source_ch.mention if source_ch else f"<#{source_id}> (deleted)"
            targets = []
            for m in source_mirrors:
                target_ch = interaction.guild.get_channel(m['target_channel_id'])
                targets.append(target_ch.mention if target_ch else f"<#{m['target_channel_id']}> (deleted)")
            embed.add_field(name=f"📤 Source: {source_name}", value="**Mirrors to:**\n" + "\n".join(f"• {t}" for t in targets), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="mirror_copy_existing", description="Copy existing messages from source into a mirror target")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        source_channel="Channel to copy messages from",
        target_channel="Channel to copy messages to",
        limit="Number of existing messages to copy (default: 100, max: 1000)",
    )
    async def mirror_copy_existing(
        self, interaction: discord.Interaction, source_channel: discord.TextChannel, target_channel: discord.TextChannel, limit: int = 100
    ):
        if limit < 1 or limit > 1000:
            await send_error(interaction, "Limit must be between 1 and 1000.")
            return

        await interaction.response.defer(ephemeral=True)
        bot_member = interaction.guild.get_member(interaction.client.user.id)

        source_perms = source_channel.permissions_for(bot_member)
        if not source_perms.read_messages or not source_perms.read_message_history:
            await send_error(interaction, f"I don't have permission to read messages in {source_channel.mention}.")
            return

        target_perms = target_channel.permissions_for(bot_member)
        if not target_perms.send_messages or not target_perms.embed_links:
            await send_error(interaction, f"I don't have permission to send messages in {target_channel.mention}.")
            return

        from core.message_mirroring import create_mirror_embed

        try:
            messages = [msg async for msg in source_channel.history(limit=limit, oldest_first=True) if not msg.author.bot]
            if not messages:
                await interaction.followup.send(f"📋 No messages found in {source_channel.mention} to copy.", ephemeral=True)
                return

            await interaction.followup.send(
                f"⏳ Copying {len(messages)} message(s) from {source_channel.mention} to {target_channel.mention}...\nThis may take a moment.",
                ephemeral=True,
            )

            copied_count = 0
            errors = 0
            for msg in messages:
                try:
                    embed = create_mirror_embed(msg)
                    embeds_to_send = [embed] + list(msg.embeds[:9])
                    mirror_msg = await target_channel.send(embeds=embeds_to_send)
                    db.track_mirrored_message(msg.id, msg.channel.id, mirror_msg.id, target_channel.id, msg.guild.id)
                    copied_count += 1
                except Exception as e:
                    logger.error(f"Error copying message {msg.id}: {e}")
                    errors += 1

            result_msg = f"✅ Successfully copied {copied_count} message(s) from {source_channel.mention} to {target_channel.mention}."
            if errors > 0:
                result_msg += f"\n⚠️ Failed to copy {errors} message(s)."
            result_msg += "\n\nThese messages will now auto-sync on edits and deletes."
            await interaction.channel.send(result_msg)
        except discord.Forbidden:
            await interaction.channel.send("❌ I don't have permission to access one of the channels.")
        except Exception as e:
            logger.error(f"Error in mirror_copy_existing: {e}")
            await interaction.channel.send(f"❌ Error copying messages: {str(e)[:200]}")

    @app_commands.command(name="assignlvl0", description="Assign lvl 0 to all verified members without a level role")
    @owner_or_permissions(manage_roles=True)
    async def assign_lvl0(self, interaction: discord.Interaction):
        """Assign lvl 0 role to verified members who don't have any level role."""
        await interaction.response.defer(ephemeral=True)
        try:
            if not db.connection_pool:
                db.init_pool()
            verified_name = db.get_guild_setting(interaction.guild.id, "verified_role_name", "verified")
            prefix = db.get_guild_setting(interaction.guild.id, "level_role_prefix", "lvl ")
            lvl0_name = f"{prefix}0"

            verified_role = discord.utils.get(interaction.guild.roles, name=verified_name)
            lvl0_role = discord.utils.get(interaction.guild.roles, name=lvl0_name)

            if not verified_role:
                await send_error(interaction, f"No '{verified_name}' role found in this server.")
                return
            if not lvl0_role:
                await send_error(interaction, f"No '{lvl0_name}' role found in this server.")
                return

            assigned_count = 0
            errors = []
            for member in interaction.guild.members:
                if member.bot or verified_role not in member.roles:
                    continue
                has_lvl_role = any(role.name.lower().startswith(prefix.lower()) for role in member.roles)
                if has_lvl_role:
                    continue
                try:
                    await member.add_roles(lvl0_role, reason=f"Manual lvl 0 assignment by {interaction.user}")
                    assigned_count += 1
                except Exception as e:
                    errors.append(f"{member.display_name}: {str(e)[:50]}")
                    logger.error(f"Error assigning lvl 0 to {member.display_name}: {e}")

            response = f"✅ Assigned lvl 0 to **{assigned_count}** member(s)"
            if errors:
                response += f"\n\n⚠️ Failed to assign {len(errors)} member(s):"
                for error in errors[:5]:
                    response += f"\n- {error}"
                if len(errors) > 5:
                    response += f"\n... and {len(errors) - 5} more"

            await interaction.followup.send(response, ephemeral=True)
        except Exception as e:
            await error_response(interaction, e, context="assign_lvl0")

    @app_commands.command(name="kickunverified", description="Kick unverified users who have been in the server for 30+ days")
    @app_commands.describe(dry_run="Preview who would be kicked without actually kicking them")
    @app_commands.default_permissions(kick_members=True)
    async def kick_unverified(self, interaction: discord.Interaction, dry_run: bool = False):
        """Kick unverified users who have been members for 30+ days and are not in a verification ticket."""
        await interaction.response.defer(ephemeral=True)
        try:
            if not db.connection_pool:
                db.init_pool()
            unverified_name = db.get_guild_setting(interaction.guild.id, "unverified_role_name", "unverified")
            unverified_role = discord.utils.get(interaction.guild.roles, name=unverified_name)

            if not unverified_role:
                await send_error(interaction, f"No '{unverified_name}' role found in this server.")
                return

            verification_category = discord.utils.get(interaction.guild.categories, name="verification")

            now = dt.datetime.now(dt.timezone.utc)
            kicked_count = 0
            skipped_count = 0
            errors = []
            kick_list = []

            for member in interaction.guild.members:
                if member.bot:
                    continue
                if unverified_role not in member.roles or not member.joined_at:
                    continue
                days_since_join = (now - member.joined_at).days
                if days_since_join < 30:
                    continue

                in_verification_ticket = False
                if verification_category:
                    for channel in verification_category.channels:
                        if isinstance(channel, discord.TextChannel) and channel.name.startswith("ticket-"):
                            if channel.permissions_for(member).read_messages:
                                in_verification_ticket = True
                                break

                if in_verification_ticket:
                    skipped_count += 1
                    continue

                if dry_run:
                    kick_list.append(f"{member.display_name} ({member.mention}) - {days_since_join} days")
                    kicked_count += 1
                else:
                    try:
                        await member.kick(
                            reason=f"Kicked by {interaction.user}: Unverified for {days_since_join} days with no active verification ticket"
                        )
                        kicked_count += 1
                    except Exception as e:
                        errors.append(f"{member.display_name}: {str(e)[:50]}")
                        logger.error(f"Error kicking {member.display_name}: {e}")

            if dry_run:
                response = "🔍 **DRY RUN** - Preview of members who would be kicked:\n\n"
                if kicked_count > 0:
                    response += f"Would kick **{kicked_count}** member(s):\n"
                    for member_info in kick_list[:10]:
                        response += f"- {member_info}\n"
                    if len(kick_list) > 10:
                        response += f"\n... and {len(kick_list) - 10} more"
                else:
                    response += "✅ No members would be kicked"
            else:
                response = f"✅ Kicked **{kicked_count}** unverified member(s) who have been in the server for 30+ days"

            if skipped_count > 0:
                response += f"\n🎫 {'Would skip' if dry_run else 'Skipped'} **{skipped_count}** member(s) with active verification tickets"
            if errors:
                response += f"\n\n⚠️ Failed to kick {len(errors)} member(s):"
                for error in errors[:5]:
                    response += f"\n- {error}"
                if len(errors) > 5:
                    response += f"\n... and {len(errors) - 5} more"

            await interaction.followup.send(response, ephemeral=True)
        except Exception as e:
            await error_response(interaction, e, context="kick_unverified")

    @app_commands.command(name="delete_role", description="Delete a single role (admin only)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(role="Role mention/ID/name to delete", confirm="Type YES to confirm deletion")
    async def delete_role(self, interaction: discord.Interaction, role: str, confirm: str):
        """Delete exactly one role. Requires explicit YES confirmation."""
        if confirm.strip().upper() != "YES":
            await send_error(interaction, "You must confirm deletion by typing YES.")
            return

        part = role.strip()
        role_obj = None
        if part.startswith("<@&") and part.endswith(">"):
            try:
                role_obj = interaction.guild.get_role(int(part[3:-1]))
            except Exception:
                pass
        elif part.isdigit():
            role_obj = interaction.guild.get_role(int(part))
        else:
            role_obj = discord.utils.get(interaction.guild.roles, name=part)

        if not role_obj:
            await send_error(interaction, "No valid role found to delete.")
            return

        error = check_role_hierarchy(interaction.user, interaction.guild.me, role_obj)
        if error:
            await send_error(interaction, error)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await role_obj.delete(reason=f"Deleted by {interaction.user}")
            await send_success(interaction, f"Deleted role: {role_obj.name}")
        except Exception as e:
            await error_response(interaction, e, context="delete_role")
