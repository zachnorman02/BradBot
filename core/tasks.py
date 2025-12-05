"""
Background tasks for BradBot
"""
import discord
import datetime as dt
import asyncio
from database import db


# ============================================================================
# VERIFIED ROLE AUTOMATION
# ============================================================================

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


# ============================================================================
# BOOSTER ROLE AUTOMATION
# ============================================================================

async def _save_booster_role(member: discord.Member, role: discord.Role):
    """Save a booster role configuration to the database"""
    try:
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
        existing_role = db.get_booster_role(member.id, member.guild.id)
        color_type = existing_role['color_type'] if existing_role else 'solid'
        
        db.store_booster_role(
            user_id=member.id,
            guild_id=member.guild.id,
            role_id=role.id,
            role_name=role.name,
            color_hex=color_hex,
            color_type=color_type,
            icon_hash=icon_hash,
            icon_data=icon_data,
            secondary_color_hex=secondary_color_hex,
            tertiary_color_hex=tertiary_color_hex
        )
        return True
    except Exception as e:
        print(f"Error saving role configuration for {member.display_name}: {e}")
        return False


async def _restore_or_create_booster_role(member: discord.Member) -> bool:
    """Restore a saved booster role or create a new one"""
    try:
        db_role_data = db.get_booster_role(member.id, member.guild.id)
        
        if db_role_data:
            # Try to find existing role
            existing_role = None
            if db_role_data.get('role_id'):
                existing_role = member.guild.get_role(db_role_data['role_id'])
            
            if existing_role:
                # Role still exists! Just assign it back
                await member.add_roles(existing_role, reason="Re-assigning existing booster role")
                print(f"✅ Re-assigned existing booster role '{existing_role.name}' to {member.display_name}")
                return True
            else:
                # Role was deleted, recreate from saved configuration
                primary_color = discord.Color(int(db_role_data['color_hex'].replace('#', ''), 16))
                secondary_color = None
                tertiary_color = None
                
                if db_role_data.get('secondary_color_hex'):
                    secondary_color = discord.Color(int(db_role_data['secondary_color_hex'].replace('#', ''), 16))
                if db_role_data.get('tertiary_color_hex'):
                    tertiary_color = discord.Color(int(db_role_data['tertiary_color_hex'].replace('#', ''), 16))
                
                # Create role with saved configuration
                restored_role = await member.guild.create_role(
                    name=db_role_data['role_name'],
                    color=primary_color,
                    secondary_color=secondary_color,
                    tertiary_color=tertiary_color,
                    reason=f"Auto-restoring booster role for {member.display_name}"
                )
                
                # Set icon if it exists
                if db_role_data['icon_data'] and "ROLE_ICONS" in member.guild.features:
                    try:
                        await restored_role.edit(display_icon=db_role_data['icon_data'])
                    except Exception as e:
                        print(f"Could not restore role icon for {member.display_name}: {e}")
                
                # Assign to user
                await member.add_roles(restored_role, reason="Auto-restoring booster role")
                
                # Update role_id in database
                db.update_booster_role_id(member.id, member.guild.id, restored_role.id)
                
                print(f"✅ Recreated and assigned booster role '{db_role_data['role_name']}' for {member.display_name}")
                return True
        else:
            # No saved role - create a new default role
            new_role = await member.guild.create_role(
                name=member.name,
                color=discord.Color.random(),
                reason=f"Auto-creating booster role for new booster {member.name}"
            )
            
            # Position it above the user's current highest role
            try:
                user_top_role = member.top_role
                await new_role.edit(position=user_top_role.position + 1)
            except Exception as e:
                print(f"Could not position role: {e}")
            
            # Assign to user
            await member.add_roles(new_role, reason="Auto-creating booster role")
            
            # Save to database
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
                user_id=member.id,
                guild_id=member.guild.id,
                role_id=new_role.id,
                role_name=new_role.name,
                color_hex=color_hex,
                color_type=color_type,
                icon_hash=None,
                icon_data=None,
                secondary_color_hex=secondary_color_hex,
                tertiary_color_hex=tertiary_color_hex
            )
            
            print(f"✅ Auto-created new booster role '{new_role.name}' for {member.display_name}")
            return True
            
    except Exception as e:
        print(f"Error restoring/creating booster role for {member.display_name}: {e}")
        return False


async def handle_booster_stopped(member: discord.Member):
    """Handle when a member stops boosting - save and delete their role"""
    try:
        # Find custom roles (only one member, not @everyone)
        personal_roles = [role for role in member.roles if not role.is_default() and len(role.members) == 1]
        
        if personal_roles:
            for role in personal_roles:
                # Save role configuration
                if await _save_booster_role(member, role):
                    print(f"💾 Saved booster role configuration for {member.display_name}")
                    
                    # Delete the role
                    try:
                        await role.delete(reason=f"{member.display_name} stopped boosting - role saved to database")
                        print(f"🗑️ Deleted booster role '{role.name}' from {member.display_name}")
                    except Exception as e:
                        print(f"Error deleting role for {member.display_name}: {e}")
    except Exception as e:
        print(f"Error processing booster status loss for {member.display_name}: {e}")


async def handle_booster_started(member: discord.Member):
    """Handle when a member starts boosting - restore or create their role"""
    await _restore_or_create_booster_role(member)


# ============================================================================
# DAILY MAINTENANCE TASKS
# ============================================================================

async def _check_booster_roles_for_guild(guild: discord.Guild):
    """Check and save booster roles for non-boosters in a guild"""
    for member in guild.members:
        # Skip bots
        if member.bot:
            continue
        
        # Find custom roles (only one member, not @everyone)
        personal_roles = [role for role in member.roles if not role.is_default() and len(role.members) == 1]
        
        # Check if user has custom roles but is NOT a booster (lost booster status)
        if personal_roles and not member.premium_since:
            # Only save if they have a booster role in the database (meaning they were previously a booster)
            existing_role = db.get_booster_role(member.id, guild.id)
            if existing_role:
                # Use the highest personal role by position
                role = max(personal_roles, key=lambda r: r.position)
                if await _save_booster_role(member, role):
                    print(f"💾 [Daily scan] Updated booster role configuration for {member.display_name}")


async def _check_verified_roles_for_guild(guild: discord.Guild, verified_role, lvl0_role):
    """Assign lvl 0 to verified members who don't have a level role"""
    for member in guild.members:
        # Skip bots
        if member.bot:
            continue
        
        # Check if they have verified role but no lvl role
        if verified_role and verified_role in member.roles and lvl0_role:
            has_lvl_role = any(role.name.startswith("lvl ") for role in member.roles)
            
            if not has_lvl_role:
                try:
                    await member.add_roles(lvl0_role, reason="Daily check - assigning missing lvl 0 to verified user")
                    print(f"[DAILY TASK] Assigned lvl 0 to {member.display_name}")
                except Exception as e:
                    print(f"[DAILY TASK] Error assigning lvl 0 to {member.display_name}: {e}")


async def _check_unverified_kicks_for_guild(guild: discord.Guild, unverified_role, verification_category, now):
    """Kick unverified users who have been members for 30+ days"""
    for member in guild.members:
        # Skip bots or members without the unverified role
        if member.bot or not unverified_role or unverified_role not in member.roles:
            continue
        
        # Check how long they've been a member
        if not member.joined_at:
            continue
        
        days_since_join = (now - member.joined_at).days
        print(f"[DAILY TASK] Checking {member.display_name}: unverified for {days_since_join} days (joined: {member.joined_at.isoformat()})")
        
        if days_since_join >= 30:
            # Check if they're in a verification ticket
            in_verification_ticket = False
            
            if verification_category:
                for channel in verification_category.channels:
                    if isinstance(channel, discord.TextChannel) and channel.name.startswith("ticket-"):
                        permissions = channel.permissions_for(member)
                        if permissions.read_messages:
                            in_verification_ticket = True
                            print(f"[DAILY TASK] {member.display_name} is in ticket: {channel.name}")
                            break
            
            # Kick if not in a verification ticket
            if not in_verification_ticket:
                try:
                    print(f"[DAILY TASK] Attempting to kick {member.display_name} (unverified for {days_since_join} days)")
                    await member.kick(reason=f"Unverified for {days_since_join} days with no active verification ticket")
                    print(f"[DAILY TASK] ✅ Successfully kicked {member.display_name}")
                except Exception as e:
                    print(f"[DAILY TASK] ❌ Error kicking {member.display_name}: {e}")
            else:
                print(f"[DAILY TASK] Skipping {member.display_name} - in verification ticket")


async def daily_maintenance_check(bot):
    """
    Daily task that runs at midnight UTC to:
    - Save booster roles for users who lost booster status
    - Assign lvl 0 to verified users without a level role
    - Kick unverified users after 30 days
    """
    await bot.wait_until_ready()
    await asyncio.sleep(5)  # Give extra time for guild members to fully load
    
    while not bot.is_closed():
        now = dt.datetime.now(dt.timezone.utc)
        next_run = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        wait_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        
        print(f"[DAILY TASK] Running midnight checks...")
        
        for guild in bot.guilds:
            # Get role objects for this guild
            verified_role = discord.utils.get(guild.roles, name="verified")
            lvl0_role = discord.utils.get(guild.roles, name="lvl 0")
            unverified_role = discord.utils.get(guild.roles, name="unverified")
            verification_category = discord.utils.get(guild.categories, name="verification")
            
            # Check guild automation settings
            booster_roles_enabled = db.get_guild_setting(guild.id, 'booster_roles_enabled', 'true').lower() == 'true'
            verify_enabled = db.get_guild_setting(guild.id, 'verify_roles_enabled', 'true').lower() == 'true'
            unverified_kicks_enabled = db.get_guild_setting(guild.id, 'unverified_kicks_enabled', 'true').lower() == 'true'
            
            # Debug logging
            print(f"[DAILY TASK] Guild: {guild.name}")
            print(f"[DAILY TASK] - Roles: verified={verified_role is not None}, lvl0={lvl0_role is not None}, unverified={unverified_role is not None}")
            print(f"[DAILY TASK] - Settings: booster_roles={booster_roles_enabled}, verify_roles={verify_enabled}, unverified_kicks={unverified_kicks_enabled}")
            
            if unverified_role:
                unverified_count = len([m for m in guild.members if not m.bot and unverified_role in m.roles])
                print(f"[DAILY TASK] - Unverified members: {unverified_count}")
            
            # Run enabled checks
            if booster_roles_enabled:
                await _check_booster_roles_for_guild(guild)
            
            if verify_enabled:
                await _check_verified_roles_for_guild(guild, verified_role, lvl0_role)
            
            if unverified_kicks_enabled:
                await _check_unverified_kicks_for_guild(guild, unverified_role, verification_category, now)
        
        print(f"[DAILY TASK] Midnight checks completed")


# ============================================================================
# MEMBER UPDATE HANDLER
# ============================================================================

async def on_member_update_handler(before: discord.Member, after: discord.Member):
    """
    Handle member updates:
    - Verified role assignment and level 0 logic
    - Booster role creation/restoration/deletion
    """
    # Always handle verified role logic
    await handle_verified_role_logic(before, after)
    
    # Check if booster role automation is enabled
    booster_roles_enabled = db.get_guild_setting(after.guild.id, 'booster_roles_enabled', 'true').lower() == 'true'
    if not booster_roles_enabled:
        return
    
    # Handle booster status changes
    if before.premium_since and not after.premium_since:
        # Member stopped boosting
        await handle_booster_stopped(after)
    elif not before.premium_since and after.premium_since:
        # Member started boosting
        await handle_booster_started(after)


# ============================================================================
# POLL AUTO-CLOSE TASK
# ============================================================================

async def poll_auto_close_check(bot):
    """Background task to check for polls that should auto-close based on time"""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            await asyncio.sleep(60)  # Check every minute
            
            if not db.connection_pool:
                db.init_pool()
            
            # Get all active polls with expired close_at times
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
                        db.close_poll(poll_id)
                        
                        # Update the message to show closed status
                        if message_id:
                            guild = bot.get_guild(guild_id)
                            if guild:
                                channel = guild.get_channel(channel_id)
                                if channel:
                                    try:
                                        message = await channel.fetch_message(message_id)
                                        
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


# ============================================================================
# REMINDER TASK
# ============================================================================

async def reminder_check(bot):
    """Background task to check for and send pending reminders"""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            await asyncio.sleep(30)  # Check every 30 seconds
            
            pending = db.get_pending_reminders()
            
            for reminder in pending:
                try:
                    user = await bot.fetch_user(reminder['user_id'])
                    if not user:
                        db.mark_reminder_sent(reminder['id'])
                        continue
                    
                    message = reminder['message']
                    sent = False
                    
                    # Try to send in the original channel first
                    if reminder['guild_id'] and reminder['channel_id']:
                        guild = bot.get_guild(reminder['guild_id'])
                        if guild:
                            channel = guild.get_channel(reminder['channel_id'])
                            if channel:
                                try:
                                    await channel.send(f"⏰ **Reminder for {user.mention}**\n{message}")
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
                            
                            await user.send(f"⏰ **Reminder**\n{message}{guild_name}")
                            sent = True
                        except discord.Forbidden:
                            pass
                    
                    db.mark_reminder_sent(reminder['id'])
                    
                    if sent:
                        print(f"⏰ Sent reminder {reminder['id']} to {user}")
                    else:
                        print(f"⏰ Could not deliver reminder {reminder['id']} (channel and DM failed)")
                
                except Exception as e:
                    print(f"Error sending reminder {reminder['id']}: {e}")
                    db.mark_reminder_sent(reminder['id'])  # Mark sent to avoid retry loops
        
        except Exception as e:
            print(f"Error in reminder check: {e}")
            await asyncio.sleep(30)


# ============================================================================
# TIMER TASK
# ============================================================================

async def timer_check(bot):
    """Background task to update and complete timers"""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            await asyncio.sleep(30)  # Check every 30 seconds
            
            active_timers = db.get_active_timers()
            now = dt.datetime.now(dt.timezone.utc)
            
            for timer in active_timers:
                try:
                    guild = bot.get_guild(timer['guild_id'])
                    if not guild:
                        db.mark_timer_complete(timer['id'])
                        continue
                    
                    channel = guild.get_channel(timer['channel_id'])
                    if not channel:
                        db.mark_timer_complete(timer['id'])
                        continue
                    
                    # Check if timer is complete
                    if timer['end_time'] <= now:
                        # Update embed to show completion
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
                            await channel.send(f"⏰ Timer complete! {user.mention}{label_text}")
                        except Exception as e:
                            print(f"Error sending timer completion message: {e}")
                        
                        db.mark_timer_complete(timer['id'])
                        print(f"⏱️ Completed timer {timer['id']}")
                    
                    # Timer still running - update the embed
                    elif timer['message_id']:
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
                            db.mark_timer_complete(timer['id'])  # Message deleted
                        except discord.HTTPException:
                            pass  # Rate limited, skip this update
                        except Exception as e:
                            print(f"Error updating timer {timer['id']}: {e}")
                
                except Exception as e:
                    print(f"Error processing timer {timer.get('id', 'unknown')}: {e}")
        
        except Exception as e:
            print(f"Error in timer check: {e}")
            await asyncio.sleep(30)


# ============================================================================
# LEGACY ALIAS (for backwards compatibility)
# ============================================================================

# Keep the old function name as an alias
daily_booster_role_check = daily_maintenance_check
