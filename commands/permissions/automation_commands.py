"""Automatic role-assignment rules: when a member has a trigger role, add/
remove other roles. Replaces admin_commands.py's `autorole` (5-way action
dispatch) with plain subcommands; the free-text role lists move into
AutomationRuleModal."""
import discord
from discord import app_commands, ui

from commands.common import GuildOnlyGroup
from commands.permissions.modals import AutomationRuleModal
from database import db
from utils.interaction_helpers import send_error


class RuleRemoveSelect(ui.Select):
    """Dropdown of a guild's active auto-role rules; picking one deletes it
    immediately -- no modal needed since there's nothing to type, just one
    thing to pick."""

    def __init__(self, guild: discord.Guild, rules: list[dict]):
        options = []
        for rule in rules[:25]:
            trigger = guild.get_role(rule['trigger_role_id'])
            options.append(discord.SelectOption(
                label=rule['rule_name'][:100],
                value=rule['rule_name'],
                description=f"Trigger: {trigger.name if trigger else 'deleted role'}"[:100],
            ))
        super().__init__(placeholder="Select a rule to delete...", options=options)

    async def callback(self, interaction: discord.Interaction):
        rule_name = self.values[0]
        db.remove_role_rule(interaction.guild.id, rule_name)
        await interaction.response.edit_message(content=f"🗑️ Removed role rule `{rule_name}`", view=None)


class RuleRemoveView(ui.View):
    def __init__(self, guild: discord.Guild, rules: list[dict]):
        super().__init__(timeout=300)
        self.add_item(RuleRemoveSelect(guild, rules))


class PermissionsAutomationGroup(GuildOnlyGroup):
    """Automatic role assignment rules keyed on a trigger role."""

    def __init__(self):
        super().__init__(name="automation", description="Automatic role assignment rules")

    @app_commands.command(name="configure", description="Create or update an auto-role rule")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(trigger_role="Role that triggers this rule when added to a member")
    async def configure(self, interaction: discord.Interaction, trigger_role: discord.Role):
        if not db.connection_pool:
            db.init_pool()
        existing = db.get_active_role_rule_for_trigger(interaction.guild.id, trigger_role.id)
        await interaction.response.send_modal(AutomationRuleModal(trigger_role=trigger_role, existing=existing))

    @app_commands.command(name="remove", description="Delete an auto-role rule")
    @app_commands.default_permissions(administrator=True)
    async def remove(self, interaction: discord.Interaction):
        rules = db.get_role_rules(interaction.guild.id)
        if not rules:
            await interaction.response.send_message("📋 No role rules configured for this server.", ephemeral=True)
            return
        if len(rules) > 25:
            await interaction.response.send_message(
                "⚠️ Too many rules to list in one dropdown (25 max) -- delete a few, then try again.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            "Pick a rule to delete:", view=RuleRemoveView(interaction.guild, rules), ephemeral=True
        )

    @app_commands.command(name="list", description="Show all auto-role rules")
    @app_commands.default_permissions(administrator=True)
    async def list_rules(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rules = db.get_role_rules(interaction.guild.id)
        if not rules:
            await interaction.followup.send("📋 No role rules configured for this server.", ephemeral=True)
            return

        embed = discord.Embed(title="⚙️ Automatic Role Assignment Rules", description=f"Found {len(rules)} rule(s)", color=discord.Color.blue())
        for rule in rules:
            trigger = interaction.guild.get_role(rule['trigger_role_id'])
            trigger_name = trigger.mention if trigger else f"<@&{rule['trigger_role_id']}> (deleted)"

            add_roles = [(interaction.guild.get_role(rid).mention if interaction.guild.get_role(rid) else f"<@&{rid}> (deleted)") for rid in rule['roles_to_add']]
            remove_roles = [(interaction.guild.get_role(rid).mention if interaction.guild.get_role(rid) else f"<@&{rid}> (deleted)") for rid in rule['roles_to_remove']]

            value_parts = [f"**Trigger:** {trigger_name}"]
            if add_roles:
                value_parts.append(f"**Add:** {', '.join(add_roles)}")
            if remove_roles:
                value_parts.append(f"**Remove:** {', '.join(remove_roles)}")
            embed.add_field(name=f"📌 {rule['rule_name']}", value="\n".join(value_parts), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="check_all", description="Check all members for auto-role rule compliance (read-only)")
    @app_commands.default_permissions(administrator=True)
    async def check_all(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rules = db.get_role_rules(interaction.guild.id)
        if not rules:
            await send_error(interaction, "No role rules configured.")
            return

        issues = []
        for member in interaction.guild.members:
            if member.bot:
                continue
            member_role_ids = {r.id for r in member.roles}
            for rule in rules:
                if rule['trigger_role_id'] not in member_role_ids:
                    continue
                for add_role_id in rule['roles_to_add']:
                    if add_role_id not in member_role_ids:
                        add_role = interaction.guild.get_role(add_role_id)
                        if add_role:
                            issues.append(f"{member.mention} missing {add_role.mention} (trigger: <@&{rule['trigger_role_id']}>)")
                for remove_role_id in rule['roles_to_remove']:
                    if remove_role_id in member_role_ids:
                        remove_role = interaction.guild.get_role(remove_role_id)
                        if remove_role:
                            issues.append(f"{member.mention} still has {remove_role.mention} (should be removed by trigger: <@&{rule['trigger_role_id']}>)")

        embed = discord.Embed(title="🔍 Role Rule Compliance Check", color=discord.Color.blue())
        if issues:
            embed.add_field(name=f"⚠️ Issues Found ({len(issues)})", value="\n".join(issues[:20]), inline=False)
            if len(issues) > 20:
                embed.add_field(name="...", value=f"and {len(issues) - 20} more", inline=False)
        else:
            embed.add_field(name="✅ All Clear", value="No compliance issues found!", inline=False)
        embed.set_footer(text="Note: This is a read-only check. Issues are not automatically fixed.")
        await interaction.followup.send(embed=embed, ephemeral=True)
