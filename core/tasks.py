"""
Background tasks for BradBot
"""
import discord
import datetime as dt
import asyncio
from database import db


async def handle_verified_role_logic(before: discord.Member, after: discord.Member):
    """
    Handle verified role assignment logic:
    1. Remove unverified role when verified role is added
    2. Give lvl 0 role if they don't have an existing lvl role
    3. Remove lvl 0 when they gain a lvl x role
    """
    try:
        # Skip bots
        if after.bot:
            return
        
        # Check if verified role automation is enabled for this guild
        verify_enabled = db.get_guild_setting(after.guild.id, 'verify_roles_enabled', 'true')
        if verify_enabled.lower() != 'true':
            return  # Feature disabled for this guild
        
        # Get role changes
        before_role_ids = {role.id for role in before.roles}
        after_role_ids = {role.id for role in after.roles}
        added_roles = after_role_ids - before_role_ids
        
        # Define role names (case-insensitive)
        verified_role = discord.utils.get(after.guild.roles, name="verified")
        unverified_role = discord.utils.get(after.guild.roles, name="unverified")
        lvl0_role = discord.utils.get(after.guild.roles, name="lvl 0")
        
        if not verified_role:
            return  # No verified role configured, skip logic
        
        # Check if verified role was just added
        if verified_role.id in added_roles:
            print(f"[VERIFIED] {after.display_name} gained verified role")
            
            # 1. Remove unverified role
            if unverified_role and unverified_role in after.roles:
                try:
                    await after.remove_roles(unverified_role, reason="User verified - removing unverified role")
                    print(f"[VERIFIED] Removed unverified role from {after.display_name}")
                except Exception as e:
                    print(f"[VERIFIED] Error removing unverified role: {e}")
            
            # 2. Check if they have any lvl role (lvl 1, lvl 2, etc.)
            has_lvl_role = any(role.name.startswith("lvl ") and role.name != "lvl 0" 
                             for role in after.roles)
            
            if not has_lvl_role and lvl0_role:
                # Give them lvl 0 role
                try:
                    await after.add_roles(lvl0_role, reason="New verified user - assigning lvl 0")
                    print(f"[VERIFIED] Assigned lvl 0 role to {after.display_name}")
                except Exception as e:
                    print(f"[VERIFIED] Error assigning lvl 0 role: {e}")
        
        # 3. Check if they gained a lvl x role (not lvl 0)
        if added_roles:
            for role_id in added_roles:
                role = after.guild.get_role(role_id)
                if role and role.name.startswith("lvl ") and role.name != "lvl 0":
                    # They got a lvl x role, remove lvl 0 if they have it
                    if lvl0_role and lvl0_role in after.roles:
                        try:
                            await after.remove_roles(lvl0_role, reason=f"User gained {role.name} - removing lvl 0")
                            print(f"[VERIFIED] Removed lvl 0 from {after.display_name} (gained {role.name})")
                        except Exception as e:
                            print(f"[VERIFIED] Error removing lvl 0 role: {e}")
                    break  # Only need to do this once
        
    except Exception as e:
        print(f"[VERIFIED] Error in verified role logic: {e}")


async def daily_booster_role_check(bot):
    """Daily task to check for users who lost booster status, save their role configurations,
    and assign lvl 0 to verified users who should have it"""
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = dt.datetime.now(dt.timezone.utc)
        # Run at midnight UTC
        next_run = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        wait_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        
        print(f"[DAILY TASK] Running midnight checks...")
        
        for guild in bot.guilds:
            # Get role objects for this guild
            verified_role = discord.utils.get(guild.roles, name="verified")
            lvl0_role = discord.utils.get(guild.roles, name="lvl 0")
            
            # Check if verified role automation is enabled for this guild
            verify_enabled = db.get_guild_setting(guild.id, 'verify_roles_enabled', 'true')
            
            for member in guild.members:
                # === Booster role check ===
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
                
                # === Level 0 assignment check ===
                # Check if they have verified role but no lvl role (skip bots)
                if not member.bot and verify_enabled.lower() == 'true' and verified_role and verified_role in member.roles and lvl0_role:
                    # Check if they have any lvl role (including lvl 0)
                    has_lvl_role = any(role.name.startswith("lvl ") for role in member.roles)
                    
                    if not has_lvl_role:
                        # They're verified but have no level role, give them lvl 0
                        try:
                            await member.add_roles(lvl0_role, reason="Daily check - assigning missing lvl 0 to verified user")
                            print(f"[DAILY TASK] Assigned lvl 0 to {member.display_name} (verified but had no level role)")
                        except Exception as e:
                            print(f"[DAILY TASK] Error assigning lvl 0 to {member.display_name}: {e}")
                
                # === Unverified user kick check ===
                # Kick unverified users after 30 days unless they're in a verification ticket
                unverified_role = discord.utils.get(guild.roles, name="unverified")
                if not member.bot and unverified_role and unverified_role in member.roles:
                    # Check how long they've been a member
                    if member.joined_at:
                        days_since_join = (now - member.joined_at).days
                        
                        if days_since_join >= 30:
                            # Check if they're in a verification ticket
                            in_verification_ticket = False
                            
                            # Find the "verification" category
                            verification_category = discord.utils.get(guild.categories, name="verification")
                            
                            if verification_category:
                                # Check all ticket channels in the verification category
                                for channel in verification_category.channels:
                                    if isinstance(channel, discord.TextChannel) and channel.name.startswith("ticket-"):
                                        # Check if member has access to this channel
                                        permissions = channel.permissions_for(member)
                                        if permissions.read_messages:
                                            in_verification_ticket = True
                                            break
                            
                            # Kick if not in a verification ticket
                            if not in_verification_ticket:
                                try:
                                    await member.kick(reason=f"Unverified for {days_since_join} days with no active verification ticket")
                                    print(f"[DAILY TASK] Kicked {member.display_name} (unverified for {days_since_join} days, no ticket)")
                                except Exception as e:
                                    print(f"[DAILY TASK] Error kicking {member.display_name}: {e}")
        
        print(f"[DAILY TASK] Midnight checks completed")


async def on_member_update_handler(before: discord.Member, after: discord.Member):
    """Detect when a member starts or stops boosting and auto-create/restore/remove their role.
    Also handle verified role assignment and level 0 role logic."""
    
    # Handle verified role logic
    await handle_verified_role_logic(before, after)
    
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


async def reminder_check(bot):
    """Background task to check for and send pending reminders"""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            # Check for pending reminders every 30 seconds
            await asyncio.sleep(30)
            
            # Get all pending reminders
            pending = db.get_pending_reminders()
            
            for reminder in pending:
                try:
                    user = await bot.fetch_user(reminder['user_id'])
                    if not user:
                        db.mark_reminder_sent(reminder['id'])
                        continue
                    
                    message = reminder['message']
                    
                    # Try to send in the original channel first
                    sent = False
                    if reminder['guild_id'] and reminder['channel_id']:
                        guild = bot.get_guild(reminder['guild_id'])
                        if guild:
                            channel = guild.get_channel(reminder['channel_id'])
                            if channel:
                                try:
                                    await channel.send(
                                        f"⏰ **Reminder for {user.mention}**\n{message}"
                                    )
                                    sent = True
                                except (discord.Forbidden, discord.HTTPException):
                                    pass
                    
                    # Fall back to DM if channel send failed
                    if not sent:
                        try:
                            guild_name = ""
                            if reminder['guild_id']:
                                guild = bot.get_guild(reminder['guild_id'])
                                if guild:
                                    guild_name = f"\n(Originally set in {guild.name})"
                            
                            await user.send(
                                f"⏰ **Reminder**\n{message}{guild_name}"
                            )
                            sent = True
                        except discord.Forbidden:
                            pass
                    
                    # Mark as sent (even if delivery failed - we tried)
                    db.mark_reminder_sent(reminder['id'])
                    
                    if sent:
                        print(f"⏰ Sent reminder {reminder['id']} to {user}")
                    else:
                        print(f"⏰ Could not deliver reminder {reminder['id']} to {user} (channel and DM failed)")
                
                except Exception as e:
                    print(f"Error sending reminder {reminder['id']}: {e}")
                    # Mark as sent to avoid retry loops
                    db.mark_reminder_sent(reminder['id'])
        
        except Exception as e:
            print(f"Error in reminder check: {e}")
            await asyncio.sleep(30)


async def timer_check(bot):
    """Background task to update and complete timers"""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            # Check timers every 30 seconds
            await asyncio.sleep(30)
            
            # Get all active timers
            active_timers = db.get_active_timers()
            now = dt.datetime.now(dt.timezone.utc)
            
            for timer in active_timers:
                try:
                    # Check if timer is complete
                    if timer['end_time'] <= now:
                        # Timer finished - mark complete and send notification
                        guild = bot.get_guild(timer['guild_id'])
                        if not guild:
                            db.mark_timer_complete(timer['id'])
                            continue
                        
                        channel = guild.get_channel(timer['channel_id'])
                        if not channel:
                            db.mark_timer_complete(timer['id'])
                            continue
                        
                        # Update the embed to show completion
                        if timer['message_id']:
                            try:
                                message = await channel.fetch_message(timer['message_id'])
                                
                                if message.embeds:
                                    embed = message.embeds[0]
                                    embed.color = discord.Color.green()
                                    embed.clear_fields()
                                    embed.add_field(
                                        name="✅ Timer Complete!",
                                        value=f"Ended <t:{int(timer['end_time'].timestamp())}:R>",
                                        inline=False
                                    )
                                    embed.set_footer(text=f"Timer ID: {timer['id']} • Finished")
                                    await message.edit(embed=embed)
                            except discord.NotFound:
                                pass
                            except Exception as e:
                                print(f"Error updating timer message: {e}")
                        
                        # Send completion notification
                        try:
                            user = await bot.fetch_user(timer['user_id'])
                            label_text = f" ({timer['label']})" if timer['label'] else ""
                            await channel.send(
                                f"⏰ Timer complete! {user.mention}{label_text}"
                            )
                        except Exception as e:
                            print(f"Error sending timer completion message: {e}")
                        
                        db.mark_timer_complete(timer['id'])
                        print(f"⏱️ Completed timer {timer['id']}")
                    
                    # Timer still running - update the embed
                    elif timer['message_id']:
                        try:
                            guild = bot.get_guild(timer['guild_id'])
                            if guild:
                                channel = guild.get_channel(timer['channel_id'])
                                if channel:
                                    try:
                                        message = await channel.fetch_message(timer['message_id'])
                                        
                                        if message.embeds:
                                            embed = message.embeds[0]
                                            embed.clear_fields()
                                            embed.add_field(
                                                name="Ends",
                                                value=f"<t:{int(timer['end_time'].timestamp())}:R> (<t:{int(timer['end_time'].timestamp())}:T>)",
                                                inline=False
                                            )
                                            await message.edit(embed=embed)
                                    except discord.NotFound:
                                        # Message was deleted, mark timer complete
                                        db.mark_timer_complete(timer['id'])
                                    except discord.HTTPException:
                                        # Rate limited or other HTTP error, skip this update
                                        pass
                        except Exception as e:
                            print(f"Error updating timer {timer['id']}: {e}")
                
                except Exception as e:
                    print(f"Error processing timer {timer.get('id', 'unknown')}: {e}")
        
        except Exception as e:
            print(f"Error in timer check: {e}")
            await asyncio.sleep(30)
