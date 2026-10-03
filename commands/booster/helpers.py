"""Booster-role business logic shared between the /booster commands and the
admin domain's booster-related user context menus."""
import asyncio
from typing import Optional

import discord

from database import db
from utils.image_processing import prepare_role_icon
from utils.logger import logger

# Guild setting storing a comma-separated list of role IDs that should never
# be treated as someone's personal/booster role, even if they otherwise match
# the "exactly one member" heuristic below (e.g. an Admin role, a VIP award
# role, or any other role that happens to have a single current holder).
BOOSTER_EXCLUDED_ROLES_SETTING = "booster_excluded_role_ids"


def get_excluded_role_ids(guild_id: int) -> set[int]:
    raw = db.get_guild_setting(guild_id, BOOSTER_EXCLUDED_ROLES_SETTING, "")
    return {int(part) for part in raw.split(",") if part.strip().isdigit()}


def add_excluded_role(guild_id: int, role_id: int) -> int:
    """Excludes role_id from booster-role detection going forward, and
    purges any booster_roles DB row currently tracking it -- otherwise a
    stale saved-role entry could later recreate a brand-new role from data
    that belonged to a role we just said should never be treated as
    anyone's booster role again. Returns the number of DB rows purged.
    """
    ids = get_excluded_role_ids(guild_id)
    ids.add(role_id)
    db.set_guild_setting(guild_id, BOOSTER_EXCLUDED_ROLES_SETTING, ",".join(str(i) for i in ids))

    purged = 0
    for row in db.get_all_booster_roles(guild_id):
        if row.get('role_id') == role_id:
            db.delete_booster_role(row['user_id'], guild_id)
            purged += 1
    return purged


def remove_excluded_role(guild_id: int, role_id: int) -> bool:
    """Returns True if the role was actually on the list."""
    ids = get_excluded_role_ids(guild_id)
    if role_id not in ids:
        return False
    ids.discard(role_id)
    db.set_guild_setting(guild_id, BOOSTER_EXCLUDED_ROLES_SETTING, ",".join(str(i) for i in ids))
    return True


# Guild setting storing a comma-separated list of user IDs the bot should
# never auto-create/restore a booster role for when they start boosting
# (see core/tasks.py's handle_booster_started). Doesn't affect manually
# running /booster customize or /booster restore -- only the automatic
# on-boost creation.
BOOSTER_EXCLUDED_USERS_SETTING = "booster_excluded_user_ids"


def get_excluded_user_ids(guild_id: int) -> set[int]:
    raw = db.get_guild_setting(guild_id, BOOSTER_EXCLUDED_USERS_SETTING, "")
    return {int(part) for part in raw.split(",") if part.strip().isdigit()}


def add_excluded_user(guild_id: int, user_id: int) -> int:
    """Excludes user_id from automatic booster-role creation, and purges
    any booster_roles DB row already saved for them (same reasoning as
    add_excluded_role: a stale saved entry would otherwise get restored the
    moment they run /booster customize or /booster restore manually).
    Returns the number of DB rows purged (0 or 1).
    """
    ids = get_excluded_user_ids(guild_id)
    ids.add(user_id)
    db.set_guild_setting(guild_id, BOOSTER_EXCLUDED_USERS_SETTING, ",".join(str(i) for i in ids))

    if db.get_booster_role(user_id, guild_id):
        db.delete_booster_role(user_id, guild_id)
        return 1
    return 0


def remove_excluded_user(guild_id: int, user_id: int) -> bool:
    """Returns True if the user was actually on the list."""
    ids = get_excluded_user_ids(guild_id)
    if user_id not in ids:
        return False
    ids.discard(user_id)
    db.set_guild_setting(guild_id, BOOSTER_EXCLUDED_USERS_SETTING, ",".join(str(i) for i in ids))
    return True


def find_personal_roles(member: discord.Member, excluded_ids: Optional[set[int]] = None) -> list[discord.Role]:
    """Return this member's one-holder roles, excluding @everyone and any
    guild-excluded roles. The single "personal role" heuristic shared by
    get_personal_role, core/tasks.py's booster lifecycle, and the admin
    loadboosterroles scan -- previously duplicated three times with no
    exclusion support in any of them.
    """
    if excluded_ids is None:
        excluded_ids = get_excluded_role_ids(member.guild.id)
    return [
        role for role in member.roles
        if not role.is_default() and role.id not in excluded_ids and len(role.members) == 1
    ]


def get_personal_role(member: discord.Member, db_role_data: Optional[dict] = None) -> Optional[discord.Role]:
    """Find a member's booster/personal role.

    Prefers the DB's tracked role_id (if that role still exists, the member
    still holds it, and it isn't guild-excluded) over the "highest-positioned
    single-member role" heuristic below. The heuristic alone can grab the
    wrong role if the member happens to hold more than one single-member
    role (e.g. a leftover role from earlier testing), silently returning the
    wrong role's colors/name/icon instead of the one actually tracked as
    theirs.
    """
    excluded_ids = get_excluded_role_ids(member.guild.id)

    if db_role_data and db_role_data.get('role_id'):
        tracked = member.guild.get_role(db_role_data['role_id'])
        if tracked and tracked.id not in excluded_ids and tracked in member.roles:
            return tracked

    personal_roles = find_personal_roles(member, excluded_ids)
    if not personal_roles:
        return None
    return max(personal_roles, key=lambda r: r.position)


async def _ensure_role_position(role: discord.Role, bot_member: discord.Member, member: Optional[discord.Member] = None) -> None:
    """Keep a personal/booster role positioned just above the member's
    highest other role, staying under the bot's own top role.

    Idempotent by design: if the role is already above that anchor, nothing
    is touched. This means manually dragging the role higher in Discord's
    UI sticks -- a later bot-triggered edit (e.g. /booster customize) won't
    silently revert it back down to a fixed anchor. It only moves the role
    when it's genuinely below where it should be (freshly created, or the
    member gained a new higher role since).
    """
    guild = role.guild
    bot_top = bot_member.top_role.position if bot_member and bot_member.top_role else None

    anchor_role = None
    if member:
        user_roles = [r for r in member.roles if not r.is_default() and r.id != role.id]
        if user_roles:
            anchor_role = max(user_roles, key=lambda r: r.position)

    if anchor_role is None:
        # No other roles to anchor on (e.g. member fetched without full role
        # cache) -- fall back to the server's built-in Booster role if any.
        booster_role = guild.premium_subscriber_role
        if booster_role and booster_role.position is not None:
            anchor_role = booster_role

    if anchor_role is None:
        logger.warning(
            "Skipping position update for role_id=%s: no anchor role found (member has no other roles and no server booster role exists).",
            role.id,
        )
        return

    if role.position > anchor_role.position:
        logger.info(
            "Booster role positioning: role_id=%s already above anchor=%s (role_pos=%s anchor_pos=%s); leaving in place.",
            role.id, anchor_role.id, role.position, anchor_role.position,
        )
        return

    target = anchor_role.position + 1
    if bot_top is not None and target >= bot_top:
        adjusted_target = bot_top - 1
        if adjusted_target < 1:
            logger.warning(f"Skipping position update for {role.name}: no valid target under bot top role {bot_top}.")
            return
        logger.info(
            "Adjusting booster role target for hierarchy: role_id=%s requested=%s adjusted=%s bot_top=%s",
            role.id, target, adjusted_target, bot_top,
        )
        target = adjusted_target

    try:
        logger.info("Attempting role move: role_id=%s from=%s to=%s anchor=%s", role.id, role.position, target, anchor_role.id)
        await guild.edit_role_positions(positions={role: target}, reason="Place booster role above member's highest role")

        fetched_roles = await guild.fetch_roles()
        moved_role = discord.utils.get(fetched_roles, id=role.id)
        logger.info("Post-move verification: role_id=%s expected=%s actual=%s", role.id, target, moved_role.position if moved_role else None)
    except Exception as e:
        logger.warning(f"Could not adjust position for {role.name}: {e}")


def _icon_bytes(icon_data):
    """Normalize icon payload from DB (may be memoryview/bytes/None)."""
    if icon_data is None:
        return None
    if isinstance(icon_data, memoryview):
        return icon_data.tobytes()
    if isinstance(icon_data, str) and icon_data.startswith("\\x"):
        try:
            return bytes.fromhex(icon_data[2:])
        except Exception:
            return None
    if isinstance(icon_data, bytes):
        return icon_data
    return icon_data


async def _apply_icon(role: discord.Role, icon_data, guild: discord.Guild) -> bool:
    """Try to apply icon; return True if set, False if skipped/failed."""
    payload = _icon_bytes(icon_data)
    if not payload:
        return False
    if "ROLE_ICONS" not in guild.features:
        logger.info(f"Guild missing ROLE_ICONS; skip icon for {role}")
        return False
    try:
        # Icons saved before we started normalizing uploads may still be
        # encoded in a way that loses transparency, so re-normalize on
        # every re-apply, not just at upload time.
        # Decoding/quantizing/re-encoding is CPU-bound; keep it off the event loop.
        normalized = await asyncio.to_thread(prepare_role_icon, payload)
        await role.edit(display_icon=normalized)
        return True
    except Exception as e:
        logger.error(f"Could not apply icon for {role}: {e}")
        return False


async def get_or_create_booster_role(interaction: discord.Interaction, db_role_data: dict = None):
    """Get existing booster role or create/restore from database."""
    personal_role = get_personal_role(interaction.user, db_role_data)

    if not personal_role and db_role_data:
        try:
            icon_payload = _icon_bytes(db_role_data.get('icon_data'))
            primary_color = discord.Color(int(db_role_data['color_hex'].replace('#', ''), 16))
            secondary_color = None
            tertiary_color = None

            if db_role_data.get('secondary_color_hex'):
                secondary_color = discord.Color(int(db_role_data['secondary_color_hex'].replace('#', ''), 16))
            if db_role_data.get('tertiary_color_hex'):
                tertiary_color = discord.Color(int(db_role_data['tertiary_color_hex'].replace('#', ''), 16))

            personal_role = await interaction.guild.create_role(
                name=db_role_data['role_name'], color=primary_color, secondary_color=secondary_color,
                tertiary_color=tertiary_color, reason="Restoring saved booster role",
            )
            await _ensure_role_position(personal_role, interaction.guild.me, interaction.user)
            await _apply_icon(personal_role, icon_payload, interaction.guild)
            await interaction.user.add_roles(personal_role, reason="Restoring saved booster role")
            db.update_booster_role_id(interaction.user.id, interaction.guild.id, personal_role.id)
        except Exception as e:
            logger.error(f"Error restoring role from database: {e}")
            return None

    if not personal_role:
        try:
            personal_role = await interaction.guild.create_role(name=f"{interaction.user.display_name}'s Role", reason="Booster role customization")
            await _ensure_role_position(personal_role, interaction.guild.me, interaction.user)
            await interaction.user.add_roles(personal_role, reason="Booster role customization")
        except Exception as e:
            logger.error(f"Error creating new role: {e}")
            return None
    else:
        await _ensure_role_position(personal_role, interaction.guild.me, interaction.user)
        icon_payload = _icon_bytes(db_role_data.get("icon_data")) if db_role_data else None
        if db_role_data:
            await _apply_icon(personal_role, icon_payload, interaction.guild)

    return personal_role


async def restore_member_booster_role(
    guild: discord.Guild,
    member: discord.Member,
    db_role_data: dict,
    reason: str = "Restore booster role",
    target_role: Optional[discord.Role] = None,
    assign: bool = True,
):
    """Restore or recreate a member's booster role using saved DB data. If
    target_role is provided, apply to that role.

    If assign is False, the role is created/updated and positioned but not
    added to the member -- for admin recovery of a non-boosting member's
    accidentally-deleted role, where handing them the booster-perk role
    while they aren't actually boosting wouldn't be appropriate.
    """
    bot_member = guild.me
    personal_role = target_role if target_role else get_personal_role(member, db_role_data)

    try:
        primary_color = discord.Color(int(db_role_data['color_hex'].replace('#', ''), 16))
        secondary_color = discord.Color(int(db_role_data['secondary_color_hex'].replace('#', ''), 16)) if db_role_data.get('secondary_color_hex') else None
        tertiary_color = discord.Color(int(db_role_data['tertiary_color_hex'].replace('#', ''), 16)) if db_role_data.get('tertiary_color_hex') else None
    except Exception as e:
        logger.warning(f"Invalid color data in DB for user {member.id}: {e}")
        primary_color = discord.Color.default()
        secondary_color = None
        tertiary_color = None

    if not personal_role:
        try:
            personal_role = await guild.create_role(
                name=db_role_data.get('role_name') or f"{member.display_name}'s Role",
                color=primary_color, secondary_color=secondary_color, tertiary_color=tertiary_color, reason=reason,
            )
            await _ensure_role_position(personal_role, bot_member, member)
            if assign:
                await member.add_roles(personal_role, reason=reason)
            db.update_booster_role_id(member.id, guild.id, personal_role.id)
        except Exception as e:
            logger.error(f"Failed to create role for {member}: {e}")
            return None, False
    else:
        try:
            await personal_role.edit(color=primary_color, secondary_color=secondary_color, tertiary_color=tertiary_color, reason=reason)
        except Exception as e:
            logger.error(f"Could not edit colors for {personal_role}: {e}")

        await _ensure_role_position(personal_role, bot_member, member)
        if assign and personal_role not in member.roles:
            try:
                await member.add_roles(personal_role, reason=reason)
            except Exception as e:
                logger.error(f"Could not assign provided role to {member}: {e}")

    icon_applied = await _apply_icon(personal_role, db_role_data.get("icon_data"), guild)
    return personal_role, icon_applied


async def save_role_to_db(user_id: int, guild_id: int, role: discord.Role):
    """Save role configuration to database. Auto-detects color_type."""
    try:
        color_hex = f"#{role.color.value:06x}"
        secondary_color_hex = f"#{role.secondary_color.value:06x}" if role.secondary_color else None
        tertiary_color_hex = f"#{role.tertiary_color.value:06x}" if role.tertiary_color else None
        icon_hash = role.icon.key if role.icon else None
        icon_data = None

        if role.icon:
            try:
                icon_data = await role.icon.read()
            except Exception:
                pass

        if tertiary_color_hex:
            color_type = "holographic"
        elif secondary_color_hex:
            color_type = "gradient"
        else:
            color_type = "solid"

        db.store_booster_role(
            user_id=user_id, guild_id=guild_id, role_id=role.id, role_name=role.name,
            color_hex=color_hex, color_type=color_type, icon_hash=icon_hash, icon_data=icon_data,
            secondary_color_hex=secondary_color_hex, tertiary_color_hex=tertiary_color_hex,
        )
    except Exception as e:
        logger.error(f"Error saving role to database: {e}")
