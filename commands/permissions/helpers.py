"""Business logic for the permissions domain: role-deny attempt logging,
deferral checks, and the list-embed builders used by the channel-restriction
and conditional-role list views. Standalone functions (not bound to a Group
class) so views can call them without holding a reference to the command
group instance.
"""
from collections import defaultdict

import discord

from database import db
from utils.logger import logger


def build_channel_restrictions_embed(guild: discord.Guild) -> discord.Embed:
    restrictions = db.get_channel_restrictions(guild.id)
    embed = discord.Embed(
        title="🔒 Channel Restrictions",
        description=f"Found {len(restrictions)} restriction(s)" if restrictions else "No restrictions configured",
        color=discord.Color.blue(),
    )
    if not restrictions:
        return embed

    by_channel = defaultdict(list)
    for r in restrictions:
        by_channel[r['channel_id']].append(r)

    for channel_id, channel_restrictions in by_channel.items():
        channel_obj = guild.get_channel(channel_id)
        channel_name = channel_obj.mention if channel_obj else f"Unknown Channel ({channel_id})"

        require_mentions = []
        block_mentions = []
        for r in channel_restrictions:
            role = guild.get_role(r['blocking_role_id'])
            label = "Require" if r.get('mode') == 'require' else "Block"
            mention = role.mention if role else f"Unknown ({r['blocking_role_id']})"
            (require_mentions if label == "Require" else block_mentions).append(mention)

        rules_lines = [
            f"**Channel:** {channel_name}",
            f"**Require:** {', '.join(require_mentions) if require_mentions else 'None'}",
            f"**Block:** {', '.join(block_mentions) if block_mentions else 'None'}",
        ]
        embed.add_field(name=f"🔒 {channel_obj.name if channel_obj else 'Unknown'}", value="\n".join(rules_lines), inline=False)
    return embed


def build_conditional_role_configs_embed(guild: discord.Guild) -> discord.Embed:
    configs = db.get_all_conditional_role_configs(guild.id)
    embed = discord.Embed(
        title="⚙️ Conditional Role Configurations",
        description=f"Found {len(configs)} configured role(s)" if configs else "No conditional roles configured",
        color=discord.Color.blue(),
    )
    for config in configs:
        role_obj = guild.get_role(config['role_id'])
        role_mention = role_obj.mention if role_obj else f"<@&{config['role_id']}> (deleted)"

        blocking_mentions = [
            (guild.get_role(bid).mention if guild.get_role(bid) else f"<@&{bid}> (deleted)")
            for bid in config['blocking_role_ids']
        ]
        deferral_mentions = [
            (guild.get_role(did).mention if guild.get_role(did) else f"<@&{did}> (deleted)")
            for did in config.get('deferral_role_ids', [])
        ]

        try:
            eligible_count = len(db.get_conditional_role_eligible_users(guild.id, config['role_id']))
        except Exception:
            eligible_count = 0

        embed.add_field(
            name=f"🔒 {config.get('role_name', 'Unknown')}",
            value=(
                f"**Role:** {role_mention}\n"
                f"**Blocking Roles:** {', '.join(blocking_mentions) if blocking_mentions else 'None'}\n"
                f"**Deferral Roles:** {', '.join(deferral_mentions) if deferral_mentions else 'None'}\n"
                f"**Queued/Eligible:** {eligible_count}"
            ),
            inline=False,
        )
    return embed


def should_defer_assignment(member: discord.Member, config: dict) -> bool:
    """True if the member has any of config's deferral roles."""
    deferral_role_ids = config.get('deferral_role_ids', [])
    if not deferral_role_ids:
        return False
    user_role_ids = {r.id for r in member.roles}
    return any(role_id in user_role_ids for role_id in deferral_role_ids)


async def record_role_deny_attempt(
    guild: discord.Guild,
    user: discord.Member,
    role: discord.Role,
    source: str,
    actor_user_id: int | None = None,
    notes: str | None = None,
) -> None:
    """Persist and optionally post a role-deny attempt event."""
    try:
        db.log_role_deny_attempt(guild.id, user.id, role.id, source, actor_user_id, notes)
    except Exception as e:
        logger.error(f"[ROLE DENY] Failed to write deny attempt log: {e}")

    try:
        from core.tasks import post_role_deny_log

        await post_role_deny_log(guild, user, role, source, actor_user_id, notes)
    except Exception as e:
        logger.error(f"[ROLE DENY] Failed to post deny attempt channel log: {e}")


def compute_channel_visibility(guild: discord.Guild, *, member: discord.Member = None, role: discord.Role = None):
    """Return (can_see, cannot_see) lists of channel mentions for a member or role.

    For a member this is exact (channel.permissions_for). For a role alone
    (no specific member) this is a best-effort approximation from
    @everyone + that role's own overwrites per channel -- Discord has no
    single API for "can any member with role X see channel Y" independent
    of a member's other roles, so a role-only check can't be exact.
    """
    can_see, cannot_see = [], []
    for channel in guild.channels:
        if isinstance(channel, discord.CategoryChannel):
            continue
        if member is not None:
            visible = channel.permissions_for(member).view_channel
        else:
            overwrites = channel.overwrites
            everyone_ow = overwrites.get(guild.default_role)
            role_ow = overwrites.get(role)
            visible = guild.default_role.permissions.view_channel
            if everyone_ow is not None and everyone_ow.view_channel is not None:
                visible = everyone_ow.view_channel
            if role_ow is not None and role_ow.view_channel is not None:
                visible = role_ow.view_channel
        (can_see if visible else cannot_see).append(channel.mention)
    return can_see, cannot_see
