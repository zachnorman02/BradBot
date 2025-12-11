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
    Handle role assignment logic based on configured role rules.
    When a member gains a role, check if it triggers any role rules
    and apply the corresponding role additions/removals.
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
        
        if not added_roles:
            return  # No roles were added, nothing to do
        
        # Get all role rules for this guild
        role_rules = db.get_role_rules(after.guild.id)
        
        # Check if any of the added roles trigger a rule
        for added_role_id in added_roles:
            for rule in role_rules:
                if rule['trigger_role_id'] == added_role_id:
                    trigger_role = after.guild.get_role(added_role_id)
                    print(f"[ROLE RULE] {after.display_name} gained {trigger_role.name if trigger_role else added_role_id}, applying rule '{rule['rule_name']}'")
                    
                    # Remove roles
                    for role_id in rule['roles_to_remove']:
                        role = after.guild.get_role(role_id)
                        if role and role in after.roles:
                            try:
                                await after.remove_roles(role, reason=f"Role rule '{rule['rule_name']}' triggered")
                                print(f"[ROLE RULE] Removed {role.name} from {after.display_name}")
                            except Exception as e:
                                print(f"[ROLE RULE] Error removing {role.name}: {e}")
                    
                    # Add roles (but only if they don't already have them)
                    for role_id in rule['roles_to_add']:
                        role = after.guild.get_role(role_id)
                        if role and role not in after.roles:
                            # Special case: Don't add "lvl 0" if user has a higher level role
                            if role.name == "lvl 0":
                                has_higher_level = any(r.name.startswith("lvl ") and r.name != "lvl 0" for r in after.roles)
                                if has_higher_level:
                                    print(f"[ROLE RULE] Skipped adding lvl 0 to {after.display_name} (has higher level)")
                                    continue
                            
                            try:
                                await after.add_roles(role, reason=f"Role rule '{rule['rule_name']}' triggered")
                                print(f"[ROLE RULE] Added {role.name} to {after.display_name}")
                            except Exception as e:
                                print(f"[ROLE RULE] Error adding {role.name}: {e}")
        
        # ===== ENFORCEMENT: Validate all role rules are satisfied =====
        # Refresh member object to get current roles after any rule applications
        try:
            after = await after.guild.fetch_member(after.id)
        except Exception as e:
            print(f"[ROLE RULE ENFORCEMENT] Could not refresh member: {e}")
            return
        
        # Check if user has any trigger roles and ensure the rules are properly applied
        after_role_ids = {r.id for r in after.roles}
        
        for rule in role_rules:
            trigger_role_id = rule['trigger_role_id']
            
            # If user has the trigger role, enforce the rule
            if trigger_role_id in after_role_ids:
                # Ensure roles_to_add are present
                for add_role_id in rule['roles_to_add']:
                    if add_role_id not in after_role_ids:
                        add_role = after.guild.get_role(add_role_id)
                        if add_role:
                            # Special case: Don't add "lvl 0" if user has a higher level role
                            if add_role.name == "lvl 0":
                                has_higher_level = any(r.name.startswith("lvl ") and r.name != "lvl 0" for r in after.roles)
                                if has_higher_level:
                                    print(f"[ROLE RULE ENFORCEMENT] Skipped adding lvl 0 to {after.display_name} (has higher level)")
                                    continue
                            
                            try:
                                await after.add_roles(add_role, reason=f"Role rule enforcement: '{rule['rule_name']}'")
                                print(f"[ROLE RULE ENFORCEMENT] Added {add_role.name} to {after.display_name}")
                            except Exception as e:
                                print(f"[ROLE RULE ENFORCEMENT] Error adding {add_role.name}: {e}")
                
                # Ensure roles_to_remove are not present
                for remove_role_id in rule['roles_to_remove']:
                    if remove_role_id in after_role_ids:
                        remove_role = after.guild.get_role(remove_role_id)
                        if remove_role:
                            try:
                                await after.remove_roles(remove_role, reason=f"Role rule enforcement: '{rule['rule_name']}'")
                                print(f"[ROLE RULE ENFORCEMENT] Removed {remove_role.name} from {after.display_name}")
                            except Exception as e:
                                print(f"[ROLE RULE ENFORCEMENT] Error removing {remove_role.name}: {e}")
    
    except Exception as e:
        print(f"[ROLE RULE] Error in handle_verified_role_logic: {e}")


# ============================================================================
# CHANNEL RESTRICTION AUTOMATION
# ============================================================================

async def handle_channel_restrictions(before: discord.Member, after: discord.Member):
    """
    Handle channel permission overwrites based on role changes.
    When a member gains a blocking role, deny them access to restricted channels.
    When a member loses a blocking role, remove the denial.
    """
    try:
        # Skip bots
        if after.bot:
            return
        
        # Get role changes
        before_role_ids = {role.id for role in before.roles}
        after_role_ids = {role.id for role in after.roles}
        added_roles = after_role_ids - before_role_ids
        removed_roles = before_role_ids - after_role_ids
        
        if not added_roles and not removed_roles:
            return  # No role changes
        
        # Get all channel restrictions for this guild
        restrictions = db.get_channel_restrictions(after.guild.id)
        
        if not restrictions:
            return  # No restrictions configured
        
        # Group restrictions by blocking role for efficiency
        from collections import defaultdict
        channels_by_role = defaultdict(list)
        for r in restrictions:
            channels_by_role[r['blocking_role_id']].append(r['channel_id'])
        
        # Handle added roles - block access to restricted channels
        for added_role_id in added_roles:
            if added_role_id in channels_by_role:
                for channel_id in channels_by_role[added_role_id]:
                    channel = after.guild.get_channel(channel_id)
                    if channel:
                        try:
                            await channel.set_permissions(
                                after,
                                view_channel=False,
                                reason=f"Channel restriction: {after.guild.get_role(added_role_id).name} role added"
                            )
                            print(f"[CHANNEL RESTRICTION] Blocked {after.display_name} from {channel.name}")
                        except Exception as e:
                            print(f"[CHANNEL RESTRICTION] Error blocking {after.display_name} from {channel.name}: {e}")
        
        # Handle removed roles - remove access blocks from restricted channels
        for removed_role_id in removed_roles:
            if removed_role_id in channels_by_role:
                for channel_id in channels_by_role[removed_role_id]:
                    channel = after.guild.get_channel(channel_id)
                    if channel:
                        # Check if they still have any other blocking roles for this channel
                        other_blocking_roles = [
                            r['blocking_role_id'] 
                            for r in restrictions 
                            if r['channel_id'] == channel_id and r['blocking_role_id'] in after_role_ids
                        ]
                        
                        if not other_blocking_roles:
                            # No other blocking roles, safe to remove overwrite
                            try:
                                await channel.set_permissions(
                                    after,
                                    overwrite=None,
                                    reason=f"Channel restriction removed: {after.guild.get_role(removed_role_id).name} role removed"
                                )
                                print(f"[CHANNEL RESTRICTION] Unblocked {after.display_name} from {channel.name}")
                            except Exception as e:
                                print(f"[CHANNEL RESTRICTION] Error unblocking {after.display_name} from {channel.name}: {e}")
    
    except Exception as e:
        print(f"[CHANNEL RESTRICTION] Error in handle_channel_restrictions: {e}")


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
        
        # Log task start
        log_id = db.log_task_start('daily_maintenance', details={'guild_count': len(bot.guilds)})
        
        try:
            guild_results = []
            
            for guild in bot.guilds:
                guild_log_id = db.log_task_start('daily_maintenance_guild', guild_id=guild.id)
                
                try:
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
                    
                    unverified_count = 0
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
                    
                    # Log guild success
                    db.log_task_complete(guild_log_id, 'success', details={
                        'booster_roles_enabled': booster_roles_enabled,
                        'verify_enabled': verify_enabled,
                        'unverified_kicks_enabled': unverified_kicks_enabled,
                        'unverified_count': unverified_count
                    })
                    
                    guild_results.append({'guild_id': guild.id, 'status': 'success'})
                    
                except Exception as e:
                    print(f"[DAILY TASK] Error processing guild {guild.name}: {e}")
                    db.log_task_complete(guild_log_id, 'error', error_message=str(e))
                    guild_results.append({'guild_id': guild.id, 'status': 'error', 'error': str(e)})
            
            print(f"[DAILY TASK] Midnight checks completed")
            
            # Log overall task completion
            success_count = sum(1 for r in guild_results if r['status'] == 'success')
            error_count = sum(1 for r in guild_results if r['status'] == 'error')
            db.log_task_complete(log_id, 'success', details={
                'guilds_processed': len(guild_results),
                'guilds_success': success_count,
                'guilds_error': error_count
            })
            
        except Exception as e:
            print(f"[DAILY TASK] Fatal error in maintenance check: {e}")
            db.log_task_complete(log_id, 'error', error_message=str(e))


# ============================================================================
# CONDITIONAL ROLE ASSIGNMENT HELPERS
# ============================================================================

def get_deferral_role_names(guild: discord.Guild, deferral_role_ids: list[int], user_role_ids: set[int]) -> list[str]:
    """Get names of deferral roles that the user has."""
    deferral_names = []
    for dr_id in deferral_role_ids:
        if dr_id in user_role_ids:
            dr = guild.get_role(dr_id)
            if dr:
                deferral_names.append(dr.name)
    return deferral_names


# ============================================================================
# MEMBER UPDATE HANDLER
# ============================================================================

async def handle_conditional_role_assignment(before: discord.Member, after: discord.Member):
    """Handle manual conditional role assignment with deferred logic.
    
    When a configured conditional role is manually assigned:
    - Check if user has any deferral roles from config
    - If yes: mark eligible but remove role (defer assignment)
    - If no: mark eligible and keep role (normal assignment)
    
    When roles are removed:
    - Check if user was marked eligible for any conditional roles
    - If user no longer has deferral roles: grant the conditional role
    
    On every role change:
    - Check if user has any conditional roles they shouldn't have
    - Remove conditional role if they now have deferral roles (catches cases where deferral role is added later)
    """
    try:
        before_role_ids = {role.id for role in before.roles}
        after_role_ids = {role.id for role in after.roles}
        added_role_ids = after_role_ids - before_role_ids
        removed_role_ids = before_role_ids - after_role_ids
        
        # Get all conditional role configs for this guild
        all_configs = db.get_all_conditional_role_configs(after.guild.id)
        
        # ===== SECTION 1: Handle conditional roles being added =====
        for added_role_id in added_role_ids:
            config = db.get_conditional_role_config(after.guild.id, added_role_id)
            if not config:
                # Not a conditional role being added, but check if it's a DEFERRAL role
                # that should remove any conditional roles the user has
                for check_config in all_configs:
                    conditional_role_id = check_config['role_id']
                    deferral_role_ids = check_config.get('deferral_role_ids', [])
                    
                    # If the added role is a deferral role for this conditional role
                    if added_role_id in deferral_role_ids and conditional_role_id in after_role_ids:
                        # User now has both the conditional role AND a deferral role
                        # Remove the conditional role
                        conditional_role = after.guild.get_role(conditional_role_id)
                        if conditional_role:
                            try:
                                await after.remove_roles(conditional_role, reason=f"User acquired deferral role, removing conditional role")
                                
                                # Mark as deferred
                                added_deferral_role = after.guild.get_role(added_role_id)
                                deferral_name = added_deferral_role.name if added_deferral_role else str(added_role_id)
                                
                                db.mark_conditional_role_eligible(
                                    after.guild.id,
                                    after.id,
                                    conditional_role_id,
                                    notes=f"Deferred: has deferral role(s): {deferral_name}"
                                )
                                
                                print(f"[CONDITIONAL ROLE] Removed {conditional_role.name} from {after.display_name} (gained deferral role: {deferral_name})")
                            except Exception as e:
                                print(f"[CONDITIONAL ROLE] Error removing conditional role after deferral role added: {e}")
                continue  # Not a conditional role being added, skip normal processing
            
            deferral_role_ids = config.get('deferral_role_ids', [])
            if not deferral_role_ids:
                # No deferral configured, mark eligible and keep role
                db.mark_conditional_role_eligible(
                    after.guild.id,
                    after.id,
                    added_role_id,
                    notes="Manually assigned, no deferral configured"
                )
                print(f"[CONDITIONAL ROLE] Approved manual assignment for {after.display_name} (role ID: {added_role_id})")
                continue
            
            # Check if user has any deferral roles
            user_role_ids = {r.id for r in after.roles}
            has_deferral_role = any(dr_id in user_role_ids for dr_id in deferral_role_ids)
            
            if has_deferral_role:
                # Get deferral role names for logging
                deferral_names = get_deferral_role_names(after.guild, deferral_role_ids, user_role_ids)
                
                # Mark eligible but remove the role (defer assignment)
                db.mark_conditional_role_eligible(
                    after.guild.id,
                    after.id,
                    added_role_id,
                    notes=f"Deferred: has deferral role(s): {', '.join(deferral_names)}"
                )
                
                added_role = after.guild.get_role(added_role_id)
                if added_role:
                    try:
                        await after.remove_roles(added_role, reason=f"Assignment deferred: user has deferral roles ({', '.join(deferral_names)})")
                        print(f"[CONDITIONAL ROLE] Deferred assignment for {after.display_name} (role: {added_role.name}, has deferral roles: {', '.join(deferral_names)})")
                    except Exception as e:
                        print(f"[CONDITIONAL ROLE] Error removing role for deferred assignment: {e}")
            else:
                # Normal assignment - mark eligible and keep role
                db.mark_conditional_role_eligible(
                    after.guild.id,
                    after.id,
                    added_role_id,
                    notes="Manually assigned and criteria met"
                )
                added_role = after.guild.get_role(added_role_id)
                role_name = added_role.name if added_role else str(added_role_id)
                print(f"[CONDITIONAL ROLE] Approved manual assignment for {after.display_name} (role: {role_name})")
        
        # ===== SECTION 2: Handle roles being removed - grant deferred conditional roles =====
        if removed_role_ids:
            for config in all_configs:
                conditional_role_id = config['role_id']
                deferral_role_ids = config.get('deferral_role_ids', [])
                
                if not deferral_role_ids:
                    continue  # No deferral configured, skip
                
                # Check if user is marked as eligible for this conditional role
                eligibility = db.get_conditional_role_eligibility(
                    after.guild.id,
                    after.id,
                    conditional_role_id
                )
                
                if not eligibility:
                    continue  # User not tracked for deferral, skip
                
                # Check if user already has the conditional role
                if conditional_role_id in after_role_ids:
                    continue  # Already has the role, skip
                
                # Check if user still has any deferral roles
                user_role_ids = {r.id for r in after.roles}
                has_deferral_role = any(dr_id in user_role_ids for dr_id in deferral_role_ids)
                
                if not has_deferral_role:
                    # User is eligible, doesn't have deferral roles anymore, and doesn't have the conditional role
                    # Grant the conditional role
                    conditional_role = after.guild.get_role(conditional_role_id)
                    if conditional_role:
                        try:
                            await after.add_roles(conditional_role, reason="Deferral criteria no longer met, granting conditional role")
                            
                            # Remove from deferral tracking
                            db.unmark_conditional_role_eligible(
                                after.guild.id,
                                after.id,
                                conditional_role_id
                            )
                            
                            print(f"[CONDITIONAL ROLE] Granted deferred role {conditional_role.name} to {after.display_name} (deferral criteria no longer met)")
                        except Exception as e:
                            print(f"[CONDITIONAL ROLE] Error granting deferred role: {e}")
        
        # ===== SECTION 3: Enforcement - remove conditional roles if user has deferral roles =====
        # This catches cases where a deferral role is added after the conditional role was assigned
        for config in all_configs:
            conditional_role_id = config['role_id']
            deferral_role_ids = config.get('deferral_role_ids', [])
            
            if not deferral_role_ids:
                continue  # No deferral configured, skip
            
            # Check if user currently has this conditional role
            if conditional_role_id not in after_role_ids:
                continue  # User doesn't have this conditional role, skip
            
            # Check if user has any deferral roles
            user_role_ids = {r.id for r in after.roles}
            has_deferral_role = any(dr_id in user_role_ids for dr_id in deferral_role_ids)
            
            if has_deferral_role:
                # User has conditional role but now has deferral role(s) - remove conditional role
                deferral_names = get_deferral_role_names(after.guild, deferral_role_ids, user_role_ids)
                
                conditional_role = after.guild.get_role(conditional_role_id)
                if conditional_role:
                    try:
                        await after.remove_roles(conditional_role, reason=f"User now has deferral roles ({', '.join(deferral_names)}), removing conditional role")
                        
                        # Mark as eligible but deferred
                        db.mark_conditional_role_eligible(
                            after.guild.id,
                            after.id,
                            conditional_role_id,
                            notes=f"Deferred: gained deferral role(s): {', '.join(deferral_names)}"
                        )
                        
                        print(f"[CONDITIONAL ROLE] Removed {conditional_role.name} from {after.display_name} (gained deferral roles: {', '.join(deferral_names)})")
                    except Exception as e:
                        print(f"[CONDITIONAL ROLE] Error removing conditional role after deferral role added: {e}")
    
    except Exception as e:
        print(f"[CONDITIONAL ROLE] Error in handle_conditional_role_assignment: {e}")


async def on_member_update_handler(before: discord.Member, after: discord.Member):
    """
    Handle member updates:
    - Verified role assignment and level 0 logic
    - Conditional role manual assignment logic (with deferral)
    - Channel restriction enforcement
    - Booster role creation/restoration/deletion
    """
    # Always handle verified role logic
    await handle_verified_role_logic(before, after)
    
    # Handle conditional role manual assignments
    await handle_conditional_role_assignment(before, after)
    
    # Handle channel restrictions
    await handle_channel_restrictions(before, after)
    
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
