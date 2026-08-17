"""Single source of truth for what gets registered on the bot's command
tree. Replaces main.py's three previously-inconsistent registration
patterns (a block of bot.tree.add_command(Group()) calls, the bespoke
setup_reaction_commands(tree) function, and two raw @bot.tree.command
decorators for echo/timestamp) with one loop over these three lists.
"""
from commands.admin import AdminGroup, ADMIN_CONTEXT_MENUS
from commands.permissions import PermissionsGroup, PERMISSIONS_CONTEXT_MENUS
from commands.booster import BoosterGroup
from commands.emoji import EmojiGroup, EMOJI_CONTEXT_MENUS
from commands.poll import PollGroup
from commands.alarm import AlarmGroup
from commands.birthday import BirthdayGroup
from commands.convert import ConversionGroup
from commands.link import LINK_CONTEXT_MENUS
from commands.verification import RulesAgreementGroup
from commands.reaction import REACTION_CONTEXT_MENUS
from commands.settings import SettingsGroup
from commands.starboard import StarboardGroup, STARBOARD_CONTEXT_MENUS
from commands.utility import UtilityGroup
from commands.voice import VoiceGroup
from commands.issues import IssuesGroup
from commands.standalone import STANDALONE_COMMANDS

# One instance per top-level command group.
ALL_GROUPS = [
    AdminGroup(),
    PermissionsGroup(),
    BoosterGroup(),
    EmojiGroup(),
    PollGroup(),
    AlarmGroup(),
    BirthdayGroup(),
    ConversionGroup(),
    RulesAgreementGroup(),
    SettingsGroup(),
    StarboardGroup(),
    UtilityGroup(),
    VoiceGroup(),
    IssuesGroup(),
]

# Message/user right-click (Apps) context menu commands.
ALL_CONTEXT_MENUS = [
    *ADMIN_CONTEXT_MENUS,
    *PERMISSIONS_CONTEXT_MENUS,
    *EMOJI_CONTEXT_MENUS,
    *LINK_CONTEXT_MENUS,
    *REACTION_CONTEXT_MENUS,
    *STARBOARD_CONTEXT_MENUS,
]

# Top-level slash commands not part of any group.
ALL_STANDALONE_COMMANDS = list(STANDALONE_COMMANDS)


def register_all(tree) -> None:
    """Add every group, context menu, and standalone command to `tree`."""
    for command in ALL_GROUPS + ALL_CONTEXT_MENUS + ALL_STANDALONE_COMMANDS:
        tree.add_command(command)
