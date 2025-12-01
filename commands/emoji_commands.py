"""
Emoji and sticker management command group and helpers
"""
import discord
from discord import app_commands
import aiohttp
import io
import re


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


class EmojiGroup(app_commands.Group):
    """Emoji and sticker management commands"""
    
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

    @app_commands.command(name="image", description="Copy an image from a message attachment as an emoji or sticker")
    @app_commands.describe(
        message_link="Link to the message containing the image",
        name="Name for the new emoji/sticker",
        which="Optional: image number(s) to copy if there are multiple (e.g. 2 or 1,3). Default: first image",
        create_sticker="Create as a sticker instead of an emoji (default: False)"
    )
    async def from_message(self, interaction: discord.Interaction, message_link: str, name: str, which: str = None, create_sticker: bool = False):
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

    @app_commands.command(name="delete", description="Delete an existing emoji or sticker")
    @app_commands.describe(
        name="Name of the emoji/sticker to delete",
        is_sticker="Whether to delete a sticker instead of emoji (default: False)"
    )
    async def delete(self, interaction: discord.Interaction, name: str, is_sticker: bool = False):
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
