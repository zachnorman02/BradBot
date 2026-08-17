"""Link command domain. No slash commands -- `edit`/`delete` are fully
replaced by message context menus (right-click a bot message -> Apps)."""
from commands.link.context_menus import edit_bot_message_ctx, delete_bot_message_ctx

LINK_CONTEXT_MENUS = [
    edit_bot_message_ctx,
    delete_bot_message_ctx,
]

__all__ = ['LINK_CONTEXT_MENUS']
