"""
Database migration manager for BradBot
Tracks and applies database schema changes automatically
"""
import os
from datetime import datetime
from database import db

class Migration:
    """Base class for database migrations"""
    
    def __init__(self, version: str, description: str):
        self.version = version
        self.description = description
        self.timestamp = datetime.now()
    
    def up(self):
        """Apply the migration"""
        raise NotImplementedError
    
    def down(self):
        """Rollback the migration (optional)"""
        pass

# Migration: Initial Schema
class Migration001(Migration):
    def __init__(self):
        super().__init__("001", "Initial schema - migration tracking and settings table")
    
    def up(self):
        # Aurora DSQL doesn't support multiple DDL statements in one transaction
        # Execute each CREATE statement separately
        
        # Migration tracking table
        db.execute_query("""
            CREATE TABLE IF NOT EXISTS main.schema_migrations (
                version VARCHAR(10) PRIMARY KEY,
                description TEXT,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """, fetch=False)
        
        # Settings table
        db.execute_query("""
            CREATE TABLE IF NOT EXISTS main.settings (
                entity_type CHARACTER VARYING NOT NULL,
                entity_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                setting_name CHARACTER VARYING NOT NULL,
                setting_value TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (entity_type, entity_id, guild_id, setting_name)
            )
        """, fetch=False)
        
        # Index for faster lookups
        db.execute_query("""
            CREATE INDEX ASYNC IF NOT EXISTS idx_settings_name ON main.settings(setting_name)
        """, fetch=False)
        
        print(f"✅ Applied migration {self.version}: {self.description}")

# Migration: Message Tracking
class Migration002(Migration):
    def __init__(self):
        super().__init__("002", "Add message tracking for reply notifications")
    
    def up(self):
        # Create message tracking table
        db.execute_query("""
            CREATE TABLE IF NOT EXISTS main.message_tracking (
                message_id BIGINT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                original_url TEXT,
                fixed_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """, fetch=False)
        
        # Create indexes separately
        db.execute_query("""
            CREATE INDEX ASYNC IF NOT EXISTS idx_message_tracking_user ON main.message_tracking(user_id)
        """, fetch=False)
        
        db.execute_query("""
            CREATE INDEX ASYNC IF NOT EXISTS idx_message_tracking_guild ON main.message_tracking(guild_id)
        """, fetch=False)
        
        print(f"✅ Applied migration {self.version}: {self.description}")

# Migration: Grant admin read access
class Migration003(Migration):
    def __init__(self):
        super().__init__("003", "Grant admin user read access to tables")
    
    def up(self):
        # Grant read access to admin user for debugging
        db.execute_query("""
            GRANT SELECT ON ALL TABLES IN SCHEMA main TO admin
        """, fetch=False)
        
        print(f"✅ Applied migration {self.version}: {self.description}")

# Migration: Clean up duplicate settings
class Migration004(Migration):
    def __init__(self):
        super().__init__("004", "Clean up duplicate settings entries")
    
    def up(self):
        # Delete older duplicate entries, keeping only the most recent for each user
        db.execute_query("""
            DELETE FROM main.settings
            WHERE entity_type = 'user' 
            AND setting_name = 'reply_notifications'
            AND (entity_type, entity_id, guild_id, setting_name, updated_at) NOT IN (
                SELECT entity_type, entity_id, guild_id, setting_name, MAX(updated_at)
                FROM main.settings
                WHERE entity_type = 'user' AND setting_name = 'reply_notifications'
                GROUP BY entity_type, entity_id, guild_id, setting_name
            )
        """, fetch=False)
        
        print(f"✅ Applied migration {self.version}: {self.description}")

# Add new migrations here as you need them
# Example:
class Migration005(Migration):
    def __init__(self):
        super().__init__("005", "Create booster_roles table for persistent booster role configurations")
    
    def up(self):
        # Create booster_roles table
        sql = """
        CREATE TABLE IF NOT EXISTS main.booster_roles (
            user_id BIGINT NOT NULL,
            guild_id BIGINT NOT NULL,
            role_id BIGINT NOT NULL,
            role_name TEXT NOT NULL,
            color_hex TEXT NOT NULL,
            color_type TEXT NOT NULL DEFAULT 'solid',
            icon_hash TEXT,
            icon_data BYTEA,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, guild_id)
        );
        """
        db.execute_query(sql, fetch=False)
        
        # Create index on guild_id for faster lookups (Aurora DSQL requires ASYNC)
        index_sql = """
        CREATE INDEX ASYNC idx_booster_roles_guild 
        ON main.booster_roles(guild_id);
        """
        try:
            db.execute_query(index_sql, fetch=False)
            print(f"   ℹ️  Index creation started asynchronously (may take a few moments to complete)")
        except Exception as e:
            # Index might already exist or be in progress
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                print(f"   ℹ️  Index already exists")
            else:
                print(f"   ⚠️  Could not create index: {e}")
        
        # Grant read access to admin user
        grant_sql = """
        GRANT SELECT ON main.booster_roles TO admin;
        """
        try:
            db.execute_query(grant_sql, fetch=False)
        except Exception as e:
            print(f"   ⚠️  Could not grant admin access (may not exist): {e}")

# List of all migrations in order
MIGRATIONS = [
    Migration001(),
    Migration002(),
    Migration003(),  # Grant admin read access
    Migration004(),  # Clean up duplicate settings
    Migration005(),  # Booster roles table
]

def get_applied_migrations():
    """Get list of already applied migration versions"""
    try:
        result = db.execute_query(
            "SELECT version FROM main.schema_migrations ORDER BY version"
        )
        return [row[0] for row in result]
    except Exception:
        # Table doesn't exist yet, return empty list
        return []

def apply_migrations():
    """Apply all pending migrations"""
    print("🔄 Checking for pending migrations...")
    
    # Initialize database connection
    db.init_pool()
    
    # Get applied migrations
    applied = get_applied_migrations()
    print(f"   Already applied: {len(applied)} migration(s)")
    
    # Apply pending migrations
    pending_count = 0
    for migration in MIGRATIONS:
        if migration.version not in applied:
            print(f"   Applying migration {migration.version}: {migration.description}")
            try:
                # Apply migration
                migration.up()
                
                # Record migration
                db.execute_query(
                    "INSERT INTO main.schema_migrations (version, description) VALUES (%s, %s)",
                    (migration.version, migration.description),
                    fetch=False
                )
                pending_count += 1
            except Exception as e:
                print(f"   ❌ Error applying migration {migration.version}: {e}")
                raise
    
    if pending_count == 0:
        print("✅ Database is up to date")
    else:
        print(f"✅ Applied {pending_count} migration(s) successfully")
    
    return pending_count

def rollback_migration(version: str):
    """Rollback a specific migration (if down() is implemented)"""
    for migration in MIGRATIONS:
        if migration.version == version:
            print(f"Rolling back migration {version}...")
            migration.down()
            db.execute_query(
                "DELETE FROM main.schema_migrations WHERE version = %s",
                (version,),
                fetch=False
            )
            print(f"✅ Rolled back migration {version}")
            return
    print(f"❌ Migration {version} not found")

def list_migrations():
    """List all migrations and their status"""
    db.init_pool()
    applied = get_applied_migrations()
    
    print("\n📋 Migration Status:")
    print("-" * 70)
    print(f"{'Version':<10} {'Status':<15} {'Description'}")
    print("-" * 70)
    
    for migration in MIGRATIONS:
        status = "✅ Applied" if migration.version in applied else "⏳ Pending"
        print(f"{migration.version:<10} {status:<15} {migration.description}")
    
    print("-" * 70)
    print(f"Total: {len(MIGRATIONS)} migrations, {len(applied)} applied, {len(MIGRATIONS) - len(applied)} pending\n")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "list":
            list_migrations()
        elif command == "migrate":
            apply_migrations()
        elif command == "rollback" and len(sys.argv) > 2:
            version = sys.argv[2]
            rollback_migration(version)
        else:
            print("Usage:")
            print("  python migrate.py list       - List all migrations")
            print("  python migrate.py migrate    - Apply pending migrations")
            print("  python migrate.py rollback <version> - Rollback a migration")
    else:
        # Default: apply migrations
        apply_migrations()
