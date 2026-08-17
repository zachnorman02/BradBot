"""Message-targeted (Apps) context menu commands for the emoji domain.
Replaces the message_link-param versions of copy/from_attachment/reaction
(and db save's message_link branch) -- the message is already resolved by
Discord, so there's no link to parse.
"""
import discord
from discord import app_commands

from database import db
from utils.interaction_helpers import send_error, require_guild
from commands.emoji.helpers import (
    check_emoji_permissions, create_emoji_or_sticker_with_overwrite,
    extract_message_emojis, extract_message_images, extract_message_reaction_emojis,
    download_emoji_bytes,
)
from commands.emoji.views import EmojiCandidatePickerView
from commands.emoji.modals import AttachmentEmojiNameModal


async def _guard(interaction: discord.Interaction) -> bool:
    if not await require_guild(interaction):
        return False
    err = await check_emoji_permissions(interaction)
    if err:
        await send_error(interaction, err)
        return False
    return True


@app_commands.context_menu(name="Copy Emoji From Message")
async def copy_emoji_from_message_ctx(interaction: discord.Interaction, message: discord.Message):
    if not await _guard(interaction):
        return

    matches = extract_message_emojis(message)
    if not matches:
        await send_error(interaction, "No custom emoji found in that message.")
        return

    async def do_copy(inter: discord.Interaction, indices: list[int]):
        await inter.response.defer(ephemeral=True)
        results = []
        for idx in indices:
            name, emoji_id, animated = matches[idx]
            try:
                image_bytes = await download_emoji_bytes(emoji_id, animated)
            except ValueError as e:
                results.append(f"❌ {name}: {e}")
                continue
            result = await create_emoji_or_sticker_with_overwrite(inter.guild, name, image_bytes, f"emoji_{name}")
            results.append(result)
            if "reached its" in result:
                break
        await inter.followup.send("\n".join(results), ephemeral=True)

    if len(matches) == 1:
        await do_copy(interaction, [0])
        return

    options = [discord.SelectOption(label=name, value=str(i)) for i, (name, _, _) in enumerate(matches[:25])]
    await interaction.response.send_message(
        "Multiple emoji found -- choose which to copy:", view=EmojiCandidatePickerView(options, do_copy), ephemeral=True
    )


@app_commands.context_menu(name="Copy Emoji From Reaction")
async def copy_emoji_from_reaction_ctx(interaction: discord.Interaction, message: discord.Message):
    if not await _guard(interaction):
        return

    reactions = extract_message_reaction_emojis(message)
    if not reactions:
        await send_error(interaction, "No custom emoji reactions found on that message.")
        return

    async def do_copy(inter: discord.Interaction, indices: list[int]):
        await inter.response.defer(ephemeral=True)
        results = []
        for idx in indices:
            emoji = reactions[idx]
            try:
                image_bytes = await download_emoji_bytes(str(emoji.id), emoji.animated)
            except ValueError as e:
                results.append(f"❌ {emoji.name}: {e}")
                continue
            result = await create_emoji_or_sticker_with_overwrite(inter.guild, emoji.name, image_bytes, f"emoji_{emoji.name}")
            results.append(result)
            if "reached its" in result:
                break
        await inter.followup.send("\n".join(results), ephemeral=True)

    if len(reactions) == 1:
        await do_copy(interaction, [0])
        return

    options = [discord.SelectOption(label=e.name, value=str(i)) for i, e in enumerate(reactions[:25])]
    await interaction.response.send_message(
        "Multiple emoji reactions found -- choose which to copy:", view=EmojiCandidatePickerView(options, do_copy), ephemeral=True
    )


@app_commands.context_menu(name="Create Emoji From Attachment")
async def create_emoji_from_attachment_ctx(interaction: discord.Interaction, message: discord.Message):
    if not await _guard(interaction):
        return

    images = extract_message_images(message)
    if not images:
        await send_error(interaction, "No images found in that message.")
        return

    async def open_name_modal(inter: discord.Interaction, image_type, image_source):
        if image_type == 'attachment':
            size_limit = 256 * 1024
            if image_source.size > size_limit:
                await send_error(inter, f"That image is too large ({image_source.size / 1024:.1f}KB). Discord emojis must be under {size_limit / 1024}KB.")
                return
            image_bytes = await image_source.read()
            source_name = image_source.filename
        else:
            from utils.http_download import download_bytes

            try:
                image_bytes = await download_bytes(image_source)
            except ValueError as e:
                await send_error(inter, str(e))
                return
            source_name = "embed_image"

        await inter.response.send_modal(AttachmentEmojiNameModal(image_bytes, source_name, create_sticker=False))

    if len(images) == 1:
        image_type, image_source = images[0]
        await open_name_modal(interaction, image_type, image_source)
        return

    async def on_pick(inter: discord.Interaction, indices: list[int]):
        image_type, image_source = images[indices[0]]
        await open_name_modal(inter, image_type, image_source)

    options = [discord.SelectOption(label=f"Image {i+1}", value=str(i)) for i in range(min(len(images), 25))]
    view = EmojiCandidatePickerView(options, on_pick)
    view._select.max_values = 1
    await interaction.response.send_message("Multiple images found -- choose one:", view=view, ephemeral=True)


@app_commands.context_menu(name="Save Emojis To Database")
async def save_emojis_from_message_ctx(interaction: discord.Interaction, message: discord.Message):
    if not await _guard(interaction):
        return

    await interaction.response.defer(ephemeral=True)
    matches = extract_message_emojis(message)

    saved_items = []
    errors = []

    for name, emoji_id, animated in matches:
        try:
            image_data = await download_emoji_bytes(emoji_id, animated)
            saved_id = db.save_emoji(
                name=name, image_data=image_data, animated=animated,
                saved_by_user_id=interaction.user.id, saved_from_guild_id=interaction.guild.id,
                notes=None, is_sticker=False,
            )
            saved_items.append(f"😀 {name} (ID: {saved_id})")
        except Exception as e:
            errors.append(f"Error saving {name}: {str(e)[:100]}")

    for sticker in message.stickers:
        try:
            image_data = await sticker.read()
            saved_id = db.save_emoji(
                name=sticker.name, image_data=image_data, animated=False,
                saved_by_user_id=interaction.user.id, saved_from_guild_id=interaction.guild.id,
                notes=None, is_sticker=True, sticker_description=sticker.description,
            )
            saved_items.append(f"🎫 {sticker.name} (ID: {saved_id})")
        except Exception as e:
            errors.append(f"Error saving sticker {sticker.name}: {str(e)[:100]}")

    if not saved_items and not errors:
        await send_error(interaction, "No emojis or stickers found in that message.")
        return

    response = ""
    if saved_items:
        response += f"✅ Saved {len(saved_items)} item(s):\n" + "\n".join(saved_items)
    if errors:
        response += f"\n\n⚠️ Errors ({len(errors)}):\n" + "\n".join(errors[:5])
        if len(errors) > 5:
            response += f"\n... and {len(errors) - 5} more errors"
    await interaction.followup.send(response[:2000], ephemeral=True)
