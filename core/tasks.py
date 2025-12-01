"""
Background tasks for BradBot
"""
import discord
import datetime as dt
import asyncio
from database import db


async def daily_booster_role_check(bot):
    """Daily task to check for users who lost booster status and save/delete their roles"""
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
                            existing_role = db.get_booster_role(member.id, guild.id)
                            color_type = existing_role['color_type'] if existing_role else 'solid'
                            
                            db.store_booster_role(
                                user_id=member.id,
                                guild_id=guild.id,
                                role_id=role.id,  # Will be outdated once deleted, but kept for reference
                                role_name=role.name,
                                color_hex=color_hex,
                                color_type=color_type,
                                icon_hash=icon_hash,
                                icon_data=icon_data,
                                secondary_color_hex=secondary_color_hex,
                                tertiary_color_hex=tertiary_color_hex
                            )
                            print(f"Saved booster role for {member.display_name} before deletion")
                            
                            # Now delete the role
                            await role.delete(reason="Lost server booster status")
                        except Exception as e:
                            print(f"Error handling role removal for {member.display_name}: {e}")


async def on_member_update_handler(before: discord.Member, after: discord.Member):
    """Detect when a member starts boosting and auto-create or restore their role"""
    # Check if member just started boosting
    if not before.premium_since and after.premium_since:
        try:
            # Check if they have a saved role in the database
            db_role_data = db.get_booster_role(after.id, after.guild.id)
            
            if db_role_data:
                # User has a saved role - restore it
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
                    
                    print(f"✅ Auto-restored booster role '{db_role_data['role_name']}' for {after.display_name}")
                    
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
