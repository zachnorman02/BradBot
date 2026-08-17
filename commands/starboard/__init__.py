"""Starboard command domain."""
from commands.starboard.commands import StarboardGroup
from commands.starboard.context_menus import force_to_starboard_ctx, block_from_starboard_ctx, unblock_from_starboard_ctx

STARBOARD_CONTEXT_MENUS = [
    force_to_starboard_ctx,
    block_from_starboard_ctx,
    unblock_from_starboard_ctx,
]

__all__ = ['StarboardGroup', 'STARBOARD_CONTEXT_MENUS']
