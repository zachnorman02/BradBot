#!/usr/bin/env python3
"""
Migration script to convert existing verified role logic to the new role rules system.
This script creates default role rules for guilds that have:
1. verified -> remove unverified, add lvl 0
2. lvl X (where X > 0) -> remove lvl 0

Run this once after deploying the new role rules system.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

def main():
    """Set up default role rules for existing guilds"""
    # Initialize database
    if not db.connection_pool:
        db.init_pool()
    
    # Create the role_rules table
    print("Creating role_rules table...")
    db.init_role_rules_table()
    print("✅ Table created/verified")
    
    # Create bot instance to fetch guild data
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    
    bot = commands.Bot(command_prefix="!", intents=intents)
    
    @bot.event
    async def on_ready():
        print(f"✅ Bot connected as {bot.user}")
        print(f"Found {len(bot.guilds)} guilds\n")
        
        # Initialize tables
        db.init_conditional_roles_tables()
        
        created_count = 0
        skipped_count = 0
        
        for guild in bot.guilds:
            print(f"Processing guild: {guild.name} (ID: {guild.id})")
            
            # Check if guild already has verified role automation enabled
            verify_enabled = db.get_guild_setting(guild.id, 'verify_roles_enabled', 'true')
            if verify_enabled.lower() != 'true':
                print(f"  ⏭️  Verify roles disabled, skipping")
                skipped_count += 1
                continue
            
            # Find the verified, unverified, and lvl 0 roles
            verified_role = discord.utils.get(guild.roles, name="verified")
            unverified_role = discord.utils.get(guild.roles, name="unverified")
            lvl0_role = discord.utils.get(guild.roles, name="lvl 0")
            
            if not verified_role:
                print(f"  ⚠️  No 'verified' role found, skipping")
                skipped_count += 1
                continue
            
            # ================================================================
            # USE CASE 1: verified -> add lvl 0, remove unverified
            # ================================================================
            existing_rule = db.get_role_rule(guild.id, 'verified_roles')
            if not existing_rule:
                roles_to_add = [lvl0_role.id] if lvl0_role else []
                roles_to_remove = [unverified_role.id] if unverified_role else []
                
                if roles_to_add or roles_to_remove:
                    db.add_role_rule(
                        guild.id,
                        'verified_roles',
                        verified_role.id,
                        roles_to_add,
                        roles_to_remove
                    )
                    
                    print(f"  ✅ Created 'verified_roles' rule:")
                    print(f"     Trigger: @{verified_role.name}")
                    if roles_to_add:
                        print(f"     Add: @{lvl0_role.name}")
                    if roles_to_remove:
                        print(f"     Remove: @{unverified_role.name}")
                    
                    created_count += 1
            else:
                print(f"  ⏭️  Rule 'verified_roles' already exists")
            
            # ================================================================
            # USE CASE 2: lvl X -> remove lvl 0
            # ================================================================
            if lvl0_role:
                # Find all lvl roles (lvl 1, lvl 3, lvl 5, etc.)
                lvl_roles = [r for r in guild.roles if r.name.startswith("lvl ") and r.name != "lvl 0"]
                
                for lvl_role in lvl_roles:
                    rule_name = f"lvl_promotion_{lvl_role.name.replace(' ', '_')}"
                    
                    # Check if rule already exists
                    existing_lvl_rule = db.get_role_rule(guild.id, rule_name)
                    if existing_lvl_rule:
                        continue
                    
                    db.add_role_rule(
                        guild.id,
                        rule_name,
                        lvl_role.id,
                        [],  # No roles to add
                        [lvl0_role.id]  # Remove lvl 0
                    )
                    
                    print(f"  ✅ Created '{rule_name}' rule: @{lvl_role.name} -> remove @lvl 0")
                    created_count += 1
            
            # ================================================================
            # USE CASE 3: wormed conditional role (if exists)
            # ================================================================
            wormed_role = discord.utils.get(guild.roles, name="wormed")
            if wormed_role:
                # Check if already configured
                existing_config = db.get_conditional_role_config(guild.id, wormed_role.id)
                
                if not existing_config:
                    # Find blocking roles: 17 (limited), lvl 0, lvl 1, lvl 3, lvl 5
                    blocking_role_names = ["17 (limited)", "lvl 0", "lvl 1", "lvl 3", "lvl 5"]
                    blocking_role_ids = []
                    
                    for role_name in blocking_role_names:
                        role = discord.utils.get(guild.roles, name=role_name)
                        if role:
                            blocking_role_ids.append(role.id)
                    
                    if blocking_role_ids:
                        db.add_conditional_role_config(
                            guild.id,
                            wormed_role.id,
                            wormed_role.name,
                            blocking_role_ids
                        )
                        
                        print(f"  ✅ Configured conditional role: @{wormed_role.name}")
                        print(f"     Blocking roles: {', '.join(blocking_role_names)}")
                        created_count += 1
                    else:
                        print(f"  ⚠️  Found @wormed role but no blocking roles to configure")
                else:
                    print(f"  ⏭️  Conditional role config for @wormed already exists")
        
        print(f"\n{'='*60}")
        print(f"Migration complete!")
        print(f"  ✅ Created: {created_count} rules")
        print(f"  ⏭️  Skipped: {skipped_count} guilds")
        print(f"{'='*60}\n")
        
        await bot.close()
    
    # Run the bot
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("❌ DISCORD_TOKEN not found in environment")
        return
    
    bot.run(token)

if __name__ == "__main__":
    main()
