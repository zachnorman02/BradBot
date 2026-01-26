"""
Booster role and booster-related command groups and helpers
"""
import discord
from discord import app_commands
import aiohttp
from database import db
from typing import Optional


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


async def _ensure_role_position(role: discord.Role, bot_member: discord.Member) -> None:
    """Place personal booster roles just under the counting penalty role if present, else above booster role, while staying under the bot."""
    guild = role.guild
    target = None

    try:
        # Prefer just below the counting penalty role if configured
        config = db.get_counting_config(guild.id)
        if config and config.get("idiot_role_id"):
            idiot_role = guild.get_role(config["idiot_role_id"])
            if idiot_role and idiot_role.position is not None:
                target = max(1, idiot_role.position - 1)
    except Exception as e:
        print(f"[BOOSTER ROLE] Could not read counting config: {e}")

    if target is None:
        booster_role = guild.premium_subscriber_role
        if booster_role and booster_role.position is not None:
            target = booster_role.position + 1

    # Never place above the bot's highest role (or equal), or Discord will reject edits.
    bot_top = bot_member.top_role.position if bot_member and bot_member.top_role else None
    if bot_top is not None:
        if target is None:
            target = max(1, bot_top - 1)
        else:
            target = min(target, max(1, bot_top - 1))

    # If we couldn't compute a target, bail quietly.
    if target is None:
        return

    try:
        if role.position != target:
            await role.edit(position=target, reason="Place booster role under bot for management")
    except Exception as e:
        print(f"[BOOSTER ROLE] Could not adjust position for {role.name}: {e}")


async def get_or_create_booster_role(interaction: discord.Interaction, db_role_data: dict = None):
    """Get existing booster role or create/restore from database"""
    # Find existing custom role(s) (only they have it, not @everyone)
    personal_roles = [
        role for role in interaction.user.roles 
        if not role.is_default() 
        and len(role.members) == 1
    ]
    
    # Use the highest personal role by position
    personal_role = max(personal_roles, key=lambda r: r.position) if personal_roles else None
    
    # If no role exists, check database for saved role
    if not personal_role and db_role_data:
        # Restore role from database
        try:
            primary_color = discord.Color(int(db_role_data['color_hex'].replace('#', ''), 16))
            secondary_color = None
            tertiary_color = None
            
            if db_role_data.get('secondary_color_hex'):
                secondary_color = discord.Color(int(db_role_data['secondary_color_hex'].replace('#', ''), 16))
            if db_role_data.get('tertiary_color_hex'):
                tertiary_color = discord.Color(int(db_role_data['tertiary_color_hex'].replace('#', ''), 16))
            
            # Create role with saved configuration
            personal_role = await interaction.guild.create_role(
                name=db_role_data['role_name'],
                color=primary_color,
                secondary_color=secondary_color,
                tertiary_color=tertiary_color,
                reason="Restoring saved booster role"
            )
            await _ensure_role_position(personal_role, interaction.guild.me)
            
            # Set icon if it exists
            if db_role_data['icon_data'] and "ROLE_ICONS" in interaction.guild.features:
                try:
                    await personal_role.edit(display_icon=db_role_data['icon_data'])
                except Exception as e:
                    print(f"Could not restore role icon: {e}")
            
            # Assign to user
            await interaction.user.add_roles(personal_role, reason="Restoring saved booster role")
            
            # Update role_id in database
            db.update_booster_role_id(interaction.user.id, interaction.guild.id, personal_role.id)
            
        except Exception as e:
            print(f"Error restoring role from database: {e}")
            return None
    
    # If still no role, create a default one
    if not personal_role:
        try:
            personal_role = await interaction.guild.create_role(
                name=f"{interaction.user.display_name}'s Role",
                reason="Booster role customization"
            )
            await _ensure_role_position(personal_role, interaction.guild.me)
            await interaction.user.add_roles(personal_role, reason="Booster role customization")
        except Exception as e:
            print(f"Error creating new role: {e}")
            return None
    else:
        # Ensure position is still under the bot in case server roles moved
        await _ensure_role_position(personal_role, interaction.guild.me)
        # Restore saved icon if the role is missing one but DB has data and guild supports role icons
        if db_role_data and not personal_role.icon and db_role_data.get("icon_data") and "ROLE_ICONS" in interaction.guild.features:
            try:
                await personal_role.edit(display_icon=db_role_data["icon_data"])
            except Exception as e:
                print(f"[BOOSTER ROLE] Could not restore icon onto existing role: {e}")
    
    return personal_role


async def restore_member_booster_role(
    guild: discord.Guild,
    member: discord.Member,
    db_role_data: dict,
    reason: str = "Restore booster role",
    target_role: Optional[discord.Role] = None,
):
    """Restore or recreate a member's booster role using saved DB data. If target_role is provided, apply to that role."""
    bot_member = guild.me

    if target_role:
        personal_role = target_role
    else:
        personal_roles = [
            role for role in member.roles
            if not role.is_default()
            and len(role.members) == 1
        ]
        personal_role = max(personal_roles, key=lambda r: r.position) if personal_roles else None

    try:
        primary_color = discord.Color(int(db_role_data['color_hex'].replace('#', ''), 16))
        secondary_color = discord.Color(int(db_role_data['secondary_color_hex'].replace('#', ''), 16)) if db_role_data.get('secondary_color_hex') else None
        tertiary_color = discord.Color(int(db_role_data['tertiary_color_hex'].replace('#', ''), 16)) if db_role_data.get('tertiary_color_hex') else None
    except Exception as e:
        print(f"[BOOSTER ROLE] Invalid color data in DB for user {member.id}: {e}")
        primary_color = discord.Color.default()
        secondary_color = None
        tertiary_color = None

    if not personal_role:
        try:
            personal_role = await guild.create_role(
                name=db_role_data.get('role_name') or f"{member.display_name}'s Role",
                color=primary_color,
                secondary_color=secondary_color,
                tertiary_color=tertiary_color,
                reason=reason
            )
            await _ensure_role_position(personal_role, bot_member)
            await member.add_roles(personal_role, reason=reason)
            db.update_booster_role_id(member.id, guild.id, personal_role.id)
        except Exception as e:
            print(f"[BOOSTER ROLE] Failed to create role for {member}: {e}")
            return None
    else:
        # Ensure role has correct colors and position
        try:
            await personal_role.edit(
                color=primary_color,
                secondary_color=secondary_color,
                tertiary_color=tertiary_color,
                reason=reason
            )
        except Exception as e:
            print(f"[BOOSTER ROLE] Could not edit colors for {personal_role}: {e}")

        await _ensure_role_position(personal_role, bot_member)
        # Make sure the member has this role
        if personal_role not in member.roles:
            try:
                await member.add_roles(personal_role, reason=reason)
            except Exception as e:
                print(f"[BOOSTER ROLE] Could not assign provided role to {member}: {e}")

    # Restore icon if saved and supported
    if db_role_data.get("icon_data") and "ROLE_ICONS" in guild.features:
        try:
            await personal_role.edit(display_icon=db_role_data["icon_data"])
        except Exception as e:
            print(f"[BOOSTER ROLE] Could not restore icon for {personal_role}: {e}")

    return personal_role


async def save_role_to_db(user_id: int, guild_id: int, role: discord.Role):
    """Save role configuration to database. Auto-detects color_type."""
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
        
        # Auto-detect color type
        if tertiary_color_hex:
            color_type = "holographic"
        elif secondary_color_hex:
            color_type = "gradient"
        else:
            color_type = "solid"
        
        db.store_booster_role(
            user_id=user_id,
            guild_id=guild_id,
            role_id=role.id,
            role_name=role.name,
            color_hex=color_hex,
            color_type=color_type,
            icon_hash=icon_hash,
            icon_data=icon_data,
            secondary_color_hex=secondary_color_hex,
            tertiary_color_hex=tertiary_color_hex
        )
    except Exception as e:
        print(f"Error saving role to database: {e}")


# ============================================================================
# COMMAND GROUPS
# ============================================================================

class BoosterRoleGroup(app_commands.Group):
    """Booster role customization commands"""
    
    @app_commands.command(name="restore", description="Restore your booster role (recreate if missing and reapply saved icon/colors)")
    async def restore(self, interaction: discord.Interaction):
        """Force re-fetch/create the personal booster role and reapply saved data (icon/colors)."""
        if not any(role.is_premium_subscriber() for role in interaction.user.roles):
            await interaction.response.send_message("❌ This command is only available to server boosters!", ephemeral=True)
            return

        db_role_data = db.get_booster_role(interaction.user.id, interaction.guild.id)
        if not db_role_data:
            await interaction.response.send_message("❌ No saved booster role data found.", ephemeral=True)
            return

        role = await get_or_create_booster_role(interaction, db_role_data)
        if not role:
            await interaction.response.send_message("❌ Could not restore your booster role.", ephemeral=True)
            return

        # If the role exists but still missing icon, try again explicitly
        if db_role_data.get("icon_data") and "ROLE_ICONS" in interaction.guild.features:
            try:
                await role.edit(display_icon=db_role_data["icon_data"])
            except Exception as e:
                print(f"[BOOSTER ROLE] Restore icon failed: {e}")

        await interaction.response.send_message(
            f"✅ Booster role restored: {role.mention}\n"
            f"• Name: {role.name}\n"
            f"• Color type: {db_role_data.get('color_type', 'solid')}\n"
            f"• Icon: {'set' if db_role_data.get('icon_data') else 'none saved'}",
            ephemeral=True
        )

    @app_commands.command(name="color", description="Set your booster role color: solid, gradient, or holographic")
    @app_commands.describe(
        style="Color style type",
        hex="Primary color (hex code like #FF0000)",
        hex2="Secondary color for gradient/holographic (hex code like #00FF00)",
        hex3="Tertiary color for holographic only (hex code like #0000FF)"
    )
    @app_commands.choices(style=[
        app_commands.Choice(name="Solid", value="solid"),
        app_commands.Choice(name="Gradient", value="gradient"),
        app_commands.Choice(name="Holographic", value="holographic")
    ])
    async def color(self, interaction: discord.Interaction, style: str = "solid", hex: str = None, hex2: str = None, hex3: str = None):
        # Check if user is a booster
        if not any(role.is_premium_subscriber() for role in interaction.user.roles):
            await interaction.response.send_message("❌ This command is only available to server boosters!", ephemeral=True)
            return
        
        # Check database for saved role first
        db_role_data = db.get_booster_role(interaction.user.id, interaction.guild.id)
        
        # Get or create/restore booster role
        highest_role = await get_or_create_booster_role(interaction, db_role_data)
        if not highest_role:
            await interaction.response.send_message("❌ Failed to create or find your booster role.", ephemeral=True)
            return
        
        # Generate color based on style and hex values
        primary_color = None
        secondary_color = None
        tertiary_color = None
        description = ""
        
        if style == "solid":
            if hex:
                try:
                    primary_color = discord.Color(int(hex.replace('#', ''), 16))
                    description = f"Solid color: {hex}"
                except ValueError:
                    await interaction.response.send_message("❌ Invalid hex color format. Use format like #FF0000", ephemeral=True)
                    return
            else:
                primary_color = discord.Color.random()
                description = f"Random solid color: #{primary_color.value:06X}"
        
        elif style == "gradient":
            # Gradient requires primary and secondary colors
            if hex:
                try:
                    primary_color = discord.Color(int(hex.replace('#', ''), 16))
                except ValueError:
                    await interaction.response.send_message("❌ Invalid primary hex color format. Use format like #FF0000", ephemeral=True)
                    return
            else:
                primary_color = discord.Color.random()
            
            if hex2:
                try:
                    secondary_color = discord.Color(int(hex2.replace('#', ''), 16))
                except ValueError:
                    await interaction.response.send_message("❌ Invalid secondary hex color format. Use format like #00FF00", ephemeral=True)
                    return
            else:
                # Generate a complementary color
                secondary_color = discord.Color.random()
            
            description = f"Gradient: #{primary_color.value:06X} → #{secondary_color.value:06X}"
        
        elif style == "holographic":
            # Holographic uses specific Discord values or custom ones
            if hex and hex2 and hex3:
                try:
                    primary_color = discord.Color(int(hex.replace('#', ''), 16))
                    secondary_color = discord.Color(int(hex2.replace('#', ''), 16))
                    tertiary_color = discord.Color(int(hex3.replace('#', ''), 16))
                    description = f"Holographic: #{primary_color.value:06X}, #{secondary_color.value:06X}, #{tertiary_color.value:06X}"
                except ValueError:
                    await interaction.response.send_message("❌ Invalid hex color format. Use format like #FF0000", ephemeral=True)
                    return
            else:
                # Use Discord's default holographic values
                primary_color = discord.Color(11127295)   # 0xA9D9FF
                secondary_color = discord.Color(16759788) # 0xFFADDC
                tertiary_color = discord.Color(16761760)  # 0xFFB5A0
                description = f"Holographic (Discord default)"
        
        try:
            # Edit role with all color values
            await highest_role.edit(
                color=primary_color,
                secondary_color=secondary_color,
                tertiary_color=tertiary_color
            )
            
            # Save to database
            await save_role_to_db(interaction.user.id, interaction.guild.id, highest_role)
            
            embed = discord.Embed(
                title="✅ Role Color Updated!",
                description=description,
                color=primary_color
            )
            embed.add_field(name="Style", value=style.title(), inline=True)
            embed.add_field(name="Role", value=highest_role.mention, inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to edit roles.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error updating role: {e}", ephemeral=True)

    @app_commands.command(name="label", description="Set your booster role label/name")
    @app_commands.describe(role_label="New label for your role")
    async def label(self, interaction: discord.Interaction, role_label: str):
        # Check if user is a booster
        if not any(role.is_premium_subscriber() for role in interaction.user.roles):
            await interaction.response.send_message("❌ This command is only available to server boosters!", ephemeral=True)
            return
        
        # Validate name length and content
        if len(role_label) > 100:
            await interaction.response.send_message("❌ Role label must be 100 characters or less.", ephemeral=True)
            return
        
        if not role_label.strip():
            await interaction.response.send_message("❌ Role label cannot be empty.", ephemeral=True)
            return
        
        # Check database for saved role first
        db_role_data = db.get_booster_role(interaction.user.id, interaction.guild.id)
        
        # Get or create/restore booster role
        highest_role = await get_or_create_booster_role(interaction, db_role_data)
        if not highest_role:
            await interaction.response.send_message("❌ Failed to create or find your booster role.", ephemeral=True)
            return
        
        # Update role name
        old_name = highest_role.name
        try:
            await highest_role.edit(name=role_label, reason=f"Booster role label change by {interaction.user}")
            
            # Save to database
            await save_role_to_db(interaction.user.id, interaction.guild.id, highest_role)
            
            await interaction.response.send_message(f"✅ Role label updated from **{old_name}** to **{role_label}**!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to edit roles.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error updating role title: {e}", ephemeral=True)

    @app_commands.command(name="icon", description="Set your booster role icon")
    @app_commands.describe(icon_url="Image URL or upload an image")
    async def icon(self, interaction: discord.Interaction, icon_url: str):
        # Check if user is a booster
        if not any(role.is_premium_subscriber() for role in interaction.user.roles):
            await interaction.response.send_message("❌ This command is only available to server boosters!", ephemeral=True)
            return
        
        # Check if guild has role icons feature
        if "ROLE_ICONS" not in interaction.guild.features:
            await interaction.response.send_message("❌ This server doesn't support role icons.", ephemeral=True)
            return
        
        # Check database for saved role first
        db_role_data = db.get_booster_role(interaction.user.id, interaction.guild.id)
        
        # Get or create/restore booster role
        highest_role = await get_or_create_booster_role(interaction, db_role_data)
        if not highest_role:
            await interaction.response.send_message("❌ Failed to create or find your booster role.", ephemeral=True)
            return
        
        try:
            # If icon_url is an attachment, use its URL
            if hasattr(interaction, 'attachments') and interaction.attachments:
                icon_url = interaction.attachments[0].url
            
            # Download the image
            async with aiohttp.ClientSession() as session:
                async with session.get(icon_url) as resp:
                    if resp.status != 200:
                        await interaction.response.send_message("❌ Could not download the image. Please check the URL or upload a valid image.", ephemeral=True)
                        return
                    image_bytes = await resp.read()
            
            await highest_role.edit(icon=image_bytes)
            
            # Save to database
            await save_role_to_db(interaction.user.id, interaction.guild.id, highest_role)
            
            await interaction.response.send_message(f"✅ Role icon updated!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to edit roles.", ephemeral=True)
        except discord.HTTPException as e:
            if e.code == 50035:
                await interaction.response.send_message("❌ Invalid image format. Please use PNG, JPG, or GIF.", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Discord error: {e}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ An unexpected error occurred: {e}", ephemeral=True)


class BoosterGroup(app_commands.Group):
    """Server booster commands"""
    
    def __init__(self):
        super().__init__(name="booster", description="Server booster commands")
        self.add_command(BoosterRoleGroup(name="role", description="Booster role customization"))
