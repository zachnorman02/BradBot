"""Message/user right-click (Apps) context menu commands for the admin domain."""
import discord
from discord import app_commands

from database import db
from utils.interaction_helpers import send_error, send_success, require_guild, require_bot_owner, has_permission_or_owner, is_bot_owner, error_response
from commands.booster.helpers import get_personal_role
from commands.booster.modals import BoosterCustomizeModal
from commands.admin.views import MirrorChannelPickerView
from commands.admin.modals import BanAuthorModal


async def _member_is_booster_or_actor_is_owner(interaction: discord.Interaction, member: discord.Member) -> bool:
    """Lets the bot owner exercise booster-role admin tooling on a
    non-booster (e.g. themselves) for testing, without loosening it for
    anyone else."""
    if any(r.is_premium_subscriber() for r in member.roles):
        return True
    return await is_bot_owner(interaction)


@app_commands.context_menu(name="Mirror This Message")
async def mirror_this_message(interaction: discord.Interaction, message: discord.Message):
    if not await require_guild(interaction):
        return
    if not await has_permission_or_owner(interaction, administrator=True):
        await send_error(interaction, "You need administrator permissions to use this.")
        return
    await interaction.response.send_message(
        f"Choose a channel to mirror this message into.",
        view=MirrorChannelPickerView(message),
        ephemeral=True,
    )


@app_commands.context_menu(name="Ban Author From Command")
async def ban_author_from_command_ctx(interaction: discord.Interaction, message: discord.Message):
    if not await require_guild(interaction):
        return
    if not await has_permission_or_owner(interaction, administrator=True):
        await send_error(interaction, "You need administrator permissions to use this.")
        return

    target_member = interaction.guild.get_member(message.author.id)
    if target_member is None:
        try:
            target_member = await interaction.guild.fetch_member(message.author.id)
        except Exception:
            target_member = None
    if target_member is None:
        await send_error(interaction, "Could not resolve that message's author as a member of this server.")
        return

    await interaction.response.send_modal(BanAuthorModal(target_member))


@app_commands.context_menu(name="Restore Booster Role")
async def restore_booster_role_ctx(interaction: discord.Interaction, member: discord.Member):
    if not await require_guild(interaction):
        return
    if not await has_permission_or_owner(interaction, administrator=True):
        await send_error(interaction, "You need administrator permissions to use this.")
        return

    from commands.booster.helpers import restore_member_booster_role

    await interaction.response.defer(ephemeral=True)
    try:
        if not db.connection_pool:
            db.init_pool()

        saved = [e for e in db.get_all_booster_roles(interaction.guild.id) if e["user_id"] == member.id]
        if not saved:
            await send_error(interaction, f"No saved booster role found for {member.mention}.")
            return
        if not await _member_is_booster_or_actor_is_owner(interaction, member):
            await send_error(interaction, f"{member.mention} is not currently a server booster.")
            return

        role_obj, icon_applied = await restore_member_booster_role(
            interaction.guild, member, saved[0], reason="Admin restore booster role (context menu)", target_role=None
        )
        if not role_obj:
            await send_error(interaction, f"Failed to restore a booster role for {member.mention}.")
            return

        note = "" if icon_applied or not saved[0].get("icon_data") else " (icon failed to apply)"
        await send_success(interaction, f"Restored {member.mention}'s booster role: {role_obj.mention}{note}")
    except Exception as e:
        await error_response(interaction, e, context="restore_booster_role_ctx")


@app_commands.context_menu(name="Edit Booster Role")
async def edit_booster_role_ctx(interaction: discord.Interaction, member: discord.Member):
    if not await require_guild(interaction):
        return
    if not await has_permission_or_owner(interaction, administrator=True):
        await send_error(interaction, "You need administrator permissions to use this.")
        return
    if not await _member_is_booster_or_actor_is_owner(interaction, member):
        await send_error(interaction, "That user is not a server booster.")
        return

    role = get_personal_role(member)
    if not role:
        await send_error(interaction, "Could not find that user's booster role. They may need to run `/booster customize` first.")
        return

    await interaction.response.send_modal(BoosterCustomizeModal(role=role, member=member))


@app_commands.context_menu(name="Test Booster Role")
async def test_booster_role_ctx(interaction: discord.Interaction, member: discord.Member):
    if not await require_guild(interaction):
        return
    if not await require_bot_owner(interaction):
        return

    from commands.admin.helpers import run_booster_role_test

    await interaction.response.defer(ephemeral=True)
    await run_booster_role_test(interaction, member, cleanup=True)
