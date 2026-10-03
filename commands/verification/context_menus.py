"""Message-targeted (Apps) context menu for the rules-agreement domain --
right-click a message to add it to the tracked list without opening
/verify settings and retyping every currently-tracked URL.
"""
import discord
from discord import app_commands

from database import db
from utils.interaction_helpers import send_error, send_success, require_guild, has_permission_or_owner


@app_commands.context_menu(name="Track For Rules Agreement")
async def track_rules_message_ctx(interaction: discord.Interaction, message: discord.Message):
    if not await require_guild(interaction):
        return
    if not await has_permission_or_owner(interaction, administrator=True):
        await send_error(interaction, "You need Administrator to do that.")
        return

    existing = db.get_rules_agreement_messages(interaction.guild.id)
    if any(m.get('message_id') == message.id for m in existing):
        await send_error(interaction, "That message is already being tracked.")
        return

    existing.append({'channel_id': message.channel.id, 'message_id': message.id, 'jump_url': message.jump_url})
    db.set_rules_agreement_messages(interaction.guild.id, existing)
    await send_success(
        interaction,
        f"Now tracking reactions on [that message]({message.jump_url}) for rules agreement.\n"
        f"({len(existing)} message(s) tracked in total -- see `/verify status`.)",
    )


@app_commands.context_menu(name="Untrack From Rules Agreement")
async def untrack_rules_message_ctx(interaction: discord.Interaction, message: discord.Message):
    if not await require_guild(interaction):
        return
    if not await has_permission_or_owner(interaction, administrator=True):
        await send_error(interaction, "You need Administrator to do that.")
        return

    existing = db.get_rules_agreement_messages(interaction.guild.id)
    remaining = [m for m in existing if m.get('message_id') != message.id]
    if len(remaining) == len(existing):
        await send_error(interaction, "That message isn't currently tracked.")
        return

    db.set_rules_agreement_messages(interaction.guild.id, remaining)
    await send_success(
        interaction,
        f"Stopped tracking that message for rules agreement.\n"
        f"({len(remaining)} message(s) still tracked -- see `/verify status`.)",
    )
