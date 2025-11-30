import enum
import aiohttp
import datetime
import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import re
import asyncio
from dotenv import load_dotenv
from typing import Literal
from websites import websites, get_site_name
from database import db

# Load environment variables from .env file
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# In-memory settings: {guild_id: include_original_message}
settings = {}

# No need for tracking storage - we'll just check the original message!

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

async def create_emoji_or_sticker_with_overwrite(guild, name: str, image_bytes: bytes, source_name: str = "image", create_sticker: bool = False, replace_existing: bool = True) -> str:
    """Create emoji or sticker, with option to replace or create with different name. Returns result message."""
    import io
    
    if create_sticker:
        # Handle sticker creation
        existing_sticker = discord.utils.get(guild.stickers, name=name)
        if existing_sticker and not replace_existing:
            # Find a unique name
            counter = 1
            new_name = f"{name}_{counter}"
            while discord.utils.get(guild.stickers, name=new_name):
                counter += 1
                new_name = f"{name}_{counter}"
            name = new_name
            existing_sticker = None  # Reset since we're using a different name
        elif existing_sticker and replace_existing:
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
            if existing_sticker and replace_existing:
                action = "replaced"
            elif not replace_existing and "_" in name:
                action = f"created as '{name}' (original name existed)"
            else:
                action = "created"
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
        if existing_emoji and not replace_existing:
            # Find a unique name
            counter = 1
            new_name = f"{name}_{counter}"
            while discord.utils.get(guild.emojis, name=new_name):
                counter += 1
                new_name = f"{name}_{counter}"
            name = new_name
            existing_emoji = None  # Reset since we're using a different name
        elif existing_emoji and replace_existing:
            try:
                await existing_emoji.delete(reason="Overwriting with new emoji")
            except Exception:
                pass
        
        try:
            new_emoji = await guild.create_custom_emoji(name=name, image=image_bytes)
            if existing_emoji and replace_existing:
                action = "replaced"
            elif not replace_existing and "_" in name:
                action = f"created as '{name}' (original name existed)"
            else:
                action = "created"
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
    
    # Initialize database connection pool
    try:
        db.init_pool()
        # Test the connection with a simple query
        result = db.execute_query("SELECT 1")
        print(f"✅ Database connected successfully")
    except Exception as e:
        print(f"⚠️  Database initialization failed: {e}")
        print("   Reply notifications will not work until database is configured")
    
    # Add command groups to the tree
    bot.tree.add_command(EmojiGroup(name="emoji", description="Emoji and sticker management commands"))
    bot.tree.add_command(BoosterGroup())
    bot.tree.add_command(SettingsGroup(name="settings", description="User settings and preferences"))
    
    try:
        # Sync slash commands
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    # Start daily booster role check task
    bot.loop.create_task(daily_booster_role_check())
    
# List of sites that support EmbedEZ (Instagram handled separately)
EMBEDEZ_SITES = {'snapchat', 'ifunny', 'weibo', 'rule34'}

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

def is_url_in_code_block(content, url):
    """Check if a URL is inside a code block (single or triple backticks)"""
    url_start = content.find(url)
    if url_start == -1:
        return False
    
    # Check for triple backtick code blocks first
    triple_blocks = []
    i = 0
    while i < len(content):
        start = content.find('```', i)
        if start == -1:
            break
        end = content.find('```', start + 3)
        if end == -1:
            break
        triple_blocks.append((start, end + 3))
        i = end + 3
    
    # Check if URL is in any triple backtick block
    for start, end in triple_blocks:
        if start <= url_start < end:
            return True
    
    # Check for single backtick code blocks (inline code)
    # Remove triple backtick blocks temporarily to avoid conflicts
    temp_content = content
    for start, end in reversed(triple_blocks):
        temp_content = temp_content[:start] + ' ' * (end - start) + temp_content[end:]
    
    # Adjust URL position for the temporary content
    temp_url_start = temp_content.find(url)
    if temp_url_start == -1:
        return False
    
    # Find all single backtick pairs
    backticks = []
    for i, char in enumerate(temp_content):
        if char == '`':
            backticks.append(i)
    
    # Check if URL is between any pair of backticks
    for i in range(0, len(backticks) - 1, 2):
        if i + 1 < len(backticks):
            start, end = backticks[i], backticks[i + 1]
            if start <= temp_url_start < end:
                return True
    
    return False

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)
    
    # Handle replies to bot's messages - ping the original poster if they have notifications enabled
    if message.reference:
        try:
            # Get the message being replied to
            replied_message = await message.channel.fetch_message(message.reference.message_id)
            
            # Check if it's a message from the bot
            if replied_message.author == bot.user:
                # Check if the bot's message is just a reply ping notification
                # Reply ping messages start with "-# " and contain only a mention
                bot_message_content = replied_message.content.strip()
                if bot_message_content.startswith('-# ') and bot_message_content.count('<@') == 1 and bot_message_content.count('>') == 1:
                    # This is just a reply ping message, don't create another ping
                    pass
                else:
                    # Look up the original user from message tracking
                    user_data = db.get_message_original_user(replied_message.id)
                    original_user_id = None
                    guild_id = message.guild.id if message.guild else None
                    
                    if user_data:
                        # Found in tracking database
                        original_user_id, guild_id = user_data
                    else:
                        # Not in database (old message) - parse the mention from the bot's message
                        # Bot messages start with "<@user_id>: ..." format
                        import re
                        mention_match = re.match(r'^<@!?(\d+)>:', replied_message.content)
                        if mention_match:
                            original_user_id = int(mention_match.group(1))
                    
                    # If we found an original user, check if they want notifications
                    if original_user_id and guild_id:
                        # Don't ping if the replier is the original poster
                        if message.author.id != original_user_id:
                            # Check if user has reply notifications enabled
                            notifications_enabled = db.get_user_reply_notifications(original_user_id, guild_id)
                            
                            if notifications_enabled:
                                # Send a subtle ping message
                                ping_message = f"-# <@{original_user_id}>"
                                await message.channel.send(ping_message, reference=message, mention_author=False)
        except Exception as e:
            # Silently fail to avoid spam (message might be deleted, db error, etc.)
            print(f"Error handling reply notification: {e}")
    
    # Continue with URL processing
    url_pattern = re.compile(r'https?://[^\s<>()]+')
    urls = url_pattern.findall(message.content)
    
    # Filter out URLs that are in code blocks
    urls = [url for url in urls if not is_url_in_code_block(message.content, url)]
    
    if not urls:
        return
    
    new_content = message.content
    content_changed = False
    fixed_urls = {}
    embedez_url = None
    instagram_embed_url = None
    
    # Process all URLs for fixes
    for url in urls:
        for website_class in websites:
            website = website_class.if_valid(url)
            if website:
                # Check if this is Instagram and get embed URL
                if website.__class__.__name__ == 'InstagramLink' and hasattr(website, 'get_embed_url'):
                    instagram_embed_url = website.get_embed_url()
                
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
        
        # Check if this URL should have suppressed embed (EmbedEZ only, not Instagram)
        should_suppress = embedez_url is not None
        
        if i == 0 and not should_suppress:
            # First URL gets normal markdown link (will show embed)
            new_content = new_content.replace(url, f'[{site_name}]({url})')
            content_changed = True
        else:
            # Other URLs or URLs with separate embeds get suppressed embeds
            new_content = new_content.replace(url, f'[{site_name}](<{url}>)')
            content_changed = True
    
    if content_changed:
        new_content = f'{message.author.mention}: {new_content}'
        if embedez_url:
            new_content += f"\n-# [EmbedEZ]({embedez_url})"
        if instagram_embed_url:
            new_content += f"\n-# [Embed]({instagram_embed_url})"

    if content_changed:
        # If original message was a reply, make the new message a reply too
        reference = message.reference
        sent_message = await message.channel.send(new_content, reference=reference)
        
        # Store message tracking for reply notifications
        if sent_message and message.guild:
            # Get the first fixed URL for tracking
            original_url = urls[0] if urls else None
            fixed_url = list(fixed_urls.values())[0] if fixed_urls else None
            
            try:
                db.store_message_tracking(
                    bot_message_id=sent_message.id,
                    user_id=message.author.id,
                    guild_id=message.guild.id,
                    original_url=original_url,
                    fixed_url=fixed_url
                )
                print(f"✓ Stored message tracking: bot_msg={sent_message.id}, user={message.author.id}")
            except Exception as e:
                print(f"✗ Failed to store message tracking: {e}")
                import traceback
                traceback.print_exc()
        
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
            indices = list(range(len(emoji_matches)))  # Default to all emojis
        
        results = []
        import aiohttp
        
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
        
        import aiohttp
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
                    import aiohttp
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
        import aiohttp
        
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
        if len(role_label) > 100:
            await interaction.response.send_message("❌ Role label must be 100 characters or less.", ephemeral=True)
            return
        
        if not role_label.strip():
            await interaction.response.send_message("❌ Role label cannot be empty.", ephemeral=True)
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
                    name=role_label,
                    reason="Booster role customization"
                )
                await interaction.user.add_roles(highest_role, reason="Booster role customization")
                await interaction.response.send_message(f"✅ Created and assigned new role: **{role_label}**", ephemeral=True)
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
            await highest_role.edit(name=role_label, reason=f"Booster role label change by {interaction.user}")
            await interaction.response.send_message(f"✅ Role label updated from **{old_name}** to **{role_label}**!", ephemeral=True)
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

@bot.tree.command(name="purge", description="Delete messages from a specific user within a date/time range")
@app_commands.describe(
    user="The user whose messages to delete",
    scope="What to delete - REQUIRED to prevent accidents",
    start_date="[CUSTOM ONLY] Start date (YYYY-MM-DD) - delete messages AFTER this date/time",
    start_time="[CUSTOM ONLY] Start time (HH:MM, 24-hour format, defaults to 00:00)",
    end_date="[CUSTOM ONLY] End date (YYYY-MM-DD) - delete messages BEFORE this date/time",
    end_time="[CUSTOM ONLY] End time (HH:MM, 24-hour format, defaults to 23:59)", 
    timezone_offset="[CUSTOM ONLY] Hours from UTC (e.g. -5 for EST, -8 for PST, 1 for CET)",
    all_channels="Delete from all channels (default: False, only current channel)",
    dry_run="Show what would be deleted without actually deleting (default: True)"
)
@app_commands.choices(scope=[
    app_commands.Choice(name="All messages (DANGER)", value="all"),
    app_commands.Choice(name="Custom date/time range", value="custom")
])
async def purge_messages(
    interaction: discord.Interaction,
    user: discord.Member,
    scope: str,
    start_date: str = None,
    start_time: str = "00:00",
    end_date: str = None,
    end_time: str = "23:59",
    timezone_offset: int = 0,
    all_channels: bool = False,
    dry_run: bool = True
):
    """
    Delete messages from a specific user within a date/time range.
    Only works if you're deleting your own messages or have manage_messages permission.
    """
    import datetime as dt
    
    # Permission check
    is_self = interaction.user.id == user.id
    has_manage_messages = interaction.user.guild_permissions.manage_messages
    
    if not (is_self or has_manage_messages):
        await interaction.response.send_message(
            "❌ You can only delete your own messages or need 'Manage Messages' permission to delete others' messages.",
            ephemeral=True
        )
        return
    
    # Parse date/time range based on scope
    start_datetime = None
    end_datetime = None
    
    if scope == 'all':
        # No date filtering - will delete all messages from the user
        pass
    elif scope == 'custom':
        # Custom date range - require at least start_date OR end_date
        if not start_date and not end_date:
            await interaction.response.send_message(
                "❌ Custom scope requires at least `start_date` or `end_date` parameter:\n"
                "• Only `start_date`: Delete all messages after this date/time\n"
                "• Only `end_date`: Delete all messages before this date/time\n"
                "• Both: Delete messages between these dates",
                ephemeral=True
            )
            return
        
        try:
            # Parse start date if provided
            if start_date:
                start_date_parsed = dt.datetime.strptime(start_date, "%Y-%m-%d").date()
                
                # Parse and validate start_time
                if ':' not in start_time:
                    await interaction.response.send_message(
                        "❌ Time format must be HH:MM (24-hour format)",
                        ephemeral=True
                    )
                    return
                    
                start_hour, start_minute = map(int, start_time.split(':'))
                
                # Validate time range
                if not (0 <= start_hour <= 23 and 0 <= start_minute <= 59):
                    await interaction.response.send_message(
                        "❌ Invalid start_time. Use HH:MM format (00:00 to 23:59)",
                        ephemeral=True
                    )
                    return
                
                # Create start datetime in user's timezone, then convert to UTC
                start_datetime = dt.datetime.combine(start_date_parsed, dt.time(start_hour, start_minute))
                start_datetime = start_datetime + dt.timedelta(hours=timezone_offset)
                start_datetime = start_datetime.replace(tzinfo=dt.timezone.utc)
            
            # Parse end date if provided
            if end_date:
                end_date_parsed = dt.datetime.strptime(end_date, "%Y-%m-%d").date()
                
                # Parse and validate end_time
                if ':' not in end_time:
                    await interaction.response.send_message(
                        "❌ Time format must be HH:MM (24-hour format)",
                        ephemeral=True
                    )
                    return
                    
                end_hour, end_minute = map(int, end_time.split(':'))
                
                # Validate time range
                if not (0 <= end_hour <= 23 and 0 <= end_minute <= 59):
                    await interaction.response.send_message(
                        "❌ Invalid end_time. Use HH:MM format (00:00 to 23:59)",
                        ephemeral=True
                    )
                    return
                
                # Create end datetime in user's timezone, then convert to UTC
                end_datetime = dt.datetime.combine(end_date_parsed, dt.time(end_hour, end_minute))
                end_datetime = end_datetime + dt.timedelta(hours=timezone_offset)
                end_datetime = end_datetime.replace(tzinfo=dt.timezone.utc)
            
            # Validate datetime order if both are provided
            if start_datetime and end_datetime and start_datetime > end_datetime:
                await interaction.response.send_message(
                    "❌ Start date/time cannot be after end date/time",
                    ephemeral=True
                )
                return
            
        except ValueError as e:
            await interaction.response.send_message(
                "❌ Invalid date/time format. Use YYYY-MM-DD for dates and HH:MM for times (24-hour format)",
                ephemeral=True
            )
            return
    
    # Defer response since this might take a while
    await interaction.response.defer(ephemeral=True)
    
    # Determine channels to process
    channels_to_process = []
    if all_channels:
        # Get all text channels the bot can see
        channels_to_process = [ch for ch in interaction.guild.text_channels if ch.permissions_for(interaction.guild.me).read_message_history]
    else:
        # Just the current channel
        if interaction.channel.permissions_for(interaction.guild.me).read_message_history:
            channels_to_process = [interaction.channel]
        else:
            await interaction.followup.send("❌ I don't have permission to read message history in this channel.", ephemeral=True)
            return
    
    # Collect messages to delete
    messages_to_delete = []
    total_scanned = 0
    
    try:
        for channel in channels_to_process:
            async for message in channel.history(limit=None):
                total_scanned += 1
                
                # Check if message is from the target user
                if message.author.id != user.id:
                    continue
                
                # Check date range if specified
                if start_datetime and end_datetime:
                    # Both dates specified: between range
                    if not (start_datetime <= message.created_at <= end_datetime):
                        continue
                elif start_datetime:
                    # Only start date: after this date
                    if message.created_at < start_datetime:
                        continue
                elif end_datetime:
                    # Only end date: before this date
                    if message.created_at > end_datetime:
                        continue
                
                messages_to_delete.append(message)
                
                # Safety limit to prevent excessive processing
                if len(messages_to_delete) >= 1000:
                    break
            
            if len(messages_to_delete) >= 1000:
                break
    
    except Exception as e:
        await interaction.followup.send(f"❌ Error scanning messages: {e}", ephemeral=True)
        return
    
    if not messages_to_delete:
        await interaction.followup.send(
            f"No messages found from {user.mention} in the specified criteria.\n"
            f"Scanned {total_scanned} messages across {len(channels_to_process)} channel(s).",
            ephemeral=True
        )
        return
    
    # Show summary
    channel_summary = "all channels" if all_channels else f"#{interaction.channel.name}"
    
    # Create date summary based on scope
    if scope == 'all':
        date_summary = "from all time"
    elif scope in ['today', 'yesterday', 'last_7_days', 'last_30_days']:
        date_summary = f"scope: {scope.replace('_', ' ')}"
    elif scope == 'custom':
        # Convert back to user's timezone for display
        if start_datetime and end_datetime:
            user_start = start_datetime - dt.timedelta(hours=timezone_offset)
            user_end = end_datetime - dt.timedelta(hours=timezone_offset)
            date_summary = f"from {user_start.strftime('%Y-%m-%d %H:%M')} to {user_end.strftime('%Y-%m-%d %H:%M')} (UTC{timezone_offset:+d})"
        elif start_datetime:
            user_start = start_datetime - dt.timedelta(hours=timezone_offset)
            date_summary = f"after {user_start.strftime('%Y-%m-%d %H:%M')} (UTC{timezone_offset:+d})"
        elif end_datetime:
            user_end = end_datetime - dt.timedelta(hours=timezone_offset)
            date_summary = f"before {user_end.strftime('%Y-%m-%d %H:%M')} (UTC{timezone_offset:+d})"
    else:
        date_summary = f"scope: {scope}"
    
    summary_message = (
        f"**{'DRY RUN - ' if dry_run else ''}Purge Summary**\n"
        f"👤 User: {user.mention}\n"
        f"📅 Date range: {date_summary}\n"
        f"📍 Location: {channel_summary}\n"
        f"🗑️ Messages to delete: {len(messages_to_delete)}\n"
        f"🔍 Total messages scanned: {total_scanned}"
    )
    
    if dry_run:
        summary_message += "\n\n✅ This was a dry run - no messages were actually deleted."
        await interaction.followup.send(summary_message, ephemeral=True)
        return
    
    # Confirm before deletion for large batches
    if len(messages_to_delete) > 50:
        summary_message += f"\n\n⚠️ **Warning:** This will delete {len(messages_to_delete)} messages. This action cannot be undone!"
        await interaction.followup.send(summary_message, ephemeral=True)
        
        # For large deletions, require manual confirmation (you could implement a button here)
        if len(messages_to_delete) > 100:
            await interaction.followup.send(
                f"❌ Deletion of {len(messages_to_delete)} messages requires manual confirmation. "
                "Please run this command again with `dry_run: True` first to verify, or contact an administrator.",
                ephemeral=True
            )
            return
    
    # Delete messages
    deleted_count = 0
    failed_count = 0
    
    for message in messages_to_delete:
        try:
            await message.delete()
            deleted_count += 1
        except discord.NotFound:
            # Message already deleted
            deleted_count += 1
        except discord.Forbidden:
            failed_count += 1
        except Exception:
            failed_count += 1
        
        # Rate limit protection
        if deleted_count % 10 == 0:
            await asyncio.sleep(0.5)
    
    # Final report
    result_message = (
        f"✅ **Purge Complete**\n"
        f"👤 User: {user.mention}\n"
        f"📅 Date range: {date_summary}\n"
        f"📍 Location: {channel_summary}\n"
        f"✅ Successfully deleted: {deleted_count}\n"
        f"❌ Failed to delete: {failed_count}"
    )
    
    if failed_count > 0:
        result_message += "\n\n⚠️ Some messages couldn't be deleted (too old, already deleted, or permission issues)."
    
    await interaction.followup.send(result_message, ephemeral=True)

# Autocomplete functions for purge command to provide conditional guidance
@purge_messages.autocomplete('start_date')
async def start_date_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    # Only show suggestions if scope is custom
    if hasattr(interaction.namespace, 'scope') and interaction.namespace.scope == 'custom':
        suggestions = [
            app_commands.Choice(name="Today (2025-09-26)", value="2025-09-26"),
            app_commands.Choice(name="Yesterday (2025-09-25)", value="2025-09-25"),
            app_commands.Choice(name="One week ago (2025-09-19)", value="2025-09-19"),
            app_commands.Choice(name="One month ago (2025-08-26)", value="2025-08-26")
        ]
        return [choice for choice in suggestions if current.lower() in choice.name.lower()]
    return [app_commands.Choice(name="Set scope to 'Custom date/time range' first", value="")]

@purge_messages.autocomplete('end_date')
async def end_date_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    # Only show suggestions if scope is custom
    if hasattr(interaction.namespace, 'scope') and interaction.namespace.scope == 'custom':
        suggestions = [
            app_commands.Choice(name="Today (2025-09-26)", value="2025-09-26"),
            app_commands.Choice(name="Yesterday (2025-09-25)", value="2025-09-25"),
            app_commands.Choice(name="One week ago (2025-09-19)", value="2025-09-19"),
            app_commands.Choice(name="One month ago (2025-08-26)", value="2025-08-26")
        ]
        return [choice for choice in suggestions if current.lower() in choice.name.lower()]
    return [app_commands.Choice(name="Set scope to 'Custom date/time range' first", value="")]

@purge_messages.autocomplete('timezone_offset')
async def timezone_offset_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    # Only show suggestions if scope is custom
    if hasattr(interaction.namespace, 'scope') and interaction.namespace.scope == 'custom':
        suggestions = [
            app_commands.Choice(name="EST/EDT (UTC-5/-4)", value="-5"),
            app_commands.Choice(name="CST/CDT (UTC-6/-5)", value="-6"),
            app_commands.Choice(name="MST/MDT (UTC-7/-6)", value="-7"),
            app_commands.Choice(name="PST/PDT (UTC-8/-7)", value="-8"),
            app_commands.Choice(name="UTC (UTC+0)", value="0"),
            app_commands.Choice(name="CET/CEST (UTC+1/+2)", value="1")
        ]
        return [choice for choice in suggestions if current in choice.name or current in choice.value]
    return [app_commands.Choice(name="Set scope to 'Custom date/time range' first", value="0")]

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

# ============================================================================
# SETTINGS COMMAND GROUP
# ============================================================================

class SettingsGroup(app_commands.Group):
    """User settings and preferences"""
    
    @app_commands.command(name="notify", description="Toggle reply notifications when someone replies to your fixed links")
    @app_commands.describe(enabled="Enable or disable reply notifications")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable notifications", value=1),
        app_commands.Choice(name="Disable notifications", value=0)
    ])
    async def notify(self, interaction: discord.Interaction, enabled: int):
        """Toggle reply notification preferences"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Update user preference
            db.set_user_reply_notifications(
                user_id=interaction.user.id,
                guild_id=interaction.guild.id,
                enabled=bool(enabled)
            )
            
            status = "**enabled** ✅" if enabled else "**disabled** 🔕"
            await interaction.response.send_message(
                f"Reply notifications {status}\n"
                f"You will {'now' if enabled else 'no longer'} be pinged when someone replies to messages "
                f"where the bot fixed your links.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error updating notification preference: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating your notification preference. Please try again later.",
                ephemeral=True
            )

bot.run(os.getenv("DISCORD_TOKEN"))