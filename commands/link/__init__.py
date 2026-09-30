"""Link command domain. No slash commands -- `edit`/`delete`/`remove embed`
are fully replaced by message context menus (right-click a bot message ->
Apps) and the matching reaction shortcuts (commands/link/reactions.py)."""
from commands.link.context_menus import edit_bot_message_ctx, delete_bot_message_ctx, remove_embed_ctx

LINK_CONTEXT_MENUS = [
    edit_bot_message_ctx,
    delete_bot_message_ctx,
    remove_embed_ctx,
]

__all__ = ['LINK_CONTEXT_MENUS']
