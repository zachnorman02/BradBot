"""
Shared role/member reference parsing.

Consolidates the mention-or-ID-or-name resolution logic that was
independently reimplemented (with minor drift) in admin_commands.py's
autorole/schedule_role/conditionalrole and mod_tools_commands.py.
"""
from typing import Tuple

import discord


def parse_role_list(guild: discord.Guild, raw: str) -> Tuple[list[discord.Role], list[str]]:
    """Resolve a comma-separated string of role mentions/IDs/names.

    Returns (resolved_roles, unresolved_tokens).
    """
    resolved: list[discord.Role] = []
    unresolved: list[str] = []
    if not raw:
        return resolved, unresolved

    for part in (p.strip() for p in raw.split(",")):
        if not part:
            continue
        token = part
        if token.startswith("<@&") and token.endswith(">"):
            token = token[3:-1]

        role = None
        if token.isdigit():
            role = guild.get_role(int(token))
        if role is None:
            role = discord.utils.get(guild.roles, name=part)

        if role is not None:
            resolved.append(role)
        else:
            unresolved.append(part)

    return resolved, unresolved


def format_role_list(roles: list[discord.Role]) -> str:
    """Format a list of roles back into a comma-separated mention string, for
    prefilling a modal or echoing a selection back to the user."""
    return ", ".join(role.mention for role in roles)


def resolve_member_reference(guild: discord.Guild, raw: str) -> discord.Member | None:
    """Resolve a single member mention/ID/username string within a guild."""
    if not raw:
        return None
    token = raw.strip()
    if token.startswith("<@") and token.endswith(">"):
        token = token.lstrip("<@!").rstrip(">")
    if token.isdigit():
        member = guild.get_member(int(token))
        if member:
            return member
    return discord.utils.find(
        lambda m: m.name.lower() == token.lower() or (m.nick and m.nick.lower() == token.lower()),
        guild.members,
    )
