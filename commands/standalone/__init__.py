"""Standalone top-level command domain (echo, timestamp)."""
from commands.standalone.commands import echo, timestamp

STANDALONE_COMMANDS = [
    echo,
    timestamp,
]

__all__ = ['STANDALONE_COMMANDS']
