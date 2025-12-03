"""
Admin command group for server and database management
"""
import discord
from discord import app_commands
from database import db


class AdminGroup(app_commands.Group):
    """Admin commands for database management"""
    
    @app_commands.command(name="linkreplacement", description="Toggle automatic link replacement for this server")
    @app_commands.describe(enabled="Enable or disable automatic link replacement")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable link replacement", value=1),
        app_commands.Choice(name="Disable link replacement", value=0)
    ])
    @app_commands.default_permissions(administrator=True)
    async def link_replacement(self, interaction: discord.Interaction, enabled: int):
        """Toggle link replacement for the server (requires administrator permission)"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Update guild setting
            db.set_guild_link_replacement(
                guild_id=interaction.guild.id,
                enabled=bool(enabled),
                changed_by_user_id=interaction.user.id,
                changed_by_username=str(interaction.user)
            )
            
            status = "**enabled** ✅" if enabled else "**disabled** 🔕"
            await interaction.response.send_message(
                f"Link replacement {status}\n"
                f"The bot will {'now automatically fix' if enabled else 'no longer fix'} social media links "
                f"(Twitter/X, TikTok, Instagram, Reddit, etc.) in this server.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error updating link replacement setting: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating the link replacement setting. Please try again later.",
                ephemeral=True
            )
    
    @app_commands.command(name="loadboosterroles", description="Load existing booster roles into the database")
    @app_commands.default_permissions(administrator=True)
    async def load_booster_roles(self, interaction: discord.Interaction):
        """Scan server for existing booster roles and save them to database (requires administrator permission)"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        # Defer response since this might take a while
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            guild = interaction.guild
            roles_found = 0
            roles_saved = 0
            errors = 0
            
            # Build a report
            report_lines = []
            
            # Scan all members for boosters and their custom roles
            for member in guild.members:
                # Check if member is a booster
                if not member.premium_since:
                    continue
                
                # Find their custom role (only one member, not @everyone)
                personal_roles = [
                    role for role in member.roles 
                    if not role.is_default() 
                    and len(role.members) == 1
                ]
                
                if not personal_roles:
                    continue
                
                # Use the highest personal role by position
                role = max(personal_roles, key=lambda r: r.position)
                roles_found += 1
                
                try:
                    # Prepare role data
                    color_hex = f"#{role.color.value:06x}"
                    secondary_color_hex = f"#{role.secondary_color.value:06x}" if role.secondary_color else None
                    tertiary_color_hex = f"#{role.tertiary_color.value:06x}" if role.tertiary_color else None
                    icon_hash = role.icon.key if role.icon else None
                    icon_data = None
                    
                    # Try to get existing color type from database, default to 'solid'
                    existing_role = db.get_booster_role(member.id, guild.id)
                    color_type = existing_role['color_type'] if existing_role else 'solid'
                    
                    # Download icon data if it exists
                    if role.icon:
                        try:
                            icon_data = await role.icon.read()
                        except Exception as e:
                            print(f"Could not read icon for {member.display_name}: {e}")
                    
                    # Save to database (preserve existing color_type or default to 'solid')
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
                    
                    roles_saved += 1
                    icon_status = " (with icon)" if icon_data else ""
                    report_lines.append(f"✅ {member.display_name}: `{role.name}`{icon_status}")
                    
                except Exception as e:
                    errors += 1
                    report_lines.append(f"❌ {member.display_name}: Error - {str(e)[:50]}")
                    print(f"Error saving role for {member.display_name}: {e}")
            
            # Build summary message
            summary = f"**Booster Roles Scan Complete**\n\n"
            summary += f"📊 **Summary:**\n"
            summary += f"• Found: {roles_found} role(s)\n"
            summary += f"• Saved: {roles_saved} role(s)\n"
            summary += f"• Errors: {errors}\n\n"
            
            if report_lines:
                summary += "**Details:**\n" + "\n".join(report_lines[:20])  # Limit to 20 entries to avoid message length issues
                if len(report_lines) > 20:
                    summary += f"\n... and {len(report_lines) - 20} more"
            else:
                summary += "ℹ️ No custom booster roles found in this server."
            
            await interaction.followup.send(summary, ephemeral=True)
            
        except Exception as e:
            print(f"Error loading booster roles: {e}")
            await interaction.followup.send(
                f"❌ An error occurred while loading booster roles: {str(e)[:100]}",
                ephemeral=True
            )
    
    @app_commands.command(name="saveboosterrole", description="Manually save a booster role to the database")
    @app_commands.describe(
        role="The role to save",
        user="The user who owns the role (select from dropdown)",
        user_id="Alternative: Manually enter user ID (for users not in server)"
    )
    @app_commands.default_permissions(administrator=True)
    async def save_booster_role(self, interaction: discord.Interaction, role: discord.Role, user: discord.User = None, user_id: str = None):
        """Manually save a specific booster role to the database (requires administrator permission)"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        # Require either user or user_id
        if not user and not user_id:
            await interaction.response.send_message("❌ Please provide either a user (from dropdown) or a user_id.", ephemeral=True)
            return
        
        # Defer response
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Determine which user ID to use
            if user:
                uid = user.id
            else:
                # Convert user_id string to int
                try:
                    uid = int(user_id)
                except ValueError:
                    await interaction.followup.send(
                        f"❌ Invalid user ID format. Please provide a numeric user ID.",
                        ephemeral=True
                    )
                    return
            
            # Try to get member info (optional - just for booster status warning)
            member = interaction.guild.get_member(uid)
            booster_warning = ""
            if member and not member.premium_since:
                booster_warning = f"\n⚠️ Note: <@{uid}> is not currently a server booster."
            elif not member:
                booster_warning = f"\n⚠️ Note: User is not currently in the server."
            
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Prepare role data
            color_hex = f"#{role.color.value:06x}"
            secondary_color_hex = f"#{role.secondary_color.value:06x}" if role.secondary_color else None
            tertiary_color_hex = f"#{role.tertiary_color.value:06x}" if role.tertiary_color else None
            icon_hash = role.icon.key if role.icon else None
            icon_data = None
            
            # Auto-detect color type based on colors present
            if tertiary_color_hex:
                color_type = "holographic"
            elif secondary_color_hex:
                color_type = "gradient"
            else:
                color_type = "solid"
            
            # Download icon data if it exists
            if role.icon:
                try:
                    icon_data = await role.icon.read()
                except Exception as e:
                    print(f"Could not read icon for role {role.name}: {e}")
            
            # Save to database
            db.store_booster_role(
                user_id=uid,
                guild_id=interaction.guild.id,
                role_id=role.id,
                role_name=role.name,
                color_hex=color_hex,
                color_type=color_type,
                icon_hash=icon_hash,
                icon_data=icon_data,
                secondary_color_hex=secondary_color_hex,
                tertiary_color_hex=tertiary_color_hex
            )
            
            icon_status = " with icon" if icon_data else ""
            color_info = color_hex
            if secondary_color_hex:
                color_info += f", {secondary_color_hex}"
            if tertiary_color_hex:
                color_info += f", {tertiary_color_hex}"
            
            await interaction.followup.send(
                f"✅ Saved booster role for <@{uid}>\n"
                f"• Role: `{role.name}`\n"
                f"• Colors: {color_info} ({color_type}){icon_status}{booster_warning}",
                ephemeral=True
            )
            
        except Exception as e:
            print(f"Error saving booster role: {e}")
            await interaction.followup.send(
                f"❌ An error occurred while saving the booster role: {str(e)[:100]}",
                ephemeral=True
            )
    
    @app_commands.command(name="sql", description="Execute a SQL query (BOT OWNER ONLY)")
    @app_commands.describe(query="The SQL query to execute")
    async def execute_sql(self, interaction: discord.Interaction, query: str):
        """Execute a SQL query on the database (BOT OWNER ONLY)"""
        # Check if user is the bot owner
        app_info = await interaction.client.application_info()
        if interaction.user.id != app_info.owner.id:
            await interaction.response.send_message(
                "❌ This command is restricted to the bot owner only.",
                ephemeral=True
            )
            return
        
        # Defer response since query might take time
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Initialize database connection if needed
            if not db.connection_pool:
                db.init_pool()
            
            # Log the query execution
            print(f"🔍 SQL Query executed by {interaction.user} (ID: {interaction.user.id}):")
            print(f"   Query: {query}")
            
            # Determine if this is a SELECT query or a modification query
            is_select = query.strip().upper().startswith('SELECT')
            
            if is_select:
                # Execute SELECT query and fetch results
                results = db.execute_query(query)
                
                if not results:
                    await interaction.followup.send("✅ Query executed successfully. No results returned.", ephemeral=True)
                    return
                
                # Format results as a table
                response = f"✅ Query returned {len(results)} row(s):\n```\n"
                
                # Limit output to prevent message from being too long
                max_rows = 20
                for i, row in enumerate(results[:max_rows]):
                    response += f"{i+1}. {row}\n"
                
                if len(results) > max_rows:
                    response += f"... and {len(results) - max_rows} more row(s)\n"
                
                response += "```"
                
                # Discord message limit is 2000 characters
                if len(response) > 1900:
                    response = response[:1900] + "\n...\n```\n⚠️ Output truncated due to length"
                
                await interaction.followup.send(response, ephemeral=True)
            else:
                # Execute modification query (INSERT, UPDATE, DELETE, etc.)
                db.execute_query(query, fetch=False)
                await interaction.followup.send("✅ Query executed successfully.", ephemeral=True)
            
            print(f"   ✅ Query completed successfully")
            
        except Exception as e:
            error_msg = str(e)
            print(f"   ❌ Query failed: {error_msg}")
            await interaction.followup.send(
                f"❌ Error executing query:\n```\n{error_msg[:1800]}\n```",
                ephemeral=True
            )
    
    @app_commands.command(name="assignlvl0", description="Assign lvl 0 to all verified members without a level role")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def assign_lvl0(self, interaction: discord.Interaction):
        """Assign lvl 0 role to verified members who don't have any level role"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get role objects
            verified_role = discord.utils.get(interaction.guild.roles, name="verified")
            lvl0_role = discord.utils.get(interaction.guild.roles, name="lvl 0")
            
            if not verified_role:
                await interaction.followup.send("❌ No 'verified' role found in this server.", ephemeral=True)
                return
            
            if not lvl0_role:
                await interaction.followup.send("❌ No 'lvl 0' role found in this server.", ephemeral=True)
                return
            
            # Find members who need lvl 0
            assigned_count = 0
            errors = []
            
            for member in interaction.guild.members:
                # Check if they have verified role
                if verified_role in member.roles:
                    # Check if they have any lvl role
                    has_lvl_role = any(role.name.startswith("lvl ") for role in member.roles)
                    
                    if not has_lvl_role:
                        # They need lvl 0
                        try:
                            await member.add_roles(lvl0_role, reason=f"Manual lvl 0 assignment by {interaction.user}")
                            assigned_count += 1
                            print(f"[ADMIN] Assigned lvl 0 to {member.display_name}")
                        except Exception as e:
                            error_msg = f"{member.display_name}: {str(e)[:50]}"
                            errors.append(error_msg)
                            print(f"[ADMIN] Error assigning lvl 0 to {member.display_name}: {e}")
            
            # Build response
            response = f"✅ Assigned lvl 0 to **{assigned_count}** member(s)"
            
            if errors:
                response += f"\n\n⚠️ Failed to assign {len(errors)} member(s):"
                for error in errors[:5]:  # Show first 5 errors
                    response += f"\n- {error}"
                if len(errors) > 5:
                    response += f"\n... and {len(errors) - 5} more"
            
            await interaction.followup.send(response, ephemeral=True)
            
        except Exception as e:
            print(f"[ADMIN] Error in assign_lvl0 command: {e}")
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)[:200]}",
                ephemeral=True
            )
