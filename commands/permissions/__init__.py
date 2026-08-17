"""Permissions command domain: channel access, role grants, conditional
roles, automation rules, and per-user role denies. Consolidates the old
admin_commands.py permission commands and all of mod_tools_commands.py into
one clearly-structured top-level /permissions group with plain, purpose-named
subcommands instead of action-dispatch mega-commands.
"""
from commands.permissions.commands import PermissionsGroup
from commands.permissions.context_menus import check_channel_access_ctx

PERMISSIONS_CONTEXT_MENUS = [
    check_channel_access_ctx,
]

__all__ = [
    'PermissionsGroup',
    'PERMISSIONS_CONTEXT_MENUS',
]
