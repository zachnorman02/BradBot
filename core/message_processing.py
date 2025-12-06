"""
Message processing logic for link replacement and reply notifications
"""
import discord
import re
from database import db
from utils.helpers import is_url_suppressed, get_embedez_link, fix_amp_links
from utils.websites import websites, get_site_name


# List of sites that support EmbedEZ (Instagram handled separately)
EMBEDEZ_SITES = {'snapchat', 'ifunny', 'weibo', 'rule34'}


async def handle_reply_notification(message: discord.Message, bot: discord.Client):
    """
    Handle reply notifications - ping original poster if they have notifications enabled.
    
    Args:
        message: The message that is a reply
        bot: The bot client instance
    """
    if not message.reference:
        return
    
    try:
        # Get the message being replied to
        replied_message = await message.channel.fetch_message(message.reference.message_id)
        
        # Check if it's a message from the bot
        if replied_message.author != bot.user:
            return
        
        # Check if the bot's message is just a reply ping notification
        # Reply ping messages start with "-# " and contain only a mention
        bot_message_content = replied_message.content.strip()
        if bot_message_content.startswith('-# ') and bot_message_content.count('<@') == 1 and bot_message_content.count('>') == 1:
            # This is just a reply ping message, don't create another ping
            return
        
        # Check if reply pings are enabled for this guild
        guild_id = message.guild.id if message.guild else None
        if guild_id:
            reply_pings_enabled = db.get_guild_setting(guild_id, 'reply_pings_enabled', 'true').lower() == 'true'
            if not reply_pings_enabled:
                return  # Feature disabled for this guild
            
            # Check if members can send pings in this guild
            member_send_pings_enabled = db.get_guild_setting(guild_id, 'member_send_pings_enabled', 'true').lower() == 'true'
            if not member_send_pings_enabled:
                return  # Members can't trigger pings in this guild
        
        # Look up the original user from message tracking
        user_data = db.get_message_original_user(replied_message.id)
        original_user_id = None
        
        if user_data:
            # Found in tracking database
            original_user_id, guild_id = user_data
        else:
            # Not in database (old message) - parse the mention from the bot's message
            # Bot messages start with "<@user_id>: ..." format
            mention_match = re.match(r'^<@!?(\d+)>:', replied_message.content)
            if mention_match:
                original_user_id = int(mention_match.group(1))
        
        # If we found an original user, check if they want notifications
        if original_user_id and guild_id:
            # Don't ping if the replier is the original poster
            if message.author.id != original_user_id:
                # Check if the replier has opted out of sending pings
                # Check global setting first (guild_id = None), then fall back to server-specific
                global_send_pings = db.get_user_setting(message.author.id, None, 'send_reply_pings', True)
                
                # If global setting exists and is disabled, skip notification
                if not global_send_pings:
                    return
                
                # Check server-specific setting for the replier
                send_pings_enabled = db.get_user_setting(message.author.id, guild_id, 'send_reply_pings', True)
                
                if not send_pings_enabled:
                    return
                
                # Now check if the original poster wants to receive notifications
                # Check global setting first (guild_id = None), then fall back to server-specific
                global_notifications = db.get_user_reply_notifications(original_user_id, None)
                
                # If global setting exists and is disabled, skip notification
                if global_notifications is not None and not global_notifications:
                    return
                
                # Check server-specific setting
                notifications_enabled = db.get_user_reply_notifications(original_user_id, guild_id)
                
                if notifications_enabled:
                    # Send a subtle ping message
                    ping_message = f"-# <@{original_user_id}>"
                    await message.channel.send(ping_message, reference=message, mention_author=False)
    except Exception as e:
        # Silently fail to avoid spam (message might be deleted, db error, etc.)
        print(f"Error handling reply notification: {e}")


async def process_message_links(message: discord.Message) -> dict | None:
    """
    Process URLs in a message for link replacement and embed fixes.
    
    Args:
        message: The Discord message to process
        
    Returns:
        Dictionary with processing results:
        - content_changed: Whether the content was modified
        - new_content: The modified content
        - embedez_url: EmbedEZ URL if applicable
        - instagram_embed_url: Instagram embed URL if applicable
        - urls: Original URLs found
        - fixed_urls: Dictionary of URL replacements
        
        Returns None if no processing is needed
    """
    # Check if link replacement is enabled for this guild
    if message.guild:
        try:
            link_replacement_enabled = db.get_guild_link_replacement_enabled(message.guild.id)
            if not link_replacement_enabled:
                return None  # Skip link replacement if disabled
        except Exception as e:
            # If there's a database error, default to enabled (fail open)
            print(f"Error checking guild link replacement setting: {e}")
    
    # Find URLs in message
    url_pattern = re.compile(r'https?://[^\s<>()]+')
    urls = url_pattern.findall(message.content)
    
    # Filter out URLs that are suppressed (in backticks or angle brackets)
    urls = [url for url in urls if not is_url_suppressed(message.content, url)]
    
    if not urls:
        return None
    
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
    
    # Fix AMP links
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
    
    return {
        'content_changed': content_changed,
        'new_content': new_content,
        'embedez_url': embedez_url,
        'instagram_embed_url': instagram_embed_url,
        'urls': urls,
        'fixed_urls': fixed_urls
    }


async def send_processed_message(message: discord.Message, processed_result: dict, bot: discord.Client):
    """
    Send the processed message and handle message tracking.
    
    Args:
        message: Original message to replace
        processed_result: Result from process_message_links()
        bot: Bot client instance
    """
    if not processed_result or not processed_result['content_changed']:
        return
    
    # If original message was a reply, make the new message a reply too
    reference = message.reference
    sent_message = await message.channel.send(processed_result['new_content'], reference=reference, silent=True)
    
    # Store message tracking for reply notifications
    if sent_message and message.guild:
        # Get the first fixed URL for tracking
        original_url = processed_result['urls'][0] if processed_result['urls'] else None
        fixed_url = list(processed_result['fixed_urls'].values())[0] if processed_result['fixed_urls'] else None
        
        try:
            db.store_message_tracking(
                bot_message_id=sent_message.id,
                user_id=message.author.id,
                guild_id=message.guild.id,
                original_url=original_url,
                fixed_url=fixed_url
            )
        except Exception as e:
            # Silently log database errors, don't interrupt message flow
            print(f"Failed to store message tracking: {e}")
    
    # Delete original message
    try:
        await message.delete()
    except discord.Forbidden:
        await message.channel.send('I don\'t have permission to delete your message.')
    except discord.NotFound:
        pass
