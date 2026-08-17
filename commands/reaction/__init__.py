"""Reaction-check command domain. No slash commands -- fully replaced by the
"Check Reactions" message context menu (was reaction.check, reaction.check_url,
and utility.check_reaction, three near-duplicate implementations)."""
from commands.reaction.context_menus import check_reactions_ctx

REACTION_CONTEXT_MENUS = [
    check_reactions_ctx,
]

__all__ = ['REACTION_CONTEXT_MENUS']
