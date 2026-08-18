"""Top-level /admin command group. Composes tools/panels/config/ops as
subgroups -- holds no commands of its own. Permission/access-control
commands live under the separate top-level /permissions group, not here."""
import discord
from discord import app_commands

from commands.admin.tools_commands import AdminToolsGroup
from commands.admin.panels_commands import AdminPanelsGroup
from commands.admin.config_commands import AdminConfigGroup
from commands.admin.ops_commands import AdminOpsGroup
from commands.admin.booster_commands import AdminBoosterGroup


class AdminGroup(app_commands.Group):
    """Admin commands for server management."""

    def __init__(self):
        super().__init__(
            name="admin",
            description="Admin server management commands",
            default_permissions=discord.Permissions(administrator=True),
        )
        self.add_command(AdminToolsGroup())
        self.add_command(AdminPanelsGroup())
        self.add_command(AdminConfigGroup())
        self.add_command(AdminOpsGroup())
        self.add_command(AdminBoosterGroup())
