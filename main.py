import enum
import aiohttp
import datetime
import discord
from discord.ext import commands
from discord import app_commands
import os
import re
import asyncio
from dotenv import load_dotenv
from typing import Literal
from websites import websites, fix_link_async, get_site_name

# Load environment variables from .env file
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# In-memory settings: {guild_id: include_original_message}
settings = {}

# Helper functions for emoji commands
def check_emoji_permissions(interaction: discord.Interaction) -> str | None:
    """Check if both bot and user have create expressions permission. Returns error message or None if OK."""
    if not interaction.guild.me.guild_permissions.create_expressions:
        return "❌ I need the 'Create Expressions' permission."
    if not interaction.user.guild_permissions.create_expressions:
        return "❌ You need the 'Create Expressions' permission."
    return None

def parse_message_link(message_link: str):
    """Parse message link and return guild_id, channel_id, message_id or None if invalid"""
    import re
    match = re.match(r"https://discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)", message_link)
    if not match:
        return None, None, None
    
    guild_id, channel_id, message_id = map(int, match.groups())
    return guild_id, channel_id, message_id

async def create_emoji_or_sticker_with_overwrite(guild, name: str, image_bytes: bytes, source_name: str = "image", create_sticker: bool = False) -> str:
    """Create emoji or sticker, overwriting if exists. Returns result message."""
    import io
    
    if create_sticker:
        # Handle sticker creation
        existing_sticker = discord.utils.get(guild.stickers, name=name)
        if existing_sticker:
            try:
                await existing_sticker.delete(reason="Overwriting with new sticker")
            except Exception:
                pass
        
        try:
            new_sticker = await guild.create_sticker(
                name=name,
                description=f"Sticker from {source_name}",
                emoji="📷",
                file=discord.File(io.BytesIO(image_bytes), filename=source_name)
            )
            action = "replaced" if existing_sticker else "created"
            return f"✅ Sticker '{new_sticker.name}' {action}!"
        except discord.HTTPException as e:
            if e.code == 30008:
                return "❌ This server has reached its sticker limit."
            else:
                return f"❌ Discord error: {e}"
        except Exception as e:
            return f"❌ An unexpected error occurred: {e}"
    else:
        # Handle emoji creation
        existing_emoji = discord.utils.get(guild.emojis, name=name)
        if existing_emoji:
            try:
                await existing_emoji.delete(reason="Overwriting with new emoji")
            except Exception:
                pass
        
        try:
            new_emoji = await guild.create_custom_emoji(name=name, image=image_bytes)
            action = "replaced" if existing_emoji else "created"
            return f"✅ Emoji '{new_emoji.name}' {action}!"
        except discord.HTTPException as e:
            if e.code == 30008:
                return "❌ This server has reached its emoji limit."
            else:
                return f"❌ Discord error: {e}"
        except Exception as e:
            return f"❌ An unexpected error occurred: {e}"

async def daily_booster_role_check():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.datetime.now(datetime.UTC)
        # Run at midnight UTC
        next_run = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        wait_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        for guild in bot.guilds:
            booster_role = discord.utils.get(guild.roles, is_premium_subscriber=True)
            if not booster_role:
                continue
            for member in guild.members:
                # Find custom roles (only one member, not @everyone, not booster role)
                personal_roles = [role for role in member.roles if role != booster_role and not role.is_default() and len(role.members) == 1]
                if personal_roles and booster_role not in member.roles:
                    for role in personal_roles:
                        try:
                            await role.delete(reason="Lost server booster status")
                        except Exception:
                            pass

@bot.event
async def on_ready():
    print(f'{bot.user} has logged in!')
    
    # Add command groups to the tree (testing new BoosterGroup)
    bot.tree.add_command(EmojiGroup(name="emoji", description="Emoji and sticker management commands"))
    bot.tree.add_command(BoosterGroup())
    
    try:
        # Sync slash commands
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    # Start daily booster role check task
    bot.loop.create_task(daily_booster_role_check())
    
# List of sites that support EmbedEZ
EMBEDEZ_SITES = {'instagram', 'snapchat', 'ifunny', 'imgur', 'weibo', 'rule34'}

async def get_embedez_link(url: str) -> str | None:
    """
    Returns an EmbedEZ embed link for the given URL, or None if not available.
    """
    api_url = "https://embedez.com/api/v1/providers/combined"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params={'q': url}, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                key = data.get('data', {}).get('key')
                if key:
                    return f"https://embedez.com/embed/{key}"
    except Exception:
        return None
    return None

async def fix_amp_links(content):
    amputator_api = 'https://www.amputatorbot.com/api/v1/convert?gac=true&md=3&q='
    # Find all URLs
    url_pattern = re.compile(r'https?://[^\s)]+')
    amp_links = set()
    for m in url_pattern.finditer(content):
        url = m.group(0)
        if 'amp' in url:
            amp_links.add(url)
    # Get canonical replacements
    replacements = {}
    async with aiohttp.ClientSession() as session:
        for link in amp_links:
            api_url = amputator_api + link
            try:
                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if 'error_message' in data:
                            continue
                        canonical_url = data[0].get('canonical', {}).get('url', link)
                        replacements[link] = canonical_url
            except Exception:
                continue
    new_content = content
    for replacement in replacements:
        new_content = new_content.replace(replacement, replacements[replacement])
    return new_content

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)
    url_pattern = re.compile(r'https?://[^\s<>()]+')
    urls = url_pattern.findall(message.content)
    if not urls:
        return
    
    new_content = message.content
    content_changed = False
    fixed_urls = {}
    embedez_url = None
    
    # Process all URLs for fixes
    for url in urls:
        for website_class in websites:
            website = website_class.if_valid(url)
            if website:
                fixed_url = await website.render()
                if fixed_url and fixed_url != url:
                    fixed_urls[url] = fixed_url
                break
    
    # Apply website fixes
    if fixed_urls:
        for original_url, fixed_url in fixed_urls.items():
            new_content = new_content.replace(original_url, fixed_url)
        content_changed = True
    
    amp_fixed_content = await fix_amp_links(new_content)
    if amp_fixed_content != new_content:
        new_content = amp_fixed_content
        content_changed = True
    
    # Get updated URLs after fixes
    updated_urls = url_pattern.findall(new_content)
    
    # Check first URL for EmbedEZ compatibility
    if updated_urls:
        first_url = updated_urls[0]
        for site in EMBEDEZ_SITES:
            if site.lower() in get_site_name(first_url).lower():
                embedez_url = await get_embedez_link(first_url)
                break
    
    # Format URLs as markdown links if they're not already formatted
    markdown_link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    existing_markdown_urls = {match.group(2) for match in markdown_link_pattern.finditer(new_content)}
    
    for i, url in enumerate(updated_urls):
        # Skip if URL is already in a markdown link
        if url in existing_markdown_urls:
            continue
            
        # Get site name from original URL if it was fixed, otherwise use current URL
        original_url = None
        for orig, fixed in fixed_urls.items():
            if fixed == url:
                original_url = orig
                break
        site_name = get_site_name(original_url or url)
        
        # Skip markdown formatting if site name is the same as the URL (no site recognized)
        if site_name == url or site_name == (original_url or url):
            continue
        
        if i == 0 and not embedez_url:
            # First URL gets normal markdown link (will show embed)
            new_content = new_content.replace(url, f'[{site_name}]({url})')
            content_changed = True
        elif i > 0 or embedez_url:
            # Other URLs get suppressed embeds
            new_content = new_content.replace(url, f'[{site_name}](<{url}>)')
            content_changed = True
    
    if content_changed:
        new_content = f'{message.author.mention}: {new_content}'
        if embedez_url:
            new_content += f"\n-# [EmbedEZ]({embedez_url})"

    if content_changed:
        # If original message was a reply, make the new message a reply too
        reference = message.reference
        await message.channel.send(new_content, reference=reference)
        try:
            await message.delete()
        except discord.Forbidden:
            await message.channel.send('I don\'t have permission to delete your message.')
        except discord.NotFound:
            pass

# Manual sync command (useful for testing) - keep as text command
@bot.command()
@commands.is_owner()
async def sync(ctx):
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} command(s)")
    except Exception as e:
        await ctx.send(f"Failed to sync: {e}")

# ============================================================================
# ENUMS AND TYPES
# ============================================================================

class RoleColorType(str, enum.Enum):
    SOLID = "solid"
    GRADIENT = "gradient"
    HOLOGRAPHIC = "holographic"

# ============================================================================
# COMMAND GROUPS
# ============================================================================

class EmojiGroup(app_commands.Group):
    """Emoji and sticker management commands"""
    
    @app_commands.command(name="copy", description="Copy custom emoji(s) from a message")
    @app_commands.describe(
        message_link="Link to the message containing the emoji", 
        which="Optional: emoji number(s) to copy (e.g. 2 or 1,3)",
        create_sticker="Create as sticker instead of emoji (default: False)"
    )
    async def copy(self, interaction: discord.Interaction, message_link: str, which: str = None, create_sticker: bool = False):
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
        import re
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
            indices = [0]  # Default to first emoji
        
        results = []
        import aiohttp
        
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
                interaction.guild, emoji_name, image_bytes, f"emoji_{emoji_name}", create_sticker
            )
            results.append(result)
            
            # Stop if we hit limit
            if "reached its" in result:
                break
        
        await interaction.response.send_message("\n".join(results), ephemeral=True)

    @app_commands.command(name="upload", description="Upload a custom emoji from an image URL")
    @app_commands.describe(
        name="Name for the new emoji/sticker", 
        url="Image URL to upload",
        create_sticker="Create as sticker instead of emoji (default: False)"
    )
    async def upload(self, interaction: discord.Interaction, name: str, url: str, create_sticker: bool = False):
        # Check permissions
        permission_check = check_emoji_permissions(interaction)
        if permission_check:
            await interaction.response.send_message(permission_check, ephemeral=True)
            return
        
        import aiohttp
        # Download image
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    await interaction.response.send_message("❌ Could not download the image. Please check the URL.", ephemeral=True)
                    return
                image_bytes = await resp.read()
        
        # Create emoji or sticker
        result = await create_emoji_or_sticker_with_overwrite(
            interaction.guild, name, image_bytes, url.split('/')[-1] or "uploaded_image", create_sticker
        )
        await interaction.response.send_message(result, ephemeral=True)

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
        which="Optional: image number to copy if there are multiple (e.g. 2)",
        create_sticker="Create as a sticker instead of an emoji (default: False)"
    )
    async def from_message(self, interaction: discord.Interaction, message_link: str, name: str, which: int = 1, create_sticker: bool = False):
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
        
        if which < 1 or which > len(all_images):
            await interaction.response.send_message(f"❌ Invalid image number. Found {len(all_images)} image(s) in the message.", ephemeral=True)
            return
        
        # Get the specified image
        image_type, image_source = all_images[which - 1]
        
        try:
            if image_type == 'attachment':
                # Check file size
                size_limit = 512 * 1024 if create_sticker else 256 * 1024
                if image_source.size > size_limit:
                    limit_name = "sticker" if create_sticker else "emoji"
                    await interaction.response.send_message(f"❌ Image is too large ({image_source.size/1024:.1f}KB). Discord {limit_name}s must be under {size_limit/1024}KB.", ephemeral=True)
                    return
                
                image_bytes = await image_source.read()
                source_name = image_source.filename
            else:  # embed image
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_source) as resp:
                        if resp.status != 200:
                            await interaction.response.send_message(f"❌ Could not download embed image.", ephemeral=True)
                            return
                        image_bytes = await resp.read()
                        source_name = "embed_image"
            
            # Create emoji or sticker
            result = await create_emoji_or_sticker_with_overwrite(
                interaction.guild, name, image_bytes, source_name, create_sticker
            )
            await interaction.response.send_message(result, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ An unexpected error occurred: {e}", ephemeral=True)


class BoosterRoleGroup(app_commands.Group):
    """Booster role customization commands"""
    
    @app_commands.command(name="color", description="Set your booster role color: solid, gradient, or holographic")
    @app_commands.describe(
        style="Color style type",
        hex="Primary color (hex code like #FF0000)",
        hex2="Secondary color for gradients (hex code like #00FF00)"
    )
    @app_commands.choices(style=[
        app_commands.Choice(name="Solid", value="solid"),
        app_commands.Choice(name="Gradient", value="gradient"),
        app_commands.Choice(name="Holographic", value="holographic")
    ])
    async def color(self, interaction: discord.Interaction, style: str = "solid", hex: str = None, hex2: str = None):
        # Check if user is a booster
        if not any(role.is_premium_subscriber() for role in interaction.user.roles):
            await interaction.response.send_message("❌ This command is only available to server boosters!", ephemeral=True)
            return
        
        # Find or create their custom role
        user_roles = [role for role in interaction.user.roles if not role.is_default()]
        if user_roles:
            highest_role = user_roles[0]
            for role in user_roles[1:]:
                if role.position > highest_role.position:
                    highest_role = role
        else:
            highest_role = None
        
        # Check if this is their personal booster role (only they have it)
        if highest_role is None or len(highest_role.members) > 1 or highest_role.is_default():
            # Create a new personal role
            try:
                highest_role = await interaction.guild.create_role(
                    name=f"{interaction.user.display_name}'s Role",
                    reason="Booster role customization"
                )
                await interaction.user.add_roles(highest_role, reason="Booster role customization")
            except discord.Forbidden:
                await interaction.response.send_message("❌ I don't have permission to create roles.", ephemeral=True)
                return
            except Exception as e:
                await interaction.response.send_message(f"❌ Error creating role: {e}", ephemeral=True)
                return
        
        # Generate color based on style and hex values
        color = None
        description = ""
        
        if style == "solid":
            if hex:
                try:
                    color = discord.Color(int(hex.replace('#', ''), 16))
                    description = f"Solid color: {hex}"
                except ValueError:
                    await interaction.response.send_message("❌ Invalid hex color format. Use format like #FF0000", ephemeral=True)
                    return
            else:
                color = discord.Color.random()
                description = f"Random solid color: #{color.value:06X}"
        
        elif style == "gradient":
            # For gradient, we'll use the primary color but mention it's a gradient
            if hex:
                try:
                    color = discord.Color(int(hex.replace('#', ''), 16))
                    description = f"Gradient color (primary): {hex}"
                    if hex2:
                        description += f" to {hex2}"
                except ValueError:
                    await interaction.response.send_message("❌ Invalid hex color format. Use format like #FF0000", ephemeral=True)
                    return
            else:
                color = discord.Color.random()
                description = f"Random gradient color: #{color.value:06X}"
        
        elif style == "holographic":
            # For holographic, we'll use a bright/iridescent color
            if hex:
                try:
                    color = discord.Color(int(hex.replace('#', ''), 16))
                    description = f"Holographic color: {hex}"
                except ValueError:
                    await interaction.response.send_message("❌ Invalid hex color format. Use format like #FF0000", ephemeral=True)
                    return
            else:
                # Use a bright, colorful default for holographic
                color = discord.Color.from_rgb(255, 0, 255)  # Bright magenta
                description = f"Holographic color: #{color.value:06X}"
        
        try:
            await highest_role.edit(color=color)
            
            embed = discord.Embed(
                title="✅ Role Color Updated!",
                description=description,
                color=color
            )
            embed.add_field(name="Style", value=style.title(), inline=True)
            embed.add_field(name="Role", value=highest_role.mention, inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to edit roles.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error updating role: {e}", ephemeral=True)

    @app_commands.command(name="label", description="Set your booster role label/name")
    @app_commands.describe(role_label="New label for your role")
    async def label(self, interaction: discord.Interaction, role_label: str):
        # Check if user is a booster
        if not any(role.is_premium_subscriber() for role in interaction.user.roles):
            await interaction.response.send_message("❌ This command is only available to server boosters!", ephemeral=True)
            return
        
        # Validate name length and content
        if len(role_title) > 100:
            await interaction.response.send_message("❌ Role title must be 100 characters or less.", ephemeral=True)
            return
        
        if not role_title.strip():
            await interaction.response.send_message("❌ Role title cannot be empty.", ephemeral=True)
            return
        
        # Find their highest role (should be their custom role)
        user_roles = [role for role in interaction.user.roles if not role.is_default()]
        if user_roles:
            highest_role = user_roles[0]
            for role in user_roles[1:]:
                if role.position > highest_role.position:
                    highest_role = role
        else:
            highest_role = None
        
        # Check if this is their personal booster role (only they have it)
        if highest_role is None or len(highest_role.members) > 1 or highest_role.is_default():
            # Create a new personal role
            try:
                highest_role = await interaction.guild.create_role(
                    name=role_title,
                    reason="Booster role customization"
                )
                await interaction.user.add_roles(highest_role, reason="Booster role customization")
                await interaction.response.send_message(f"✅ Created and assigned new role: **{role_title}**", ephemeral=True)
                return
            except discord.Forbidden:
                await interaction.response.send_message("❌ I don't have permission to create roles.", ephemeral=True)
                return
            except Exception as e:
                await interaction.response.send_message(f"❌ Error creating role: {e}", ephemeral=True)
                return
        
        # Update existing personal role
        old_name = highest_role.name
        try:
            await highest_role.edit(name=role_title, reason=f"Booster role title change by {interaction.user}")
            await interaction.response.send_message(f"✅ Role title updated from **{old_name}** to **{role_title}**!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to edit roles.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error updating role title: {e}", ephemeral=True)

    @app_commands.command(name="icon", description="Set your booster role icon")
    @app_commands.describe(icon_url="Image URL or upload an image")
    async def icon(self, interaction: discord.Interaction, icon_url: str):
        # Check if user is a booster
        if not any(role.is_premium_subscriber() for role in interaction.user.roles):
            await interaction.response.send_message("❌ This command is only available to server boosters!", ephemeral=True)
            return
        
        # Check if guild has role icons feature
        if "ROLE_ICONS" not in interaction.guild.features:
            await interaction.response.send_message("❌ This server doesn't support role icons.", ephemeral=True)
            return
        
        # Find their highest role (should be their custom role)
        user_roles = [role for role in interaction.user.roles if not role.is_default()]
        if user_roles:
            highest_role = user_roles[0]
            for role in user_roles[1:]:
                if role.position > highest_role.position:
                    highest_role = role
        else:
            highest_role = None
        
        # Check if this is their personal booster role (only they have it)
        if highest_role is None or len(highest_role.members) > 1 or highest_role.is_default():
            # Create a new personal role
            try:
                highest_role = await interaction.guild.create_role(
                    name=f"{interaction.user.display_name}'s Role",
                    reason="Booster role customization"
                )
                await interaction.user.add_roles(highest_role, reason="Booster role customization")
            except discord.Forbidden:
                await interaction.response.send_message("❌ I don't have permission to create roles.", ephemeral=True)
                return
            except Exception as e:
                await interaction.response.send_message(f"❌ Error creating role: {e}", ephemeral=True)
                return
        
        try:
            # If icon_url is an attachment, use its URL
            if hasattr(interaction, 'attachments') and interaction.attachments:
                icon_url = interaction.attachments[0].url
            
            # Download the image
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(icon_url) as resp:
                    if resp.status != 200:
                        await interaction.response.send_message("❌ Could not download the image. Please check the URL or upload a valid image.", ephemeral=True)
                        return
                    image_bytes = await resp.read()
            await highest_role.edit(icon=image_bytes)
            await interaction.response.send_message(f"✅ Role icon updated!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to edit roles.", ephemeral=True)
        except discord.HTTPException as e:
            if e.code == 50035:
                await interaction.response.send_message("❌ Invalid image format. Please use PNG, JPG, or GIF.", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Discord error: {e}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ An unexpected error occurred: {e}", ephemeral=True)


class BoosterGroup(app_commands.Group):
    """Server booster commands"""
    
    def __init__(self):
        super().__init__(name="booster", description="Server booster commands")
        self.add_command(BoosterRoleGroup(name="role", description="Booster role customization"))

# ============================================================================
# INDIVIDUAL SLASH COMMANDS  
# ============================================================================
        
# Slash command to clear all messages in the current channel
@bot.tree.command(name="clear", description="Delete all messages in this channel")
async def clear(interaction: discord.Interaction):
    # Owner check
    app_info = await interaction.client.application_info()
    if interaction.user.id != app_info.owner.id:
        await interaction.response.send_message("You must be the bot owner to use this command.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    channel = interaction.channel
    deleted = 0
    async for msg in channel.history(limit=None):
        try:
            await msg.delete()
            deleted += 1
        except Exception:
            pass
    await interaction.followup.send(f"Deleted {deleted} messages in this channel.", ephemeral=True)


class ConversionType(str, enum.Enum):
    CYPIONATE = "cypionate"
    GEL = "gel"

@bot.tree.command(name="tconvert", description="Convert between testosterone cypionate and gel")
@app_commands.describe(
    starting_type="Type of testosterone (cypionate or gel)",
    dose="Dose amount (in mg or ml)",
    frequency="Frequency of dose (in days)"
)
@app_commands.choices(starting_type=[
    app_commands.Choice(name="Cypionate", value="cypionate"),
    app_commands.Choice(name="Gel", value="gel")
])
async def tconvert(
    interaction: discord.Interaction,
    starting_type: str,
    dose: float,
    frequency: int
):
    """
    Converts between testosterone cypionate and gel doses.
    """
    daily_dose = dose / frequency
    gel_absorption = 0.1
    cyp_absorption = 0.95
    if starting_type == "gel":
        absorption = daily_dose * gel_absorption
        weekly = absorption * 7
        final = weekly / cyp_absorption
        response = f"{dose}mg gel every {frequency} days is approximately {final:.2f}mg cypionate weekly."
    elif starting_type == "cypionate":
        absorption = daily_dose * cyp_absorption
        final = absorption / gel_absorption
        response = f"{dose}mg cypionate every {frequency} days is approximately {final:.2f}mg gel daily."
    else:
        response = "❌ Invalid conversion type."
    await interaction.response.send_message(response)

class TimestampStyle(str, enum.Enum):
    SHORT_TIME = "t"          # 16:20
    LONG_TIME = "T"           # 16:20:30
    SHORT_DATE = "d"          # 20/04/2021
    LONG_DATE = "D"           # 20 April 2021
    SHORT_DATETIME = "f"      # 20 April 2021 16:20
    LONG_DATETIME = "F"       # Tuesday, 20 April 2021 16:20
    RELATIVE = "R"            # 2 months ago

@bot.tree.command(name="timestamp", description="Generate a Discord timestamp")
@app_commands.describe(
    date="Date in YYYY-MM-DD format (optional, defaults to today)",
    time="Time in 24hr (13:00) or 12hr (1 PM, 1:00 PM) format (optional, defaults to current time)",
    style="Display style for the timestamp",
    timezone_offset="Hours behind UTC for the input time (e.g. -6 for CST, -4 for EDT, 1 for CET)"
)
async def timestamp(
    interaction: discord.Interaction,
    date: str = None,
    time: str = None,
    style: TimestampStyle = None,
    timezone_offset: int = 0
):
    """
    Creates a Discord timestamp that shows relative time and adapts to user's timezone.
    """
    import datetime as dt
    
    try:
        now = dt.datetime.now()
        
        # Parse date (use today if not provided)
        if date:
            try:
                parsed_date = dt.datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                await interaction.response.send_message("❌ Invalid date format. Use 'YYYY-MM-DD'", ephemeral=True)
                return
        else:
            parsed_date = now.date()
        
        # Parse time (use current time if not provided)
        if time:
            try:
                # Clean up the input - remove extra spaces and make case-insensitive
                time_clean = time.strip().upper()
                
                # Try different time formats
                parsed_time = None
                time_formats = [
                    "%H:%M:%S",      # 13:00:30 (24-hour with seconds)
                    "%H:%M",         # 13:00 (24-hour)
                    "%I:%M:%S %p",   # 1:00:30 PM (12-hour with seconds)
                    "%I:%M %p",      # 1:00 PM (12-hour)
                    "%I %p",         # 1 PM (12-hour, no minutes)
                ]
                
                for fmt in time_formats:
                    try:
                        parsed_time = dt.datetime.strptime(time_clean, fmt).time()
                        break
                    except ValueError:
                        continue
                
                if parsed_time is None:
                    await interaction.response.send_message(
                        "❌ Invalid time format. Supported formats:\n"
                        "• 24-hour: `13:00`, `13:00:30`\n"
                        "• 12-hour: `1 PM`, `1:00 PM`, `1:00:30 PM`", 
                        ephemeral=True
                    )
                    return
                    
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid time format. Supported formats:\n"
                    "• 24-hour: `13:00`, `13:00:30`\n"
                    "• 12-hour: `1 PM`, `1:00 PM`, `1:00:30 PM`", 
                    ephemeral=True
                )
                return
        else:
            parsed_time = now.time()
        
        # Combine date and time
        combined_datetime = dt.datetime.combine(parsed_date, parsed_time)
        
        # Apply timezone offset to convert to UTC
        # timezone_offset represents hours behind UTC, so we SUBTRACT it to get UTC time
        # For example: 7 PM in UTC-6 becomes 7 PM - (-6) = 7 PM + 6 hours = 1 AM UTC (next day)
        combined_datetime_utc = combined_datetime - dt.timedelta(hours=timezone_offset)
        
        # Convert to Unix timestamp using UTC timezone explicitly
        # This ensures Python treats our datetime as UTC, not local time
        utc_with_timezone = combined_datetime_utc.replace(tzinfo=dt.timezone.utc)
        unix_timestamp = int(utc_with_timezone.timestamp())
        
        # Create response with examples of all formats
        all_formats = [
            f"**Short Time (t)**: `<t:{unix_timestamp}:t>` <t:{unix_timestamp}:t>",
            f"**Long Time (T)**: `<t:{unix_timestamp}:T>` <t:{unix_timestamp}:T>",
            f"**Short Date (d)**: `<t:{unix_timestamp}:d>` <t:{unix_timestamp}:d>",
            f"**Long Date (D)**: `<t:{unix_timestamp}:D>` <t:{unix_timestamp}:D>",
            f"**Short DateTime (f)**: `<t:{unix_timestamp}:f>` <t:{unix_timestamp}:f>",
            f"**Long DateTime (F)**: `<t:{unix_timestamp}:F>` <t:{unix_timestamp}:F>",
            f"**Relative (R)**: `<t:{unix_timestamp}:R>` <t:{unix_timestamp}:R>"
        ]
        
        input_info = f"**Input:** {parsed_date} {parsed_time.strftime('%H:%M:%S')}"
        if timezone_offset != 0:
            input_info += f" (UTC{timezone_offset:+d})"
            input_info += f"\n**Converted to UTC:** {combined_datetime_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        
        response = f"{input_info}\n"
        response += f"**Unix timestamp:** {unix_timestamp}\n"
        if style is not None:
            # Generate Discord timestamp
            discord_timestamp = f"<t:{unix_timestamp}:{style.value}>"
            response += f"**Your timestamp:** `{discord_timestamp}`\n"
            response += f"**Preview:** {discord_timestamp}\n\n"
        else:
            response += "**All format examples:**\n" + "\n".join(all_formats)
        
        await interaction.response.send_message(response)
        
    except ValueError as e:
        await interaction.response.send_message(f"❌ Error parsing input: {e}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)

bot.run(os.getenv("DISCORD_TOKEN"))