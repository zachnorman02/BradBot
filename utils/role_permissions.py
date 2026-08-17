"""
Shared role-hierarchy and role-deny permission checks.

Consolidates the "can the bot/actor manage this role" checks that were
duplicated across shiftrole, setrole, temporole, restore_booster_roles,
and delete_role in admin_commands.py.
"""
from typing import Optional

import discord


def check_role_hierarchy(
    actor: discord.Member,
    bot_member: discord.Member,
    target_role: discord.Role,
) -> Optional[str]:
    """Return a user-facing error string if actor or bot can't manage
    target_role, else None."""
    if target_role.is_default():
        return "You can't manage @everyone."

    if target_role.managed:
        return "That role is managed by an integration/bot and cannot be modified."

    if not bot_member.guild_permissions.manage_roles:
        return "I need the Manage Roles permission to do that."

    if bot_member.top_role <= target_role:
        return "I can't manage that role because it is above my highest role."

    if actor.top_role <= target_role and not actor.guild_permissions.administrator:
        return "You can't manage a role higher than or equal to your top role."

    return None


def check_role_action_allowed(guild_id: int, role: discord.Role, is_denied) -> Optional[str]:
    """Return an error string if `role` is on the deny-list for this guild,
    else None. `is_denied` is a callable(guild_id, role_id) -> bool (e.g.
    database.db.is_role_denied) so this stays free of a hard db import."""
    if is_denied(guild_id, role.id):
        return f"The role {role.mention} is restricted and cannot be assigned this way."
    return None
