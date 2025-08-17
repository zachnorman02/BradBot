import aiohttp
import datetime
import discord
from discord.ext import commands
from discord import app_commands
import os
import re
import asyncio
from dotenv import load_dotenv
from websites import fix_link_async, get_site_name

# Load environment variables from .env file
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# In-memory settings: {guild_id: include_original_message}
settings = {}

async def daily_booster_role_check():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.datetime.utcnow()
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

@bot.event
async def on_message(message):
    # Don't respond to bot messages
    if message.author.bot:
        return
    
    # Process commands first
    await bot.process_commands(message)
    
    # Match URLs, including those inside spoiler tags (||...||)
    spoiler_url_pattern = r'(\|\|)?(https?://[^\s|]+)(\|\|)?'
    matches = re.finditer(spoiler_url_pattern, message.content)
    
    fixed_content = message.content
    any_links_fixed = False
    
    # Step 1: Replace all URLs with their fixed versions
    url_pattern = r'(https?://[^\s|)]+)'
    fixed_content = message.content
    any_links_fixed = False
    # Find all URLs
    url_matches = list(re.finditer(url_pattern, fixed_content))
    replacements = {}
    for match in url_matches:
        url = match.group(1)
        site_name = get_site_name(url)
        fixed_url = await fix_link_async(url)
        # If Rule34, do not remove query parameters
        if site_name and site_name.lower() == 'rule34' and fixed_url:
            replacements[(match.start(1), match.end(1))] = fixed_url  # Use as-is
            any_links_fixed = True
        elif fixed_url and fixed_url != url:
            # Remove query parameters for other sites
            clean_url = fixed_url.split('?')[0]
            replacements[(match.start(1), match.end(1))] = clean_url
            any_links_fixed = True
    # Apply replacements from end to start
    for (start, end), replacement in sorted(replacements.items(), reverse=True):
        fixed_content = fixed_content[:start] + replacement + fixed_content[end:]

    # Step 2: Wrap only plain URLs (not inside markdown) with markdown
    # Find all markdown links and mark their spans
    markdown_link_pattern = re.compile(r'(\[[^\]]+\])\((https?://[^\s)]+)\)')
    markdown_spans = [ (m.start(2), m.end(2)) for m in markdown_link_pattern.finditer(fixed_content) ]

    def is_in_markdown_link(start, end):
        return any(start >= span_start and end <= span_end for span_start, span_end in markdown_spans)

    # Find all URLs and wrap only those not inside markdown
    url_pattern = re.compile(r'(https?://[^\s|)]+)')
    new_content = fixed_content
    offset = 0
    embez_links = []
    for match in url_pattern.finditer(fixed_content):
        url_start, url_end = match.start(1), match.end(1)
        if is_in_markdown_link(url_start, url_end):
            continue
        url = match.group(1)
        site_name = get_site_name(url)
        # If site is supported by EmbedEZ, try to get EmbedEZ link
        if site_name or site_name.lower() in EMBEDEZ_SITES:
            embedez_link = await get_embedez_link(url)
            embez_links.append(embedez_link)
        # Only wrap in markdown if site_name is not the url itself
        if site_name and site_name != url:
            replacement = f'[{site_name}]({url})'
        else:
            replacement = url
        # Replace in new_content, adjusting for offset
        new_content = new_content[:url_start+offset] + replacement + new_content[url_end+offset:]
        offset += len(replacement) - (url_end - url_start)
    fixed_content = new_content

    # Suppress embeds for all but the first link (including markdown links)
    # Find all markdown and raw links
    markdown_link_pattern = re.compile(r'(\[[^\]]+\])\((https?://[^\s)]+)\)')
    raw_url_pattern = re.compile(r'(https?://[^\s|)]+)')
    # Collect all link spans (start, end, is_markdown)
    link_spans = []
    for m in markdown_link_pattern.finditer(fixed_content):
        link_spans.append((m.start(2), m.end(2), True))
    for m in raw_url_pattern.finditer(fixed_content):
        # Only add if not inside markdown
        if not any(m.start(1) >= span_start and m.end(1) <= span_end for span_start, span_end, _ in link_spans):
            link_spans.append((m.start(1), m.end(1), False))
    # Sort by start position
    link_spans.sort()
    # Only keep the first link as-is, wrap others in <>
    if link_spans:
        first = True
        offset = 0
        content = fixed_content
        for start, end, is_markdown in link_spans:
            start += offset
            end += offset
            url = content[start:end]
            if first:
                first = False
                continue
            if is_markdown:
                # Wrap URL part in angle brackets
                replacement = f'<{url}>'
            else:
                # Wrap raw URL in angle brackets
                replacement = f'<{url}>'
            content = content[:start] + replacement + content[end:]
            offset += len(replacement) - (end - start)
        fixed_content = content

    # Send the fixed message if any links were replaced
    if any_links_fixed:
        # Create the response with user ping and fixed content
        response = f"{message.author.mention}: {fixed_content}"
        if embez_links:
            embez_link_text = [f'[EmbedEZ]({link})' for link in embez_links]
            response = f'EmbedEZ Links: {" ".join(embez_link_text)}\n{response}'
        # Send the fixed message
        await message.channel.send(response, silent=True)
        
        # Delete the original message
        try:
            await message.delete()
        except discord.Forbidden:
            # Bot doesn't have permission to delete messages
            await message.channel.send("*Note: I don't have permission to delete the original message*")
        except discord.NotFound:
            # Message was already deleted
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

# Slash command for server boosters to set their personal role color
@bot.tree.command(name="boostercolor", description="Set your booster role color: solid, gradient, or holographic")
@app_commands.describe(hex="Hex color code (e.g. #FF5733)", style="Color style: solid, gradient, or holographic", hex2="Second hex code for gradient (optional)")
async def boostercolor(interaction: discord.Interaction, hex: str, style: str = "solid", hex2: str = None):
    guild = interaction.guild
    member = interaction.user if hasattr(interaction, 'user') else interaction.author
    booster_role = discord.utils.get(guild.roles, is_premium_subscriber=True)
    app_info = await interaction.client.application_info()
    is_owner = interaction.user.id == app_info.owner.id
    if not (booster_role and booster_role in member.roles) and not is_owner:
        await interaction.response.send_message("You must be a server booster or the bot owner to use this command.", ephemeral=True)
        return
    # Validate hex codes and style
    if style == "solid":
        if not re.fullmatch(r'#?[0-9A-Fa-f]{6}', hex):
            await interaction.response.send_message("Invalid hex code. Please use format #RRGGBB.", ephemeral=True)
            return
        color_value = int(hex.lstrip('#'), 16)
        color = discord.Color(color_value)
        secondary_color = None
        preset = None
    elif style == "gradient":
        if not (hex and hex2 and re.fullmatch(r'#?[0-9A-Fa-f]{6}', hex) and re.fullmatch(r'#?[0-9A-Fa-f]{6}', hex2)):
            await interaction.response.send_message("For gradient, provide two hex codes in format #RRGGBB.", ephemeral=True)
            return
        color = discord.Color(int(hex.lstrip('#'), 16))
        secondary_color = discord.Color(int(hex2.lstrip('#'), 16))
        preset = None
    elif style == "holographic":
        color = discord.Color(11127295)
        secondary_color = discord.Color(16759788)
        tertiary_color = discord.Color(16761760)
        preset = None
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
        bot_member = guild.me
        bot_top_role = sorted(bot_member.roles, key=lambda r: r.position, reverse=True)[0]
        move_success = True
        try:
            await new_role.edit(position=bot_top_role.position - 1)
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
        move_success = True
        try:
            await new_role.edit(position=bot_top_role.position - 1)
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
@bot.tree.command(name="copyemoji", description="Copy custom emoji(s) from a message into the server")
@app_commands.describe(message_link="Link to the message containing the emoji", which="Optional: emoji number(s) to copy (e.g. 2 or 1,3)")
async def copyemoji(interaction: discord.Interaction, message_link: str, which: str = None):
    # Check bot and user permissions
    if not interaction.guild.me.guild_permissions.manage_emojis_and_stickers:
        await interaction.response.send_message("❌ I need the 'Manage Emojis and Stickers' permission to copy emojis.", ephemeral=True)
        return
    if not interaction.user.guild_permissions.manage_emojis_and_stickers:
        await interaction.response.send_message("❌ You need the 'Manage Emojis and Stickers' permission to use this command.", ephemeral=True)
        return
    # Parse message link
    import re
    match = re.match(r"https://discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)", message_link)
    if not match:
        await interaction.response.send_message("❌ Invalid message link format.", ephemeral=True)
        return
    guild_id, channel_id, message_id = map(int, match.groups())
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
        except Exception:
            await interaction.response.send_message("❌ Invalid emoji number(s) format. Use e.g. 2 or 1,3.", ephemeral=True)
            return
        indices = [i for i in indices if 0 <= i < len(emoji_matches)]
        if not indices:
            await interaction.response.send_message("❌ No valid emoji number(s) specified.", ephemeral=True)
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
        # Try to add emoji to the server
        try:
            new_emoji = await interaction.guild.create_custom_emoji(name=emoji_name, image=image_bytes)
            results.append(f"✅ Emoji '{new_emoji.name}' copied to the server!")
        except discord.HTTPException as e:
            if e.code == 30008:
                results.append("❌ This server has reached its emoji limit.")
                break
            else:
                results.append(f"❌ Discord error for '{emoji_name}': {e}")
        except Exception as e:
            results.append(f"❌ Unexpected error for '{emoji_name}': {e}")
    await interaction.response.send_message("\n".join(results), ephemeral=True)

# Slash command to upload a custom emoji from an image URL
@bot.tree.command(name="uploademoji", description="Upload a custom emoji from an image URL")
@app_commands.describe(name="Name for the new emoji", url="Image URL to upload as emoji")
async def uploademoji(interaction: discord.Interaction, name: str, url: str):
    # Check bot and user permissions
    if not interaction.guild.me.guild_permissions.manage_emojis_and_stickers:
        await interaction.response.send_message("❌ I need the 'Manage Emojis and Stickers' permission to upload emojis.", ephemeral=True)
        return
    if not interaction.user.guild_permissions.manage_emojis_and_stickers:
        await interaction.response.send_message("❌ You need the 'Manage Emojis and Stickers' permission to use this command.", ephemeral=True)
        return
    import aiohttp
    # Download image
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                await interaction.response.send_message("❌ Could not download the image. Please check the URL.", ephemeral=True)
                return
            image_bytes = await resp.read()
    # Try to add emoji to the server
    try:
        new_emoji = await interaction.guild.create_custom_emoji(name=name, image=image_bytes)
        await interaction.response.send_message(f"✅ Emoji '{new_emoji.name}' uploaded to the server!", ephemeral=True)
    except discord.HTTPException as e:
        if e.code == 30008:
            await interaction.response.send_message("❌ This server has reached its emoji limit.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Discord error: {e}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ An unexpected error occurred: {e}", ephemeral=True)

bot.run(os.getenv("DISCORD_TOKEN"))