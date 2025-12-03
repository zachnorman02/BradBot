"""
Background tasks for BradBot
"""
import discord
import datetime as dt
import asyncio
from database import db


async def daily_booster_role_check(bot):
    """Daily task to check for users who lost booster status and save their role configurations"""
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = dt.datetime.now(dt.timezone.utc)
        # Run at midnight UTC
        next_run = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        wait_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        
        for guild in bot.guilds:
            for member in guild.members:
                # Find custom roles (only one member, not @everyone)
                personal_roles = [role for role in member.roles if not role.is_default() and len(role.members) == 1]
                # Check if user has custom roles but is NOT a booster (lost booster status)
                if personal_roles and not member.premium_since:
                    # User lost booster status - save role info to DB (but don't delete)
                    for role in personal_roles:
                        try:
                            # Save role configuration to database
                            color_hex = f"#{role.color.value:06x}"
                            secondary_color_hex = f"#{role.secondary_color.value:06x}" if role.secondary_color else None
                            tertiary_color_hex = f"#{role.tertiary_color.value:06x}" if role.tertiary_color else None
                            icon_hash = role.icon.key if role.icon else None
                            icon_data = None
                            if role.icon:
                                try:
                                    icon_data = await role.icon.read()
                                except Exception:
                                    pass
                            
                            # Get existing role data to preserve color_type
                            existing_role = db.get_booster_role(member.id, guild.id)
                            color_type = existing_role['color_type'] if existing_role else 'solid'
                            
                            db.store_booster_role(
                                user_id=member.id,
                                guild_id=guild.id,
                                role_id=role.id,
                                role_name=role.name,
                                color_hex=color_hex,
                                color_type=color_type,
                                icon_hash=icon_hash,
                                icon_data=icon_data,
                                secondary_color_hex=secondary_color_hex,
                                tertiary_color_hex=tertiary_color_hex
                            )
                            print(f"💾 [Daily scan] Saved booster role configuration for {member.display_name} (role kept)")
                        except Exception as e:
                            print(f"Error saving role configuration for {member.display_name}: {e}")


async def on_member_update_handler(before: discord.Member, after: discord.Member):
    """Detect when a member starts or stops boosting and auto-create/restore/remove their role"""
    
    # Check if member just stopped boosting
    if before.premium_since and not after.premium_since:
        try:
            # Find custom roles (only one member, not @everyone)
            personal_roles = [role for role in after.roles if not role.is_default() and len(role.members) == 1]
            
            if personal_roles:
                # User lost booster status - save role info to DB before deleting
                for role in personal_roles:
                    try:
                        # Save role configuration to database
                        color_hex = f"#{role.color.value:06x}"
                        secondary_color_hex = f"#{role.secondary_color.value:06x}" if role.secondary_color else None
                        tertiary_color_hex = f"#{role.tertiary_color.value:06x}" if role.tertiary_color else None
                        icon_hash = role.icon.key if role.icon else None
                        icon_data = None
                        if role.icon:
                            try:
                                icon_data = await role.icon.read()
                            except Exception:
                                pass
                        
                        # Get existing role data to preserve color_type
                        existing_role = db.get_booster_role(after.id, after.guild.id)
                        color_type = existing_role['color_type'] if existing_role else 'solid'
                        
                        db.store_booster_role(
                            user_id=after.id,
                            guild_id=after.guild.id,
                            role_id=role.id,
                            role_name=role.name,
                            color_hex=color_hex,
                            color_type=color_type,
                            icon_hash=icon_hash,
                            icon_data=icon_data,
                            secondary_color_hex=secondary_color_hex,
                            tertiary_color_hex=tertiary_color_hex
                        )
                        print(f"💾 Saved booster role configuration for {after.display_name} (stopped boosting, role kept)")
                    except Exception as e:
                        print(f"Error saving role configuration for {after.display_name}: {e}")
        except Exception as e:
            print(f"Error processing booster status loss for {after.display_name}: {e}")
    
    # Check if member just started boosting
    elif not before.premium_since and after.premium_since:
        try:
            # Check if they have a saved role in the database
            db_role_data = db.get_booster_role(after.id, after.guild.id)
            
            if db_role_data:
                # User has a saved role - first try to find the existing role
                existing_role = None
                if db_role_data.get('role_id'):
                    existing_role = after.guild.get_role(db_role_data['role_id'])
                
                if existing_role:
                    # Role still exists! Just assign it back to them
                    try:
                        await after.add_roles(existing_role, reason="Re-assigning existing booster role")
                        print(f"✅ Re-assigned existing booster role '{existing_role.name}' to {after.display_name}")
                    except Exception as e:
                        print(f"Error re-assigning existing role to {after.display_name}: {e}")
                else:
                    # Role was deleted, recreate it from saved configuration
                    try:
                        primary_color = discord.Color(int(db_role_data['color_hex'].replace('#', ''), 16))
                        secondary_color = None
                        tertiary_color = None
                        
                        if db_role_data.get('secondary_color_hex'):
                            secondary_color = discord.Color(int(db_role_data['secondary_color_hex'].replace('#', ''), 16))
                        if db_role_data.get('tertiary_color_hex'):
                            tertiary_color = discord.Color(int(db_role_data['tertiary_color_hex'].replace('#', ''), 16))
                        
                        # Create role with saved configuration
                        restored_role = await after.guild.create_role(
                            name=db_role_data['role_name'],
                            color=primary_color,
                            secondary_color=secondary_color,
                            tertiary_color=tertiary_color,
                            reason=f"Auto-restoring booster role for {after.display_name}"
                        )
                        
                        # Set icon if it exists
                        if db_role_data['icon_data'] and "ROLE_ICONS" in after.guild.features:
                            try:
                                await restored_role.edit(display_icon=db_role_data['icon_data'])
                            except Exception as e:
                                print(f"Could not restore role icon for {after.display_name}: {e}")
                        
                        # Assign to user
                        await after.add_roles(restored_role, reason="Auto-restoring booster role")
                        
                        # Update role_id in database
                        db.update_booster_role_id(after.id, after.guild.id, restored_role.id)
                        
                        print(f"✅ Recreated and assigned booster role '{db_role_data['role_name']}' for {after.display_name}")
                        
                    except Exception as e:
                        print(f"Error restoring booster role for {after.display_name}: {e}")
            else:
                # No saved role - create a new default role
                try:
                    new_role = await after.guild.create_role(
                        name=after.name,
                        color=discord.Color.random(),
                        reason=f"Auto-creating booster role for new booster {after.name}"
                    )
                    
                    # Position it above the user's current highest role
                    try:
                        user_top_role = after.top_role
                        # Position new role just above their current top role
                        await new_role.edit(position=user_top_role.position + 1)
                    except Exception as e:
                        print(f"Could not position role: {e}")
                    
                    # Assign to user
                    await after.add_roles(new_role, reason="Auto-creating booster role")
                    
                    # Save to database with auto-detected color type
                    color_hex = f"#{new_role.color.value:06x}"
                    secondary_color_hex = f"#{new_role.secondary_color.value:06x}" if new_role.secondary_color else None
                    tertiary_color_hex = f"#{new_role.tertiary_color.value:06x}" if new_role.tertiary_color else None
                    
                    # Auto-detect color type
                    if tertiary_color_hex:
                        color_type = "holographic"
                    elif secondary_color_hex:
                        color_type = "gradient"
                    else:
                        color_type = "solid"
                    
                    db.store_booster_role(
                        user_id=after.id,
                        guild_id=after.guild.id,
                        role_id=new_role.id,
                        role_name=new_role.name,
                        color_hex=color_hex,
                        color_type=color_type,
                        icon_hash=None,
                        icon_data=None,
                        secondary_color_hex=secondary_color_hex,
                        tertiary_color_hex=tertiary_color_hex
                    )
                    
                    print(f"✅ Auto-created new booster role '{new_role.name}' for {after.display_name}")
                    
                except Exception as e:
                    print(f"Error creating new booster role for {after.display_name}: {e}")
        except Exception as e:
            print(f"Error checking for saved booster role: {e}")


async def poll_auto_close_check(bot):
    """Background task to check for polls that should auto-close based on time"""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            # Check every minute
            await asyncio.sleep(60)
            
            # Initialize database if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Get all active polls with close_at times
            query = """
            SELECT id, guild_id, channel_id, message_id, question, close_at
            FROM main.polls
            WHERE is_active = TRUE AND close_at IS NOT NULL AND close_at <= CURRENT_TIMESTAMP
            """
            expired_polls = db.execute_query(query)
            
            if expired_polls:
                for poll_data in expired_polls:
                    poll_id, guild_id, channel_id, message_id, question, close_at = poll_data
                    
                    try:
                        # Close the poll
                        db.close_poll(poll_id)
                        
                        # Try to update the message to show it's closed
                        if message_id:
                            guild = bot.get_guild(guild_id)
                            if guild:
                                channel = guild.get_channel(channel_id)
                                if channel:
                                    try:
                                        message = await channel.fetch_message(message_id)
                                        
                                        # Update embed to show closed status
                                        if message.embeds:
                                            embed = message.embeds[0]
                                            embed.color = discord.Color.red()
                                            embed.title = "📊 Poll (CLOSED)"
                                            
                                            # Disable the button
                                            view = discord.ui.View()
                                            button = discord.ui.Button(
                                                label="Poll Closed",
                                                style=discord.ButtonStyle.secondary,
                                                disabled=True
                                            )
                                            view.add_item(button)
                                            
                                            await message.edit(embed=embed, view=view)
                                    except discord.NotFound:
                                        pass
                                    except Exception as e:
                                        print(f"Error updating closed poll message: {e}")
                        
                        print(f"⏱️ Auto-closed poll {poll_id} due to time limit")
                    
                    except Exception as e:
                        print(f"Error auto-closing poll {poll_id}: {e}")
        
        except Exception as e:
            print(f"Error in poll auto-close check: {e}")
