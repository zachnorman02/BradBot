"""Modals for the emoji domain -- these replace what used to be 3-4 free-text
slash-command params each. Boolean/choice params (is_sticker, scope,
create_sticker) stay as native slash params since Discord already gives
those a clean picker; only the free-text fields move into the modal.
"""
import re

import discord

from database import db
from utils.interaction_helpers import send_error, send_success, error_response
from commands.emoji.helpers import download_emoji_bytes


class SaveEmojiModal(discord.ui.Modal, title="Save Emoji/Sticker"):
    item = discord.ui.Label(
        text="Item",
        description="A custom emoji (e.g. :name:) or a sticker's exact name.",
        component=discord.ui.TextInput(style=discord.TextStyle.short, max_length=100),
    )
    custom_name = discord.ui.Label(
        text="Custom Name",
        description="Leave blank to use the item's own name.",
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=100),
    )
    notes = discord.ui.Label(
        text="Notes",
        description="Optional notes about this item.",
        component=discord.ui.TextInput(style=discord.TextStyle.paragraph, required=False, max_length=500),
    )

    def __init__(self, is_sticker: bool):
        super().__init__()
        self.is_sticker = is_sticker

    async def on_submit(self, interaction: discord.Interaction):
        item = self.item.component.value.strip()
        custom_name = self.custom_name.component.value.strip() or None
        notes = self.notes.component.value.strip() or None

        await interaction.response.defer(ephemeral=True)

        if self.is_sticker:
            sticker = discord.utils.get(interaction.guild.stickers, name=item)
            if not sticker:
                await send_error(interaction, f"No sticker found with name: `{item}`")
                return
            try:
                image_data = await sticker.read()
                saved_id = db.save_emoji(
                    name=custom_name or sticker.name, image_data=image_data, animated=False,
                    saved_by_user_id=interaction.user.id, saved_from_guild_id=interaction.guild.id,
                    notes=notes, is_sticker=True, sticker_description=sticker.description,
                )
                await send_success(interaction, f"Saved sticker `{custom_name or sticker.name}` (ID: {saved_id})\nUse `/emoji db load {saved_id}` to add it to a server later.")
            except Exception as e:
                await error_response(interaction, e, context="save_emoji_modal_sticker")
            return

        match = re.match(r'<(a?):(\w+):(\d+)>', item)
        if not match:
            await send_error(interaction, "Please provide a custom emoji (e.g., :emoji_name:) or check 'is_sticker' for stickers.")
            return

        is_animated = match.group(1) == 'a'
        emoji_name = match.group(2)
        emoji_id = match.group(3)
        save_name = custom_name or emoji_name

        try:
            image_data = await download_emoji_bytes(emoji_id, is_animated)
            saved_id = db.save_emoji(
                name=save_name, image_data=image_data, animated=is_animated,
                saved_by_user_id=interaction.user.id, saved_from_guild_id=interaction.guild.id,
                notes=notes, is_sticker=False,
            )
            await send_success(interaction, f"Saved emoji `{save_name}` (ID: {saved_id})\nUse `/emoji db load {saved_id}` to add it to a server later.")
        except ValueError as e:
            await send_error(interaction, str(e))
        except Exception as e:
            await error_response(interaction, e, context="save_emoji_modal")


class SaveServerEmojiModal(discord.ui.Modal, title="Save Server Emoji(s)"):
    emoji_name = discord.ui.Label(
        text="Emoji Name",
        description="Required if saving a single emoji; ignored when saving all.",
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=100),
    )
    custom_name = discord.ui.Label(
        text="Custom Name",
        description="Only used for a single emoji. Leave blank to keep its name.",
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=100),
    )
    notes = discord.ui.Label(
        text="Notes",
        description="Optional notes about the emoji(s).",
        component=discord.ui.TextInput(style=discord.TextStyle.paragraph, required=False, max_length=500),
    )

    def __init__(self, scope: str):
        super().__init__()
        self.scope = scope

    async def on_submit(self, interaction: discord.Interaction):
        emoji_name = self.emoji_name.component.value.strip()
        custom_name = self.custom_name.component.value.strip() or None
        notes = self.notes.component.value.strip() or None

        await interaction.response.defer(ephemeral=True)

        if self.scope == "single":
            if not emoji_name:
                await send_error(interaction, "Please provide an emoji name when saving a single emoji.")
                return
            emoji = discord.utils.get(interaction.guild.emojis, name=emoji_name)
            if not emoji:
                await send_error(interaction, f"No emoji found with name: `{emoji_name}` in this server.")
                return
            try:
                image_data = await emoji.read()
                saved_id = db.save_emoji(
                    name=custom_name or emoji.name, image_data=image_data, animated=emoji.animated,
                    saved_by_user_id=interaction.user.id, saved_from_guild_id=interaction.guild.id,
                    notes=notes, is_sticker=False,
                )
                await send_success(interaction, f"Saved emoji `{custom_name or emoji.name}` (ID: {saved_id})\nUse `/emoji db load {saved_id}` to add it to a server later.")
            except Exception as e:
                await error_response(interaction, e, context="save_server_emoji_single")
            return

        if not interaction.guild.emojis:
            await send_error(interaction, "This server has no custom emojis.")
            return

        saved_items = []
        errors = []
        for emoji in interaction.guild.emojis:
            try:
                image_data = await emoji.read()
                saved_id = db.save_emoji(
                    name=emoji.name, image_data=image_data, animated=emoji.animated,
                    saved_by_user_id=interaction.user.id, saved_from_guild_id=interaction.guild.id,
                    notes=notes, is_sticker=False,
                )
                saved_items.append(f"😀 {emoji.name} (ID: {saved_id})")
            except Exception as e:
                errors.append(f"Error saving {emoji.name}: {str(e)[:100]}")

        response = ""
        if saved_items:
            response += f"✅ Saved {len(saved_items)} emoji(s):\n" + "\n".join(saved_items[:20])
            if len(saved_items) > 20:
                response += f"\n... and {len(saved_items) - 20} more"
        if errors:
            response += f"\n\n⚠️ Errors ({len(errors)}):\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                response += f"\n... and {len(errors) - 5} more errors"
        await interaction.followup.send(response[:2000], ephemeral=True)


class AttachmentEmojiNameModal(discord.ui.Modal, title="Create Emoji/Sticker"):
    name = discord.ui.Label(
        text="Name",
        description="Name for the new emoji/sticker.",
        component=discord.ui.TextInput(style=discord.TextStyle.short, max_length=32),
    )

    def __init__(self, image_bytes: bytes, source_name: str, create_sticker: bool):
        super().__init__()
        self.image_bytes = image_bytes
        self.source_name = source_name
        self.create_sticker = create_sticker

    async def on_submit(self, interaction: discord.Interaction):
        from commands.emoji.helpers import create_emoji_or_sticker_with_overwrite

        await interaction.response.defer(ephemeral=True)
        result = await create_emoji_or_sticker_with_overwrite(
            interaction.guild, self.name.component.value.strip(), self.image_bytes, self.source_name, self.create_sticker
        )
        await interaction.followup.send(result, ephemeral=True)
