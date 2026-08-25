"""Emoji and sticker management commands. `save`/`saveserver` open a Modal
for their free-text fields instead of taking 3-4 string params; `copy`,
`from_attachment`, and `reaction` (message-link-based) are replaced entirely
by the message context menus in commands/emoji/context_menus.py.
"""
import discord
from discord import app_commands

from database import db
from utils.interaction_helpers import send_error, send_success, error_response, require_bot_owner
from commands.emoji.helpers import check_emoji_permissions, create_emoji_or_sticker_with_overwrite


class SavedEmojiGroup(app_commands.Group):
    """Commands for managing saved emojis in the database."""

    def __init__(self):
        super().__init__(name="db", description="Manage saved emojis/stickers in database")

    @app_commands.command(name="save", description="Save an emoji or sticker to the database for later use")
    @app_commands.describe(is_sticker="Whether to save a sticker instead of emoji")
    async def save(self, interaction: discord.Interaction, is_sticker: bool = False):
        """Opens a Modal to save a single emoji/sticker by name.
        To save every emoji in a message at once, right-click it -> Apps -> Save Emojis To Database."""
        err = await check_emoji_permissions(interaction)
        if err:
            await send_error(interaction, err)
            return

        from commands.emoji.modals import SaveEmojiModal

        await interaction.response.send_modal(SaveEmojiModal(is_sticker=is_sticker))

    @app_commands.command(name="load", description="Load a saved emoji/sticker and add it to this server")
    @app_commands.describe(
        search="Emoji/sticker ID or name to search for",
        force_type="Force loading as emoji or sticker (default: use saved type)",
        replace_existing="Replace existing emoji if name conflicts (default: True)",
    )
    @app_commands.choices(force_type=[
        app_commands.Choice(name="Use saved type", value="auto"),
        app_commands.Choice(name="Force as emoji", value="emoji"),
        app_commands.Choice(name="Force as sticker", value="sticker"),
    ])
    async def load(self, interaction: discord.Interaction, search: str, force_type: str = "auto", replace_existing: bool = True):
        err = await check_emoji_permissions(interaction)
        if err:
            await send_error(interaction, err)
            return

        await interaction.response.defer(ephemeral=True)

        emoji_data = db.get_saved_emoji(int(search)) if search.isdigit() else None
        if not emoji_data:
            results = db.search_saved_emojis(search, limit=1)
            if results:
                emoji_data = results[0]

        if not emoji_data:
            await send_error(interaction, f"No saved emoji/sticker found matching: `{search}`")
            return

        create_sticker = emoji_data['is_sticker']
        if force_type == "emoji":
            create_sticker = False
        elif force_type == "sticker":
            create_sticker = True

        image_data = emoji_data['image_data']
        if isinstance(image_data, memoryview):
            image_data = bytes(image_data)

        result = await create_emoji_or_sticker_with_overwrite(
            interaction.guild, emoji_data['name'], image_data, f"saved emoji {emoji_data['id']}", create_sticker, replace_existing
        )
        await interaction.followup.send(result, ephemeral=True)

    @app_commands.command(name="list", description="List saved emojis and stickers")
    @app_commands.describe(search="Optional: search term to filter results", filter_type="Filter by type (default: all)")
    @app_commands.choices(filter_type=[
        app_commands.Choice(name="All", value="all"),
        app_commands.Choice(name="Emojis only", value="emoji"),
        app_commands.Choice(name="Stickers only", value="sticker"),
    ])
    async def list_saved(self, interaction: discord.Interaction, search: str = None, filter_type: str = "all"):
        err = await check_emoji_permissions(interaction)
        if err:
            await send_error(interaction, err)
            return

        await interaction.response.defer(ephemeral=True)
        results = db.search_saved_emojis(
            search or "", limit=50, only_stickers=filter_type == "sticker", only_emojis=filter_type == "emoji"
        )
        if not results:
            await interaction.followup.send("No saved emojis/stickers found.", ephemeral=True)
            return

        response = f"**Saved Emojis/Stickers** ({len(results)} found):\n\n"
        for emoji in results:
            emoji_type = "🎫" if emoji['is_sticker'] else "😀"
            response += f"{emoji_type} **{emoji['name']}** (ID: `{emoji['id']}`)\n"
            if emoji.get('notes'):
                response += f"   _Notes: {emoji['notes'][:50]}_\n"
            if len(response) > 1800:
                response += "... (list truncated)"
                break
        await interaction.followup.send(response, ephemeral=True)

    @app_commands.command(name="saveserver", description="Save emoji(s) from this server to the database")
    @app_commands.describe(scope="Save a specific emoji or all emojis from the server")
    @app_commands.choices(scope=[
        app_commands.Choice(name="Single emoji", value="single"),
        app_commands.Choice(name="All server emojis", value="all"),
    ])
    async def saveserver(self, interaction: discord.Interaction, scope: str):
        err = await check_emoji_permissions(interaction)
        if err:
            await send_error(interaction, err)
            return

        from commands.emoji.modals import SaveServerEmojiModal

        await interaction.response.send_modal(SaveServerEmojiModal(scope=scope))

    @app_commands.command(name="delete", description="Delete a saved emoji from database (bot owner only)")
    @app_commands.describe(emoji_id="ID of the emoji to delete")
    async def delete(self, interaction: discord.Interaction, emoji_id: int):
        if not await require_bot_owner(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        emoji_data = db.get_saved_emoji(emoji_id)
        if not emoji_data:
            await send_error(interaction, f"No saved emoji found with ID: {emoji_id}")
            return

        db.delete_saved_emoji(emoji_id)
        await send_success(interaction, f"Deleted saved emoji: `{emoji_data['name']}` (ID: {emoji_id})")


class EmojiGroup(app_commands.Group):
    """Emoji and sticker management commands."""

    def __init__(self):
        super().__init__(name="emoji", description="Emoji and sticker management")
        self.add_command(SavedEmojiGroup())

    @app_commands.command(name="upload", description="Upload a custom emoji from an image URL")
    @app_commands.describe(
        name="Name for the new emoji/sticker", url="Image URL to upload",
        create_sticker="Create as sticker instead of emoji", replace_existing="Replace existing emoji if name conflicts",
    )
    async def upload(self, interaction: discord.Interaction, name: str, url: str, create_sticker: bool = False, replace_existing: bool = True):
        err = await check_emoji_permissions(interaction)
        if err:
            await send_error(interaction, err)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            from utils.http_download import download_bytes

            image_bytes = await download_bytes(url)
        except ValueError as e:
            await send_error(interaction, str(e))
            return

        result = await create_emoji_or_sticker_with_overwrite(
            interaction.guild, name, image_bytes, url.split('/')[-1] or "uploaded_image", create_sticker, replace_existing
        )
        await interaction.followup.send(result, ephemeral=True)

    @app_commands.command(name="rename", description="Rename an existing emoji or sticker")
    @app_commands.describe(current_name="Current name", new_name="New name", is_sticker="Whether this is a sticker instead of emoji")
    async def rename(self, interaction: discord.Interaction, current_name: str, new_name: str, is_sticker: bool = False):
        err = await check_emoji_permissions(interaction)
        if err:
            await send_error(interaction, err)
            return

        collection = interaction.guild.stickers if is_sticker else interaction.guild.emojis
        item_type = "sticker" if is_sticker else "emoji"

        existing_item = discord.utils.get(collection, name=current_name)
        if not existing_item:
            await send_error(interaction, f"No {item_type} found with the name '{current_name}' in this server.")
            return
        if discord.utils.get(collection, name=new_name):
            await send_error(interaction, f"A {item_type} with the name '{new_name}' already exists in this server.")
            return

        try:
            await existing_item.edit(name=new_name, reason=f"Renamed by {interaction.user}")
            await send_success(interaction, f"{item_type.capitalize()} '{current_name}' has been renamed to '{new_name}'!")
        except Exception as e:
            await error_response(interaction, e, context="emoji_rename")

    @app_commands.command(name="remove", description="Remove an emoji or sticker from this server")
    @app_commands.describe(name="Name of the emoji/sticker to remove", is_sticker="Whether this is a sticker instead of emoji")
    async def remove(self, interaction: discord.Interaction, name: str, is_sticker: bool = False):
        err = await check_emoji_permissions(interaction)
        if err:
            await send_error(interaction, err)
            return

        collection = interaction.guild.stickers if is_sticker else interaction.guild.emojis
        item_type = "sticker" if is_sticker else "emoji"

        existing_item = discord.utils.get(collection, name=name)
        if not existing_item:
            await send_error(interaction, f"No {item_type} found with the name '{name}' in this server.")
            return

        try:
            await existing_item.delete(reason=f"Deleted by {interaction.user}")
            await send_success(interaction, f"{item_type.capitalize()} '{name}' has been deleted!")
        except Exception as e:
            await error_response(interaction, e, context="emoji_remove")
