"""
Message mirroring functionality
Automatically copies messages to configured target channels and keeps them synced
"""
import discord
from typing import Optional
from database import db


def create_mirror_embed(message: discord.Message) -> discord.Embed:
    """Create a mirror embed for a message.
    
    Args:
        message: The original Discord message to mirror
        
    Returns:
        discord.Embed: The embed representation of the message
    """
    content = message.content or ""
    
    # Create embed with author info
    embed = discord.Embed(
        description=content if content else "*[No text content]*",
        color=message.author.color if message.author.color != discord.Color.default() else discord.Color.blue(),
        timestamp=message.created_at
    )
    
    # Add author info
    embed.set_author(
        name=message.author.display_name,
        icon_url=message.author.display_avatar.url
    )
    
    # Add footer showing source channel
    embed.set_footer(text=f"Mirrored from #{message.channel.name}")
    
    # Handle attachments
    if message.attachments:
        # Add attachment URLs to embed
        attachment_text = "\n\n**Attachments:**\n" + "\n".join(
            f"[{att.filename}]({att.url})" for att in message.attachments
        )
        
        # Append to description if it fits
        if len(embed.description + attachment_text) <= 4096:
            embed.description += attachment_text
        else:
            embed.add_field(
                name="📎 Attachments",
                value="\n".join(f"[{att.filename}]({att.url})" for att in message.attachments[:10]),
                inline=False
            )
    
    return embed


async def handle_message_mirror(message: discord.Message):
    """Handle mirroring of a new message to configured target channels."""
    # Ignore bot messages to prevent infinite loops
    if message.author.bot:
        return
    
    # Only process guild messages
    if not message.guild:
        return
    
    # Check if this channel has any mirror configurations
    mirrors = db.get_message_mirrors(message.guild.id, message.channel.id)
    
    if not mirrors:
        return  # No mirrors configured
    
    # Mirror the message to each target channel
    for mirror in mirrors:
        target_channel = message.guild.get_channel(mirror['target_channel_id'])
        
        if not target_channel:
            print(f"[MIRROR] Target channel {mirror['target_channel_id']} not found, skipping")
            continue
        
        try:
            # Create mirror embed using helper function
            embed = create_mirror_embed(message)
            
            # Handle embeds from original message
            embeds_to_send = [embed]
            if message.embeds:
                # Add original embeds (up to 10 total)
                for orig_embed in message.embeds[:9]:  # Leave room for our wrapper embed
                    embeds_to_send.append(orig_embed)
            
            # Send mirrored message
            mirror_msg = await target_channel.send(embeds=embeds_to_send)
            
            # Track the mirrored message for future updates
            db.track_mirrored_message(
                message.id,
                message.channel.id,
                mirror_msg.id,
                target_channel.id,
                message.guild.id
            )
            
            print(f"[MIRROR] Mirrored message {message.id} from #{message.channel.name} to #{target_channel.name}")
            
        except discord.Forbidden:
            print(f"[MIRROR] No permission to send messages in {target_channel.name}")
        except Exception as e:
            print(f"[MIRROR] Error mirroring message to {target_channel.name}: {e}")


async def handle_message_edit(before: Optional[discord.Message], after: discord.Message):
    """Handle editing of a mirrored message."""
    print(f"[DEBUG] on_message_edit fired: before_id={getattr(before, 'id', None)}, after_id={getattr(after, 'id', None)}, author={getattr(after, 'author', None)}, channel={getattr(after, 'channel', None)}")
    # Ignore bot messages
    if after.author.bot:
        print(f"[DEBUG] Skipping bot message edit: {after.id}")
        return
    
    # Only process guild messages
    if not after.guild:
        print(f"[DEBUG] Skipping non-guild message edit: {after.id}")
        return
    
    # Check if this message has been mirrored
    mirrored = db.get_mirrored_messages(after.id)
    print(f"[DEBUG] Mirrored entries for {after.id}: {mirrored}")
    
    if not mirrored:
        print(f"[DEBUG] No mirrored messages found for {after.id}")
        return  # Message not mirrored
    
    # Update all mirror copies
    for mirror_info in mirrored:
        target_channel = after.guild.get_channel(mirror_info['mirror_channel_id'])
        print(f"[DEBUG] Attempting to update mirror: mirror_message_id={mirror_info['mirror_message_id']}, mirror_channel_id={mirror_info['mirror_channel_id']}, target_channel={target_channel}")
        
        if not target_channel:
            print(f"[MIRROR] Target channel {mirror_info['mirror_channel_id']} not found for edit")
            continue
        
        try:
            # Fetch the mirror message
            mirror_msg = await target_channel.fetch_message(mirror_info['mirror_message_id'])
            print(f"[DEBUG] Fetched mirror message: {mirror_msg.id}")
            
            # Build updated embed
            content = after.content or ""
            
            embed = discord.Embed(
                description=content if content else "*[No text content]*",
                color=after.author.color if after.author.color != discord.Color.default() else discord.Color.blue(),
                timestamp=after.created_at
            )
            
            # Add author info
            embed.set_author(
                name=after.author.display_name,
                icon_url=after.author.display_avatar.url
            )
            
            # Add footer showing source channel and edit indicator
            embed.set_footer(text=f"Mirrored from #{after.channel.name} • Edited")
            
            # Handle attachments
            if after.attachments:
                attachment_text = "\n\n**Attachments:**\n" + "\n".join(
                    f"[{att.filename}]({att.url})" for att in after.attachments
                )
                
                if len(embed.description + attachment_text) <= 4096:
                    embed.description += attachment_text
                else:
                    embed.add_field(
                        name="📎 Attachments",
                        value="\n".join(f"[{att.filename}]({att.url})" for att in after.attachments[:10]),
                        inline=False
                    )
            
            # Handle embeds from original message
            embeds_to_send = [embed]
            if after.embeds:
                for orig_embed in after.embeds[:9]:
                    embeds_to_send.append(orig_embed)
            
            # Update the mirror message
            await mirror_msg.edit(embeds=embeds_to_send)
            
            print(f"[MIRROR] Updated mirror {mirror_info['mirror_message_id']} in #{target_channel.name}")
            
        except discord.NotFound:
            print(f"[MIRROR] Mirror message {mirror_info['mirror_message_id']} not found, cleaning up tracking")
        except discord.Forbidden:
            print(f"[MIRROR] No permission to edit message in {target_channel.name}")
        except Exception as e:
            print(f"[MIRROR] Error updating mirror in {target_channel.name}: {e}")


async def handle_message_delete(message: discord.Message):
    """Handle deletion of a mirrored message."""
    # Ignore bot messages
    if message.author.bot:
        return
    
    # Only process guild messages
    if not message.guild:
        return
    
    # Check if this message has been mirrored
    mirrored = db.get_mirrored_messages(message.id)
    
    if not mirrored:
        return  # Message not mirrored
    
    # Delete all mirror copies
    for mirror_info in mirrored:
        target_channel = message.guild.get_channel(mirror_info['mirror_channel_id'])
        
        if not target_channel:
            print(f"[MIRROR] Target channel {mirror_info['mirror_channel_id']} not found for deletion")
            continue
        
        try:
            # Fetch and delete the mirror message
            mirror_msg = await target_channel.fetch_message(mirror_info['mirror_message_id'])
            await mirror_msg.delete()
            
            print(f"[MIRROR] Deleted mirror {mirror_info['mirror_message_id']} from #{target_channel.name}")
            
        except discord.NotFound:
            print(f"[MIRROR] Mirror message {mirror_info['mirror_message_id']} already deleted")
        except discord.Forbidden:
            print(f"[MIRROR] No permission to delete message in {target_channel.name}")
        except Exception as e:
            print(f"[MIRROR] Error deleting mirror in {target_channel.name}: {e}")
    
    # Clean up all tracking entries for this message
    db.delete_mirrored_message_tracking(message.id)
    print(f"[MIRROR] Cleaned up tracking for original message {message.id}")
