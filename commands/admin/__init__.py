"""Admin command domain: server/bot configuration and diagnostics.

Access-control commands (roles, channel restrictions, deny lists) live in
commands/permissions/, not here.
"""
from commands.admin.commands import AdminGroup
from commands.admin.views import AdminSettingsView, CommandToggleView
from commands.admin.context_menus import (
    mirror_this_message,
    ban_author_from_command_ctx,
    restore_booster_role_ctx,
    edit_booster_role_ctx,
    test_booster_role_ctx,
)

ADMIN_CONTEXT_MENUS = [
    mirror_this_message,
    ban_author_from_command_ctx,
    restore_booster_role_ctx,
    edit_booster_role_ctx,
    test_booster_role_ctx,
]

__all__ = [
    'AdminGroup',
    'AdminSettingsView',
    'CommandToggleView',
    'ADMIN_CONTEXT_MENUS',
]
