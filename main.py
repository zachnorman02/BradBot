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
    
class RoleColorType(str, enum.Enum):
    SOLID = "solid"
    GRADIENT = "gradient"
    HOLOGRAPHIC = "holographic"

# Slash command for server boosters to set their personal role color
@bot.tree.command(name="boostercolor", description="Set your booster role color: solid, gradient, or holographic")
@app_commands.describe(hex="Hex color code (e.g. #FF5733)", style="Color style: solid, gradient, or holographic", hex2="Second hex code for gradient (optional)")
async def boostercolor(interaction: discord.Interaction, style: RoleColorType = RoleColorType.SOLID, hex: str = None, hex2: str = None):
    guild = interaction.guild
    member = interaction.user if hasattr(interaction, 'user') else interaction.author
    booster_role = discord.utils.get(guild.roles, is_premium_subscriber=True)
    app_info = await interaction.client.application_info()
    is_owner = interaction.user.id == app_info.owner.id
    if not (booster_role and booster_role in member.roles) and not is_owner:
        await interaction.response.send_message("You must be a server booster or the bot owner to use this command.", ephemeral=True)
        return
    # Validate hex codes and style
    if style == RoleColorType.HOLOGRAPHIC:
        color = discord.Color(11127295)
        secondary_color = discord.Color(16759788)
        tertiary_color = discord.Color(16761760)
    elif style == RoleColorType.SOLID:
        if not hex:
            await interaction.response.send_message("Hex color is required for solid style.", ephemeral=True)
            return
        if not re.fullmatch(r'#?[0-9A-Fa-f]{6}', hex):
            await interaction.response.send_message("Invalid hex code. Please use format #RRGGBB.", ephemeral=True)
            return
        color_value = int(hex.lstrip('#'), 16)
        color = discord.Color(color_value)
        secondary_color = None
    elif style == RoleColorType.GRADIENT:
        if not hex or not hex2:
            await interaction.response.send_message("Both hex and hex2 are required for gradient style.", ephemeral=True)
            return
        if not (re.fullmatch(r'#?[0-9A-Fa-f]{6}', hex) and re.fullmatch(r'#?[0-9A-Fa-f]{6}', hex2)):
            await interaction.response.send_message("For gradient, provide two hex codes in format #RRGGBB.", ephemeral=True)
            return
        color = discord.Color(int(hex.lstrip('#'), 16))
        secondary_color = discord.Color(int(hex2.lstrip('#'), 16))
    else:
        await interaction.response.send_message("Style must be 'solid', 'gradient', or 'holographic'.", ephemeral=True)
        return
    # Find highest ranking role (excluding @everyone and booster role)
    personal_roles = [role for role in member.roles if role != booster_role and not role.is_default()]
    try:
        if personal_roles:
            highest_role = sorted(personal_roles, key=lambda r: r.position, reverse=True)[0]
            if len(highest_role.members) == 1:
                try:
                    if style == "solid":
                        await highest_role.edit(colour=color)
                        await interaction.response.send_message(f"Updated your highest role '{highest_role.name}' color to {hex.upper()}!", ephemeral=True)
                    elif style == "gradient":
                        await highest_role.edit(colour=color, secondary_colour=secondary_color)
                        await interaction.response.send_message(f"Updated your highest role '{highest_role.name}' to a gradient color from {hex.upper()} to {hex2.upper()}!", ephemeral=True)
                    elif style == "holographic":
                        await highest_role.edit(
                            colour=color,
                            secondary_colour=secondary_color,
                            tertiary_colour=tertiary_color
                        )
                        await interaction.response.send_message(f"Updated your highest role '{highest_role.name}' to holographic!", ephemeral=True)
                    return
                except discord.HTTPException as e:
                    if e.code == 30039:
                        await interaction.response.send_message("❌ This server does not have enough boosts for gradient or holographic role colors.", ephemeral=True)
                        return
                    else:
                        raise
                    
        new_role = await guild.create_role(name=member.display_name, mentionable=False)
        await asyncio.sleep(1)  # Short delay to ensure Discord registers the new role
        # Place new role above the booster role
        target_position = None
        if booster_role:
            # Place above user's highest role
            personal_roles_sorted = sorted([role for role in member.roles if not role.is_default()], key=lambda r: r.position, reverse=True)
            highest_role = personal_roles_sorted[0] if personal_roles_sorted else None
            if highest_role:
                target_position = highest_role.position + 1
            else:
                target_position = 1
        move_success = True
        try:
            await new_role.edit(position=target_position)
        except Exception:
            move_success = False
        await member.add_roles(new_role)
        try:
            if style == "solid":
                await new_role.edit(colour=color)
                msg = f"Created a new personal role and set its color to {hex.upper()}! "
            elif style == "gradient":
                await new_role.edit(colour=color, secondary_colour=secondary_color)
                msg = f"Created a new personal role and set its gradient color from {hex.upper()} to {hex2.upper()}! "
            elif style == "holographic":
                await new_role.edit(
                    colour=color,
                    secondary_colour=secondary_color,
                    tertiary_colour=tertiary_color
                )
                msg = f"Created a new personal role and set its color to holographic! "
            else:
                msg = "Created a new personal role! "
        except discord.HTTPException as e:
            if e.code == 30039:
                msg = "❌ This server does not have enough boosts for gradient or holographic role colors."
            else:
                raise
        msg += "(Role moved as high as possible)" if move_success else "(Role could not be moved to the top; check bot permissions)"
        await interaction.response.send_message(msg, ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don't have permission to manage roles or change role colors. Please check my permissions and role position.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ An unexpected error occurred: {e}", ephemeral=True)
    
# Slash command for server boosters to rename their personal role
@bot.tree.command(name="boostername", description="Set your booster role name (custom role)")
@app_commands.describe(name="New role name")
async def boostername(interaction: discord.Interaction, name: str):
    guild = interaction.guild
    member = interaction.user if hasattr(interaction, 'user') else interaction.author
    booster_role = discord.utils.get(guild.roles, is_premium_subscriber=True)
    app_info = await interaction.client.application_info()
    is_owner = interaction.user.id == app_info.owner.id
    if not (booster_role and booster_role in member.roles) and not is_owner:
        await interaction.response.send_message("You must be a server booster or the bot owner to use this command.", ephemeral=True)
        return
    # Find highest personal role (only assigned to this user)
    personal_roles = [role for role in member.roles if role != booster_role and not role.is_default() and len(role.members) == 1]
    try:
        if personal_roles:
            highest_role = sorted(personal_roles, key=lambda r: r.position, reverse=True)[0]
            await highest_role.edit(name=name)
            await interaction.response.send_message(f"Renamed your highest personal role to '{name}'!", ephemeral=True)
            return
        # If no personal role, create a new role
        bot_member = guild.me
        bot_top_role = sorted(bot_member.roles, key=lambda r: r.position, reverse=True)[0]
        new_role = await guild.create_role(name=name, mentionable=False)
        await asyncio.sleep(1)  # Short delay to ensure Discord registers the new role
        # Determine target position for new role
        personal_roles_sorted = sorted([role for role in member.roles if not role.is_default()], key=lambda r: r.position, reverse=True)
        highest_role = personal_roles_sorted[0] if personal_roles_sorted else None
        if highest_role:
            target_position = highest_role.position + 1
        else:
            target_position = 1
        move_success = True
        try:
            await new_role.edit(position=target_position)
        except Exception:
            move_success = False
        await member.add_roles(new_role)
        msg = f"Created a new personal role and set its name to '{name}'! "
        msg += "(Role moved as high as possible)" if move_success else "(Role could not be moved to the top; check bot permissions)"
        await interaction.response.send_message(msg, ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don't have permission to manage roles or rename roles. Please check my permissions and role position.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ An unexpected error occurred: {e}", ephemeral=True)

# Slash command for server boosters to set their personal role icon
@bot.tree.command(name="boostericon", description="Set your booster role icon (custom role icon)")
@app_commands.describe(icon_url="Image URL or upload an image")
async def boostericon(interaction: discord.Interaction, icon_url: str):
    guild = interaction.guild
    member = interaction.user if hasattr(interaction, 'user') else interaction.author
    booster_role = discord.utils.get(guild.roles, premium_subscriber=True)
    app_info = await interaction.client.application_info()
    is_owner = interaction.user.id == app_info.owner.id
    if not (booster_role and booster_role in member.roles) and not is_owner:
        await interaction.response.send_message("You must be a server booster or the bot owner to use this command.", ephemeral=True)
        return
    # Find highest personal role (only assigned to this user)
    personal_roles = [role for role in member.roles if role != booster_role and not role.is_default() and len(role.members) == 1]
    if personal_roles:
        highest_role = sorted(personal_roles, key=lambda r: r.position, reverse=True)[0]
    else:    
        bot_member = guild.me
        bot_top_role = sorted(bot_member.roles, key=lambda r: r.position, reverse=True)[0]
        highest_role = await guild.create_role(name=member.display_name, mentionable=False)
        await asyncio.sleep(1)
        try:
            await highest_role.edit(position=bot_top_role.position - 1)
        except Exception:
            pass
        await member.add_roles(highest_role)
    # Try to set the role icon
    try:
        # If icon_url is an attachment, use its URL
        if interaction.attachments:
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
        await interaction.response.send_message(f"Role icon updated!", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don't have permission to manage roles or set role icons. Please check my permissions and role position.", ephemeral=True)
    except discord.HTTPException as e:
        if e.code == 30039:  # Not enough boosts for role icons
            await interaction.response.send_message("❌ This server does not have enough boosts to set a role icon.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Discord error: {e}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ An unexpected error occurred: {e}", ephemeral=True)

# Slash command to copy a custom emoji from a message into the server
# Slash command to copy custom emoji(s) from a message into the server
@bot.tree.command(name="copyemoji", description="Copy custom emoji(s) from a message into the server")
@app_commands.describe(
    message_link="Link to the message containing the emoji", 
    which="Optional: emoji number(s) to copy (e.g. 2 or 1,3)",
    create_sticker="Create as sticker instead of emoji (default: False)"
)
async def copyemoji(interaction: discord.Interaction, message_link: str, which: str = None, create_sticker: bool = False):
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

# Slash command to upload a custom emoji from an image URL
@bot.tree.command(name="uploademoji", description="Upload a custom emoji from an image URL")
@app_commands.describe(
    name="Name for the new emoji/sticker", 
    url="Image URL to upload",
    create_sticker="Create as sticker instead of emoji (default: False)"
)
async def uploademoji(interaction: discord.Interaction, name: str, url: str, create_sticker: bool = False):
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

# Slash command to rename an existing emoji or sticker
@bot.tree.command(name="renameemoji", description="Rename an existing emoji or sticker in the server")
@app_commands.describe(
    current_name="Current name of the emoji/sticker to rename",
    new_name="New name for the emoji/sticker",
    is_sticker="Whether to rename a sticker instead of emoji (default: False)"
)
async def renameemoji(interaction: discord.Interaction, current_name: str, new_name: str, is_sticker: bool = False):
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

# Slash command to copy an image from a message attachment as an emoji or sticker
@bot.tree.command(name="msgtoemoji", description="Copy an image from a message attachment as an emoji or sticker")
@app_commands.describe(
    message_link="Link to the message containing the image",
    name="Name for the new emoji/sticker",
    which="Optional: image number to copy if there are multiple (e.g. 2)",
    create_sticker="Create as a sticker instead of an emoji (default: False)"
)
async def msgtoemoji(interaction: discord.Interaction, message_link: str, name: str, which: int = 1, create_sticker: bool = False):
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

class ConversionType(str, enum.Enum):
    CYPIONATE = "cypionate"
    GEL = "gel"

@bot.tree.command(name="tconvert", description="Convert between testosterone cypionate and gel")
@app_commands.describe(
    starting_type="Type of testosterone (cypionate or gel)",
    dose="Dose amount (in mg or ml)",
    frequency="Frequency of dose (in days)"
)
async def tconvert(
    interaction: discord.Interaction,
    starting_type: ConversionType,
    dose: float,
    frequency: int
):
    """
    Converts between testosterone cypionate and gel doses.
    """
    daily_dose = dose / frequency
    gel_absorption = 0.1
    cyp_absorption = 0.95
    if starting_type == ConversionType.GEL:
        absorption = daily_dose * gel_absorption
        weekly = absorption * 7
        final = weekly / cyp_absorption
        response = f"{dose}mg gel every {frequency} days is approximately {final:.2f}mg cypionate weekly."
    if starting_type == ConversionType.CYPIONATE:
        absorption = daily_dose * cyp_absorption
        final = absorption / gel_absorption
        response = f"{dose}mg cypionate every {frequency} days is approximately {final:.2f}mg gel daily."
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