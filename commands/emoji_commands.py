"""
Emoji and sticker management command group and helpers
"""
import discord
from discord import app_commands
import aiohttp
import io
import re
from database import db


def check_emoji_permissions(interaction: discord.Interaction) -> str | None:
    """
    Check if the user has permission to manage emojis/stickers.
    
    Returns:
        Error message string if permissions are insufficient, None if OK
    """
    if not interaction.guild:
        return "❌ This command can only be used in a server!"
    
    if not interaction.user.guild_permissions.manage_emojis_and_stickers:
        return "❌ You need 'Manage Expressions' permission to use this command."
    
    if not interaction.guild.me.guild_permissions.manage_emojis_and_stickers:
        return "❌ I don't have 'Manage Expressions' permission to create/edit emojis or stickers."
    
    return None


def parse_message_link(link: str) -> tuple[int | None, int | None, int | None]:
    """
    Parse a Discord message link into its components.
    
    Returns:
        Tuple of (guild_id, channel_id, message_id) or (None, None, None) if invalid
    """
    pattern = r'https://discord\.com/channels/(\d+)/(\d+)/(\d+)'
    match = re.match(pattern, link)
    if match:
        guild_id, channel_id, message_id = map(int, match.groups())
        return guild_id, channel_id, message_id
    return None, None, None


async def create_emoji_or_sticker_with_overwrite(
    guild: discord.Guild,
    name: str,
    image_bytes: bytes,
    source_name: str = "image",
    create_sticker: bool = False,
    replace_existing: bool = True
) -> str:
    """
    Create an emoji or sticker, optionally replacing an existing one with the same name.
    
    Returns:
        Status message string
    """
    if create_sticker:
        # Check sticker limits
        sticker_limit = guild.sticker_limit
        existing_sticker = discord.utils.get(guild.stickers, name=name)
        
        if existing_sticker:
            if replace_existing:
                try:
                    await existing_sticker.delete(reason="Replaced with new sticker")
                except discord.Forbidden:
                    return f"❌ I don't have permission to delete the existing sticker '{name}'."
                except Exception as e:
                    return f"❌ Failed to delete existing sticker: {e}"
            else:
                return f"❌ A sticker named '{name}' already exists. Use replace_existing=True to overwrite."
        
        if len(guild.stickers) >= sticker_limit:
            return f"❌ This server has reached its sticker limit ({sticker_limit})."
        
        try:
            new_sticker = await guild.create_sticker(
                name=name,
                description=f"Imported from {source_name}",
                emoji="⭐",
                file=discord.File(io.BytesIO(image_bytes), filename=f"{name}.png"),
                reason="Created via bot command"
            )
            return f"✅ Created sticker: {new_sticker.name}"
        except discord.Forbidden:
            return "❌ I don't have permission to create stickers."
        except discord.HTTPException as e:
            return f"❌ Failed to create sticker: {e}"
    else:
        # Check emoji limits
        emoji_limit = guild.emoji_limit
        existing_emoji = discord.utils.get(guild.emojis, name=name)
        
        if existing_emoji:
            if replace_existing:
                try:
                    await existing_emoji.delete(reason="Replaced with new emoji")
                except discord.Forbidden:
                    return f"❌ I don't have permission to delete the existing emoji '{name}'."
                except Exception as e:
                    return f"❌ Failed to delete existing emoji: {e}"
            else:
                return f"❌ An emoji named '{name}' already exists. Use replace_existing=True to overwrite."
        
        if len(guild.emojis) >= emoji_limit:
            return f"❌ This server has reached its emoji limit ({emoji_limit})."
        
        try:
            new_emoji = await guild.create_custom_emoji(
                name=name,
                image=image_bytes,
                reason="Created via bot command"
            )
            return f"✅ Created emoji: {new_emoji}"
        except discord.Forbidden:
            return "❌ I don't have permission to create emojis."
        except discord.HTTPException as e:
            return f"❌ Failed to create emoji: {e}"


class SavedEmojiGroup(app_commands.Group):
    """Commands for managing saved emojis in the database"""
    
    def __init__(self, bot):
        super().__init__(name="saved", description="Manage saved emojis/stickers")
        self.bot = bot
    
    @app_commands.command(name="save", description="Save an emoji or sticker to the database for later use")
    @app_commands.describe(
        item="The emoji or sticker name to save (not needed if message_link provided)",
        is_sticker="Whether to save a sticker instead of emoji (default: False)",
        name="Optional: custom name for the saved item",
        notes="Optional: notes about this item",
        message_link="Optional: Discord message link to extract emojis/stickers from"
    )
    async def save_emoji(self, interaction: discord.Interaction, item: str = None, is_sticker: bool = False, name: str = None, notes: str = None, message_link: str = None):
        """Save an emoji or sticker to the database"""
        # Check permissions
        permission_check = check_emoji_permissions(interaction)
        if permission_check:
            await interaction.response.send_message(permission_check, ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Validate inputs
        if not item and not message_link:
            await interaction.followup.send("❌ Please provide either an emoji/sticker or a message link.", ephemeral=True)
            return
        
        # Handle message link input
        if message_link:
            parsed = parse_message_link(message_link)
            if not parsed:
                await interaction.followup.send("❌ Invalid message link format.", ephemeral=True)
                return
            
            guild_id, channel_id, message_id = parsed
            
            # Fetch the message
            try:
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    await interaction.followup.send("❌ Cannot access that guild.", ephemeral=True)
                    return
                
                channel = guild.get_channel(int(channel_id))
                if not channel:
                    await interaction.followup.send("❌ Cannot access that channel.", ephemeral=True)
                    return
                
                message = await channel.fetch_message(int(message_id))
            except Exception as e:
                await interaction.followup.send(f"❌ Error fetching message: {str(e)[:200]}", ephemeral=True)
                return
            
            # Extract emojis from message content
            emoji_pattern = r'<(a?):(\w+):(\d+)>'
            emoji_matches = re.findall(emoji_pattern, message.content)
            
            saved_items = []
            errors = []
            
            # Save emojis from message content
            for match in emoji_matches:
                is_animated = match[0] == 'a'
                emoji_name = match[1]
                emoji_id = match[2]
                
                try:
                    # Download emoji
                    ext = 'gif' if is_animated else 'png'
                    url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as resp:
                            if resp.status != 200:
                                errors.append(f"Failed to download emoji {emoji_name}")
                                continue
                            image_data = await resp.read()
                    
                    # Save to database
                    saved_id = db.save_emoji(
                        name=emoji_name,
                        image_data=image_data,
                        animated=is_animated,
                        saved_by_user_id=interaction.user.id,
                        saved_from_guild_id=interaction.guild.id if interaction.guild else None,
                        notes=notes,
                        is_sticker=False
                    )
                    
                    saved_items.append(f"😀 {emoji_name} (ID: {saved_id})")
                except Exception as e:
                    errors.append(f"Error saving {emoji_name}: {str(e)[:100]}")
            
            # Save stickers from message
            for sticker in message.stickers:
                try:
                    image_data = await sticker.read()
                    
                    saved_id = db.save_emoji(
                        name=sticker.name,
                        image_data=image_data,
                        animated=False,
                        saved_by_user_id=interaction.user.id,
                        saved_from_guild_id=interaction.guild.id if interaction.guild else None,
                        notes=notes,
                        is_sticker=True,
                        sticker_description=sticker.description
                    )
                    
                    saved_items.append(f"🎫 {sticker.name} (ID: {saved_id})")
                except Exception as e:
                    errors.append(f"Error saving sticker {sticker.name}: {str(e)[:100]}")
            
            # Build response
            if not saved_items and not errors:
                await interaction.followup.send("❌ No emojis or stickers found in that message.", ephemeral=True)
                return
            
            response = ""
            if saved_items:
                response += f"✅ Saved {len(saved_items)} item(s):\n" + "\n".join(saved_items)
            
            if errors:
                response += f"\n\n⚠️ Errors ({len(errors)}):\n" + "\n".join(errors[:5])
                if len(errors) > 5:
                    response += f"\n... and {len(errors) - 5} more errors"
            
            await interaction.followup.send(response[:2000], ephemeral=True)
            return
        
        # Original save logic for direct emoji/sticker input
        if is_sticker:
            # Find sticker by name
            sticker = discord.utils.get(interaction.guild.stickers, name=item)
            
            if not sticker:
                await interaction.followup.send(f"❌ No sticker found with name: `{item}`", ephemeral=True)
                return
            
            # Download sticker
            try:
                image_data = await sticker.read()
                
                # Save to database
                saved_id = db.save_emoji(
                    name=name or sticker.name,
                    image_data=image_data,
                    animated=False,  # Stickers are not animated in the same way
                    saved_by_user_id=interaction.user.id,
                    saved_from_guild_id=interaction.guild.id if interaction.guild else None,
                    notes=notes,
                    is_sticker=True,
                    sticker_description=sticker.description
                )
                
                await interaction.followup.send(
                    f"✅ Saved sticker `{name or sticker.name}` (ID: {saved_id})\n"
                    f"Use `/emoji saved load {saved_id}` to add it to a server later.",
                    ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(f"❌ Error saving sticker: {str(e)[:200]}", ephemeral=True)
        else:
            # Parse emoji
            emoji_pattern = r'<(a?):(\w+):(\d+)>'
            match = re.match(emoji_pattern, item)
            
            if not match:
                await interaction.followup.send("❌ Please provide a custom emoji (e.g., :emoji_name:) or use is_sticker=True for stickers.", ephemeral=True)
                return
            
            is_animated = match.group(1) == 'a'
            emoji_name = match.group(2)
            emoji_id = match.group(3)
            
            # Use provided name or default to emoji name
            save_name = name or emoji_name
            
            # Download emoji
            ext = 'gif' if is_animated else 'png'
            url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            await interaction.followup.send("❌ Failed to download emoji.", ephemeral=True)
                            return
                        image_data = await resp.read()
                
                # Save to database
                saved_id = db.save_emoji(
                    name=save_name,
                    image_data=image_data,
                    animated=is_animated,
                    saved_by_user_id=interaction.user.id,
                    saved_from_guild_id=interaction.guild.id if interaction.guild else None,
                    notes=notes,
                    is_sticker=False
                )
                
                await interaction.followup.send(
                    f"✅ Saved emoji `{save_name}` (ID: {saved_id})\n"
                    f"Use `/emoji saved load {saved_id}` to add it to a server later.",
                    ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(f"❌ Error saving emoji: {str(e)[:200]}", ephemeral=True)
    
    @app_commands.command(name="load", description="Load a saved emoji/sticker and add it to this server")
    @app_commands.describe(
        search="Emoji/sticker ID or name to search for",
        force_type="Force loading as emoji or sticker (default: use saved type)",
        replace_existing="Replace existing emoji if name conflicts (default: True)"
    )
    @app_commands.choices(force_type=[
        app_commands.Choice(name="Use saved type", value="auto"),
        app_commands.Choice(name="Force as emoji", value="emoji"),
        app_commands.Choice(name="Force as sticker", value="sticker")
    ])
    async def load_emoji(self, interaction: discord.Interaction, search: str, force_type: str = "auto", replace_existing: bool = True):
        """Load a saved emoji/sticker from the database"""
        # Check permissions
        permission_check = check_emoji_permissions(interaction)
        if permission_check:
            await interaction.response.send_message(permission_check, ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Try to get emoji by ID first
        emoji_data = None
        if search.isdigit():
            emoji_data = db.get_saved_emoji(int(search))
        
        # If not found by ID, search by name
        if not emoji_data:
            results = db.search_saved_emojis(search, limit=1)
            if results:
                emoji_data = results[0]
        
        if not emoji_data:
            await interaction.followup.send(f"❌ No saved emoji/sticker found matching: `{search}`", ephemeral=True)
            return
        
        # Determine if loading as sticker or emoji
        create_sticker = emoji_data['is_sticker']
        if force_type == "emoji":
            create_sticker = False
        elif force_type == "sticker":
            create_sticker = True
        
        # Load the image data
        image_data = emoji_data['image_data']
        name = emoji_data['name']
        
        # Create emoji or sticker
        result = await create_emoji_or_sticker_with_overwrite(
            interaction.guild,
            name,
            image_data,
            f"saved emoji {emoji_data['id']}",
            create_sticker,
            replace_existing
        )
        
        await interaction.followup.send(result, ephemeral=True)
    
    @app_commands.command(name="list", description="List saved emojis and stickers")
    @app_commands.describe(
        search="Optional: search term to filter results",
        filter_type="Filter by type (default: all)"
    )
    @app_commands.choices(filter_type=[
        app_commands.Choice(name="All", value="all"),
        app_commands.Choice(name="Emojis only", value="emoji"),
        app_commands.Choice(name="Stickers only", value="sticker")
    ])
    async def list_saved_emojis(self, interaction: discord.Interaction, search: str = None, filter_type: str = "all"):
        """List all saved emojis/stickers"""
        # Check permissions
        permission_check = check_emoji_permissions(interaction)
        if permission_check:
            await interaction.response.send_message(permission_check, ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Get filtering options
        only_stickers = filter_type == "sticker"
        only_emojis = filter_type == "emoji"
        
        # Search database
        results = db.search_saved_emojis(search or "", limit=50, only_stickers=only_stickers, only_emojis=only_emojis)
        
        if not results:
            await interaction.followup.send("No saved emojis/stickers found.", ephemeral=True)
            return
        
        # Build response
        response = f"**Saved Emojis/Stickers** ({len(results)} found):\n\n"
        
        for emoji in results:
            emoji_type = "🎫" if emoji['is_sticker'] else "😀"
            response += f"{emoji_type} **{emoji['name']}** (ID: `{emoji['id']}`)\n"
            if emoji.get('notes'):
                response += f"   _Notes: {emoji['notes'][:50]}_\n"
            
            # Prevent message from getting too long
            if len(response) > 1800:
                response += "... (list truncated)"
                break
        
        await interaction.followup.send(response, ephemeral=True)
    
    @app_commands.command(name="delete", description="Delete a saved emoji from database (bot owner only)")
    @app_commands.describe(
        emoji_id="ID of the emoji to delete"
    )
    async def delete_saved_emoji(self, interaction: discord.Interaction, emoji_id: int):
        """Delete a saved emoji from the database"""
        # Check if user is bot owner
        app_info = await interaction.client.application_info()
        if interaction.user.id != app_info.owner.id:
            await interaction.response.send_message(
                "❌ This command is restricted to the bot owner only.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Check if emoji exists
        emoji_data = db.get_saved_emoji(emoji_id)
        if not emoji_data:
            await interaction.followup.send(f"❌ No saved emoji found with ID: {emoji_id}", ephemeral=True)
            return
        
        # Delete emoji
        db.delete_saved_emoji(emoji_id)
        await interaction.followup.send(f"✅ Deleted saved emoji: `{emoji_data['name']}` (ID: {emoji_id})", ephemeral=True)


class EmojiGroup(app_commands.Group):
    """Emoji and sticker management commands"""
    
    def __init__(self, bot):
        super().__init__(name="emoji", description="Emoji and sticker management")
        self.bot = bot
        
        # Create subgroups
        self.saved = SavedEmojiGroup(bot)
        self.add_command(self.saved)
    
    @app_commands.command(name="copy", description="Copy custom emoji(s) from a message")
    @app_commands.describe(
        message_link="Link to the message containing the emoji", 
        which="Optional: emoji number(s) to copy (e.g. 2 or 1,3). Default: all emojis",
        create_sticker="Create as sticker instead of emoji (default: False)",
        replace_existing="Replace existing emoji if name conflicts (default: True)"
    )
    async def copy(self, interaction: discord.Interaction, message_link: str, which: str = None, create_sticker: bool = False, replace_existing: bool = True):
        # Check permissions
        permission_check = check_emoji_permissions(interaction)
        if permission_check:
            await interaction.response.send_message(permission_check, ephemeral=True)
            return
        
        # Parse message link
        guild_id, channel_id, message_id = parse_message_link(message_link)
        if guild_id is None:
            await interaction.response.send_message("❌ Invalid message link format.", ephemeral=True)
            return
        
        if guild_id != interaction.guild.id:
            await interaction.response.send_message("❌ The message must be from this server.", ephemeral=True)
            return
        
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            await interaction.response.send_message("❌ Could not find the channel.", ephemeral=True)
            return
        
        try:
            msg = await channel.fetch_message(message_id)
        except Exception:
            await interaction.response.send_message("❌ Could not fetch the message.", ephemeral=True)
            return
        
        # Find all custom emojis in the message
        emoji_pattern = r'<a?:([\w]+):([0-9]+)>'
        emoji_matches = list(re.finditer(emoji_pattern, msg.content))
        
        if not emoji_matches:
            await interaction.response.send_message("❌ No custom emoji found in that message.", ephemeral=True)
            return
        
        # Parse which emojis to copy
        indices = []
        if which:
            try:
                indices = [int(i.strip())-1 for i in which.split(",") if i.strip().isdigit()]
                indices = [i for i in indices if 0 <= i < len(emoji_matches)]
                if not indices:
                    await interaction.response.send_message("❌ No valid emoji number(s) specified.", ephemeral=True)
                    return
            except Exception:
                await interaction.response.send_message("❌ Invalid emoji number(s) format. Use e.g. 2 or 1,3.", ephemeral=True)
                return
        else:
            indices = list(range(len(emoji_matches)))  # Default to all emojis
        
        results = []
        
        # Defer the response since this might take a while
        await interaction.response.defer(ephemeral=True)
        
        for idx in indices:
            emoji_match = emoji_matches[idx]
            emoji_name, emoji_id = emoji_match.groups()
            is_animated = msg.content[emoji_match.start()] == '<' and msg.content[emoji_match.start()+1] == 'a'
            ext = 'gif' if is_animated else 'png'
            url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
            
            # Download emoji image
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        results.append(f"❌ Could not download emoji '{emoji_name}'.")
                        continue
                    image_bytes = await resp.read()
            
            # Create emoji or sticker
            result = await create_emoji_or_sticker_with_overwrite(
                interaction.guild, emoji_name, image_bytes, f"emoji_{emoji_name}", create_sticker, replace_existing
            )
            results.append(result)
            
            # Stop if we hit limit
            if "reached its" in result:
                break
        
        await interaction.followup.send("\n".join(results), ephemeral=True)
    
    @app_commands.command(name="upload", description="Upload a custom emoji from an image URL")
    @app_commands.describe(
        name="Name for the new emoji/sticker", 
        url="Image URL to upload",
        create_sticker="Create as sticker instead of emoji (default: False)",
        replace_existing="Replace existing emoji if name conflicts (default: True)"
    )
    async def upload(self, interaction: discord.Interaction, name: str, url: str, create_sticker: bool = False, replace_existing: bool = True):
        # Check permissions
        permission_check = check_emoji_permissions(interaction)
        if permission_check:
            await interaction.response.send_message(permission_check, ephemeral=True)
            return
        
        # Defer the response since downloading and uploading might take time
        await interaction.response.defer(ephemeral=True)
        
        # Download image
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ Could not download the image. Please check the URL.", ephemeral=True)
                    return
                image_bytes = await resp.read()
        
        # Create emoji or sticker
        result = await create_emoji_or_sticker_with_overwrite(
            interaction.guild, name, image_bytes, url.split('/')[-1] or "uploaded_image", create_sticker, replace_existing
        )
        await interaction.followup.send(result, ephemeral=True)

    @app_commands.command(name="rename", description="Rename an existing emoji or sticker")
    @app_commands.describe(
        current_name="Current name of the emoji/sticker to rename",
        new_name="New name for the emoji/sticker",
        is_sticker="Whether to rename a sticker instead of emoji (default: False)"
    )
    async def rename(self, interaction: discord.Interaction, current_name: str, new_name: str, is_sticker: bool = False):
        # Check permissions
        permission_check = check_emoji_permissions(interaction)
        if permission_check:
            await interaction.response.send_message(permission_check, ephemeral=True)
            return
        
        if is_sticker:
            # Find the sticker by name
            existing_item = discord.utils.get(interaction.guild.stickers, name=current_name)
            if not existing_item:
                await interaction.response.send_message(f"❌ No sticker found with the name '{current_name}' in this server.", ephemeral=True)
                return
            
            # Check if new name already exists
            name_conflict = discord.utils.get(interaction.guild.stickers, name=new_name)
            if name_conflict:
                await interaction.response.send_message(f"❌ A sticker with the name '{new_name}' already exists in this server.", ephemeral=True)
                return
            
            item_type = "sticker"
        else:
            # Find the emoji by name
            existing_item = discord.utils.get(interaction.guild.emojis, name=current_name)
            if not existing_item:
                await interaction.response.send_message(f"❌ No emoji found with the name '{current_name}' in this server.", ephemeral=True)
                return
            
            # Check if new name already exists
            name_conflict = discord.utils.get(interaction.guild.emojis, name=new_name)
            if name_conflict:
                await interaction.response.send_message(f"❌ An emoji with the name '{new_name}' already exists in this server.", ephemeral=True)
                return
            
            item_type = "emoji"
        
        try:
            # Edit the name
            await existing_item.edit(name=new_name, reason=f"Renamed by {interaction.user}")
            await interaction.response.send_message(f"✅ {item_type.capitalize()} '{current_name}' has been renamed to '{new_name}'!", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Discord error: {e}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ An unexpected error occurred: {e}", ephemeral=True)

    @app_commands.command(name="from_attachment", description="Create emoji/sticker from a message attachment")
    @app_commands.describe(
        message_link="Link to the message containing the image",
        name="Name for the new emoji/sticker",
        which="Optional: image number(s) to copy if there are multiple (e.g. 2 or 1,3). Default: first image",
        create_sticker="Create as a sticker instead of an emoji (default: False)"
    )
    async def from_attachment(self, interaction: discord.Interaction, message_link: str, name: str, which: str = None, create_sticker: bool = False):
        # Check permissions
        permission_check = check_emoji_permissions(interaction)
        if permission_check:
            await interaction.response.send_message(permission_check, ephemeral=True)
            return
        
        # Parse message link
        guild_id, channel_id, message_id = parse_message_link(message_link)
        if guild_id is None:
            await interaction.response.send_message("❌ Invalid message link format.", ephemeral=True)
            return
        
        if guild_id != interaction.guild.id:
            await interaction.response.send_message("❌ The message must be from this server.", ephemeral=True)
            return
        
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            await interaction.response.send_message("❌ Could not find the channel.", ephemeral=True)
            return
        
        try:
            msg = await channel.fetch_message(message_id)
        except Exception:
            await interaction.response.send_message("❌ Could not fetch the message.", ephemeral=True)
            return
        
        # Find image attachments and embeds
        image_attachments = [att for att in msg.attachments if any(att.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp'])]
        image_embeds = [embed for embed in msg.embeds if embed.image or embed.thumbnail]
        
        all_images = []
        for att in image_attachments:
            all_images.append(('attachment', att))
        for embed in image_embeds:
            if embed.image:
                all_images.append(('embed', embed.image.url))
            elif embed.thumbnail:
                all_images.append(('embed', embed.thumbnail.url))
        
        if not all_images:
            await interaction.response.send_message("❌ No images found in that message.", ephemeral=True)
            return
        
        # Parse which images to copy
        indices = []
        if which:
            try:
                indices = [int(i.strip())-1 for i in which.split(",") if i.strip().isdigit()]
                indices = [i for i in indices if 0 <= i < len(all_images)]
                if not indices:
                    await interaction.response.send_message("❌ No valid image number(s) specified.", ephemeral=True)
                    return
            except Exception:
                await interaction.response.send_message("❌ Invalid image number(s) format. Use e.g. 2 or 1,3.", ephemeral=True)
                return
        else:
            indices = [0]  # Default to first image
        
        results = []
        
        # Defer the response since this might take a while
        await interaction.response.defer(ephemeral=True)
        
        for idx in indices:
            # Get the specified image
            image_type, image_source = all_images[idx]
            
            try:
                if image_type == 'attachment':
                    # Check file size
                    size_limit = 512 * 1024 if create_sticker else 256 * 1024
                    if image_source.size > size_limit:
                        limit_name = "sticker" if create_sticker else "emoji"
                        results.append(f"❌ Image {idx+1} is too large ({image_source.size/1024:.1f}KB). Discord {limit_name}s must be under {size_limit/1024}KB.")
                        continue
                    
                    image_bytes = await image_source.read()
                    source_name = image_source.filename
                else:  # embed image
                    async with aiohttp.ClientSession() as session:
                        async with session.get(image_source) as resp:
                            if resp.status != 200:
                                results.append(f"❌ Could not download embed image {idx+1}.")
                                continue
                            image_bytes = await resp.read()
                            source_name = "embed_image"
                
                # Create emoji or sticker with indexed name if multiple
                emoji_name = name if len(indices) == 1 else f"{name}_{idx+1}"
                result = await create_emoji_or_sticker_with_overwrite(
                    interaction.guild, emoji_name, image_bytes, source_name, create_sticker
                )
                results.append(result)
                
                # Stop if we hit limit
                if "reached its" in result:
                    break
                
            except Exception as e:
                results.append(f"❌ An unexpected error occurred with image {idx+1}: {e}")
        
        await interaction.followup.send("\n".join(results), ephemeral=True)

    @app_commands.command(name="remove", description="Remove an emoji or sticker from this server")
    @app_commands.describe(
        name="Name of the emoji/sticker to remove",
        is_sticker="Whether to remove a sticker instead of emoji (default: False)"
    )
    async def remove(self, interaction: discord.Interaction, name: str, is_sticker: bool = False):
        # Check permissions
        permission_check = check_emoji_permissions(interaction)
        if permission_check:
            await interaction.response.send_message(permission_check, ephemeral=True)
            return
        
        if is_sticker:
            # Find the sticker by name
            existing_item = discord.utils.get(interaction.guild.stickers, name=name)
            if not existing_item:
                await interaction.response.send_message(f"❌ No sticker found with the name '{name}' in this server.", ephemeral=True)
                return
            
            item_type = "sticker"
        else:
            # Find the emoji by name
            existing_item = discord.utils.get(interaction.guild.emojis, name=name)
            if not existing_item:
                await interaction.response.send_message(f"❌ No emoji found with the name '{name}' in this server.", ephemeral=True)
                return
            
            item_type = "emoji"
        
        try:
            # Delete the item
            await existing_item.delete(reason=f"Deleted by {interaction.user}")
            await interaction.response.send_message(f"✅ {item_type.capitalize()} '{name}' has been deleted!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to delete this item.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Discord error: {e}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ An unexpected error occurred: {e}", ephemeral=True)

    @app_commands.command(name="reaction", description="Copy an emoji from a message reaction")
    @app_commands.describe(
        message_link="Link to the message with the reaction",
        which="Optional: reaction number(s) to copy if there are multiple (e.g. 2 or 1,3). Default: all reactions",
        create_sticker="Create as sticker instead of emoji (default: False)",
        replace_existing="Replace existing emoji if name conflicts (default: True)"
    )
    async def from_reaction(self, interaction: discord.Interaction, message_link: str, which: str = None, create_sticker: bool = False, replace_existing: bool = True):
        # Check permissions
        permission_check = check_emoji_permissions(interaction)
        if permission_check:
            await interaction.response.send_message(permission_check, ephemeral=True)
            return
        
        # Parse message link
        guild_id, channel_id, message_id = parse_message_link(message_link)
        if guild_id is None:
            await interaction.response.send_message("❌ Invalid message link format.", ephemeral=True)
            return
        
        if guild_id != interaction.guild.id:
            await interaction.response.send_message("❌ The message must be from this server.", ephemeral=True)
            return
        
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            await interaction.response.send_message("❌ Could not find the channel.", ephemeral=True)
            return
        
        try:
            msg = await channel.fetch_message(message_id)
        except Exception:
            await interaction.response.send_message("❌ Could not fetch the message.", ephemeral=True)
            return
        
        # Find all custom emoji reactions on the message
        custom_reactions = []
        for reaction in msg.reactions:
            if hasattr(reaction.emoji, 'id'):  # Custom emoji
                custom_reactions.append(reaction.emoji)
        
        if not custom_reactions:
            await interaction.response.send_message("❌ No custom emoji reactions found on that message.", ephemeral=True)
            return
        
        # Parse which reactions to copy
        indices = []
        if which:
            try:
                indices = [int(i.strip())-1 for i in which.split(",") if i.strip().isdigit()]
                indices = [i for i in indices if 0 <= i < len(custom_reactions)]
                if not indices:
                    await interaction.response.send_message("❌ No valid reaction number(s) specified.", ephemeral=True)
                    return
            except Exception:
                await interaction.response.send_message("❌ Invalid reaction number(s) format. Use e.g. 2 or 1,3.", ephemeral=True)
                return
        else:
            indices = list(range(len(custom_reactions)))  # Default to all reactions
        
        results = []
        
        # Defer the response since this might take a while
        await interaction.response.defer(ephemeral=True)
        
        for idx in indices:
            # Get the selected emoji
            selected_emoji = custom_reactions[idx]
            emoji_name = selected_emoji.name
            emoji_id = selected_emoji.id
            is_animated = selected_emoji.animated
            
            # Download the custom emoji
            ext = 'gif' if is_animated else 'png'
            url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        results.append(f"❌ Could not download emoji '{emoji_name}'.")
                        continue
                    image_bytes = await resp.read()
            
            # Create emoji or sticker
            result = await create_emoji_or_sticker_with_overwrite(
                interaction.guild, emoji_name, image_bytes, f"emoji_{emoji_name}", create_sticker, replace_existing
            )
            results.append(result)
            
            # Stop if we hit limit
            if "reached its" in result:
                break
        
        await interaction.followup.send("\n".join(results), ephemeral=True)
