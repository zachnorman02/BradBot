"""Modals for the permissions domain -- both replace what used to be
comma-separated role-list *string* slash-command params with a small form,
using the shared utils.role_parsing.parse_role_list for resolution.
"""
import discord

from database import db
from utils.role_parsing import parse_role_list
from utils.interaction_helpers import send_error, send_success, error_response


class ConditionalRoleConfigModal(discord.ui.Modal, title="Configure Conditional Role"):
    blocking_roles = discord.ui.Label(
        text="Blocking Roles",
        description="Comma-separated mentions/names/IDs. Having any of these blocks the role.",
        component=discord.ui.TextInput(style=discord.TextStyle.paragraph, required=False, max_length=1000),
    )
    deferral_roles = discord.ui.Label(
        text="Deferral Roles",
        description="Comma-separated. Having any of these marks eligible but defers assignment.",
        component=discord.ui.TextInput(style=discord.TextStyle.paragraph, required=False, max_length=1000),
    )

    def __init__(self, role: discord.Role):
        super().__init__()
        self.role = role

    async def on_submit(self, interaction: discord.Interaction):
        blocking, unresolved_b = parse_role_list(interaction.guild, self.blocking_roles.component.value)
        deferral, unresolved_d = parse_role_list(interaction.guild, self.deferral_roles.component.value)

        db.add_conditional_role_config(
            interaction.guild.id, self.role.id, self.role.name,
            [r.id for r in blocking], [r.id for r in deferral],
        )

        lines = [f"✅ Configured conditional role: {self.role.mention}"]
        lines.append(f"**Blocking Roles:** {', '.join(r.mention for r in blocking) if blocking else 'None'}")
        lines.append(f"**Deferral Roles:** {', '.join(r.mention for r in deferral) if deferral else 'None'}")
        unresolved = unresolved_b + unresolved_d
        if unresolved:
            lines.append(f"⚠️ Could not resolve: {', '.join(unresolved)}")

        await interaction.response.send_message("\n".join(lines), ephemeral=True)


class AutomationRuleModal(discord.ui.Modal, title="Configure Auto-Role Rule"):
    roles_to_add = discord.ui.Label(
        text="Roles To Add",
        description="Comma-separated mentions/names/IDs, applied when the trigger role is present.",
        component=discord.ui.TextInput(style=discord.TextStyle.paragraph, required=False, max_length=1000),
    )
    roles_to_remove = discord.ui.Label(
        text="Roles To Remove",
        description="Comma-separated, removed when the trigger role is present.",
        component=discord.ui.TextInput(style=discord.TextStyle.paragraph, required=False, max_length=1000),
    )

    def __init__(self, rule_name: str, trigger_role: discord.Role):
        super().__init__()
        self.rule_name = rule_name
        self.trigger_role = trigger_role

    async def on_submit(self, interaction: discord.Interaction):
        add_roles, unresolved_a = parse_role_list(interaction.guild, self.roles_to_add.component.value)
        remove_roles, unresolved_r = parse_role_list(interaction.guild, self.roles_to_remove.component.value)

        if not add_roles and not remove_roles:
            await send_error(interaction, "Please provide at least one role to add or remove.")
            return

        db.add_role_rule(
            interaction.guild.id, self.rule_name, self.trigger_role.id,
            [r.id for r in add_roles], [r.id for r in remove_roles],
        )

        lines = [f"✅ Created/updated role rule `{self.rule_name}`", f"**Trigger:** {self.trigger_role.mention}"]
        if add_roles:
            lines.append(f"**Add:** {', '.join(r.mention for r in add_roles)}")
        if remove_roles:
            lines.append(f"**Remove:** {', '.join(r.mention for r in remove_roles)}")
        unresolved = unresolved_a + unresolved_r
        if unresolved:
            lines.append(f"⚠️ Could not resolve: {', '.join(unresolved)}")

        await interaction.response.send_message("\n".join(lines), ephemeral=True)
