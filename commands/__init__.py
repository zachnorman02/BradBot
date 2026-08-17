"""Command domains for BradBot.

Each subdirectory here is a self-contained domain package (its own
commands.py/modals.py/views.py/context_menus.py/helpers.py as needed --
see commands/common.py for the shared Group base classes). Nothing is
re-exported at this level; commands/registry.py is the single place that
aggregates every domain for registration on the bot's command tree.
"""
