"""
Database migration manager for BradBot
Tracks and applies database schema changes automatically
"""
import os
import sys
from datetime import datetime

# Add parent directory to path so we can import database module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

# Migration: Grant admin read access (legacy)
class Migration003(Migration):
    def __init__(self):
        super().__init__("003", "Grant admin user read access to tables")
    
    def up(self):
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

class Migration006(Migration):
    def __init__(self):
        super().__init__("006", "Rename settings to user_settings and create guild_settings table")
    
    def up(self):
        # Rename settings table to user_settings
        rename_sql = """
        ALTER TABLE main.settings RENAME TO user_settings;
        """
        db.execute_query(rename_sql, fetch=False)
        print(f"   ✅ Renamed settings table to user_settings")
        
        # Create guild_settings table
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS main.guild_settings (
            guild_id BIGINT NOT NULL,
            setting_name CHARACTER VARYING NOT NULL,
            setting_value TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (guild_id, setting_name)
        );
        """
        db.execute_query(create_table_sql, fetch=False)
        print(f"   ✅ Created guild_settings table")
        
        # Create index on guild_id for faster lookups
        index_sql = """
        CREATE INDEX ASYNC idx_guild_settings_guild 
        ON main.guild_settings(guild_id);
        """
        try:
            db.execute_query(index_sql, fetch=False)
            print(f"   ℹ️  Index creation started asynchronously")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                print(f"   ℹ️  Index already exists")
            else:
                print(f"   ⚠️  Could not create index: {e}")
        
        # Set default link_replacement setting to enabled for all existing guilds
        # We'll do this via the bot's on_guild_join or on first use
        print(f"   ℹ️  Guild setting 'link_replacement' defaults to enabled")

class Migration007(Migration):
    def __init__(self):
        super().__init__("007", "Add secondary and tertiary color columns to booster_roles")
    
    def up(self):
        # Add secondary_color_hex column
        alter_secondary_sql = """
        ALTER TABLE main.booster_roles 
        ADD COLUMN IF NOT EXISTS secondary_color_hex TEXT;
        """
        db.execute_query(alter_secondary_sql, fetch=False)
        print(f"   ✅ Added secondary_color_hex column")
        
        # Add tertiary_color_hex column
        alter_tertiary_sql = """
        ALTER TABLE main.booster_roles 
        ADD COLUMN IF NOT EXISTS tertiary_color_hex TEXT;
        """
        db.execute_query(alter_tertiary_sql, fetch=False)
        print(f"   ✅ Added tertiary_color_hex column")

# Migration: Update color types based on actual color data
class Migration008(Migration):
    def __init__(self):
        super().__init__("008", "Update color_type to gradient/holographic based on secondary/tertiary colors")
    
    def up(self):
        # Update to 'gradient' if secondary_color_hex exists but not tertiary
        update_gradient_sql = """
        UPDATE main.booster_roles 
        SET color_type = 'gradient'
        WHERE secondary_color_hex IS NOT NULL 
        AND (tertiary_color_hex IS NULL OR tertiary_color_hex = '')
        AND color_type = 'solid';
        """
        db.execute_query(update_gradient_sql, fetch=False)
        print(f"   ✅ Updated rows with secondary color to 'gradient'")
        
        # Update to 'holographic' if both secondary and tertiary exist
        update_holographic_sql = """
        UPDATE main.booster_roles 
        SET color_type = 'holographic'
        WHERE secondary_color_hex IS NOT NULL 
        AND tertiary_color_hex IS NOT NULL 
        AND tertiary_color_hex != ''
        AND color_type != 'holographic';
        """
        db.execute_query(update_holographic_sql, fetch=False)
        print(f"   ✅ Updated rows with tertiary color to 'holographic'")

# Migration: Grant admin access to all tables (legacy)
class Migration009(Migration):
    def __init__(self):
        super().__init__("009", "Grant admin SELECT access to all tables")
    
    def up(self):
        print(f"   ✅ Granted admin SELECT access to all tables")

# Migration: Create poll tables
class Migration010(Migration):
    def __init__(self):
        super().__init__("010", "Create polls and poll_responses tables for text-response polls")
    
    def up(self):
        # Create polls table (ID will be generated by application using MAX(id) + 1)
        db.execute_query("""
            CREATE TABLE IF NOT EXISTS main.polls (
                id INTEGER PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                creator_id BIGINT NOT NULL,
                question TEXT NOT NULL,
                message_id BIGINT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """, fetch=False)
        print(f"   ✅ Created polls table")
        
        # Create poll_responses table (ID will be generated by application using MAX(id) + 1)
        db.execute_query("""
            CREATE TABLE IF NOT EXISTS main.poll_responses (
                id INTEGER PRIMARY KEY,
                poll_id INTEGER NOT NULL,
                user_id BIGINT NOT NULL,
                username TEXT NOT NULL,
                response_text TEXT NOT NULL,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(poll_id, user_id)
            )
        """, fetch=False)
        print(f"   ✅ Created poll_responses table")
        
        # Create indexes for better query performance
        try:
            db.execute_query("""
                CREATE INDEX ASYNC IF NOT EXISTS idx_polls_guild_active 
                ON main.polls(guild_id, is_active)
            """, fetch=False)
            print(f"   ℹ️  Index creation started asynchronously for polls table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"   ℹ️  Polls index already exists")
            else:
                print(f"   ⚠️  Could not create polls index: {e}")
        
        try:
            db.execute_query("""
                CREATE INDEX ASYNC IF NOT EXISTS idx_poll_responses_poll_id 
                ON main.poll_responses(poll_id)
            """, fetch=False)
            print(f"   ℹ️  Index creation started asynchronously for poll_responses table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"   ℹ️  Poll responses index already exists")
            else:
                print(f"   ⚠️  Could not create poll_responses index: {e}")
        
        print(f"   ✅ Created poll_responses table")

# Migration: Add auto-close functionality to polls
class Migration011(Migration):
    def __init__(self):
        super().__init__("011", "Add max_responses, close_at, show_responses, and public_results columns to polls")
    
    def up(self):
        # Add max_responses column
        db.execute_query("""
            ALTER TABLE main.polls 
            ADD COLUMN IF NOT EXISTS max_responses INTEGER
        """, fetch=False)
        print(f"   ✅ Added max_responses column to polls")
        
        # Add close_at column
        db.execute_query("""
            ALTER TABLE main.polls 
            ADD COLUMN IF NOT EXISTS close_at TIMESTAMP
        """, fetch=False)
        print(f"   ✅ Added close_at column to polls")
        
        # Add show_responses column (whether to display responses in the poll embed)
        db.execute_query("""
            ALTER TABLE main.polls 
            ADD COLUMN IF NOT EXISTS show_responses BOOLEAN
        """, fetch=False)
        print(f"   ✅ Added show_responses column to polls")
        
        # Set default value for existing rows
        db.execute_query("""
            UPDATE main.polls 
            SET show_responses = FALSE 
            WHERE show_responses IS NULL
        """, fetch=False)
        
        # Add public_results column (whether anyone can view results or just creator+admins)
        db.execute_query("""
            ALTER TABLE main.polls 
            ADD COLUMN IF NOT EXISTS public_results BOOLEAN
        """, fetch=False)
        print(f"   ✅ Added public_results column to polls")
        
        # Set default value for existing rows
        db.execute_query("""
            UPDATE main.polls 
            SET public_results = TRUE 
            WHERE public_results IS NULL
        """, fetch=False)

class Migration012(Migration):
    def __init__(self):
        super().__init__("012", "Add allow_multiple_responses column to polls")
    
    def up(self):
        # Add allow_multiple_responses column
        db.execute_query("""
            ALTER TABLE main.polls 
            ADD COLUMN IF NOT EXISTS allow_multiple_responses BOOLEAN
        """, fetch=False)
        print(f"   ✅ Added allow_multiple_responses column to polls")
        
        # Set default value for existing rows (allow multiple by default for backwards compatibility)
        db.execute_query("""
            UPDATE main.polls 
            SET allow_multiple_responses = TRUE 
            WHERE allow_multiple_responses IS NULL
        """, fetch=False)

class Migration013(Migration):
    def __init__(self):
        super().__init__("013", "Add reminders table")
    
    def up(self):
        # Create reminders table
        db.execute_query("""
            CREATE TABLE IF NOT EXISTS main.reminders (
                id INTEGER PRIMARY KEY,
                user_id BIGINT NOT NULL,
                guild_id BIGINT,
                channel_id BIGINT,
                message TEXT NOT NULL,
                remind_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_sent BOOLEAN DEFAULT FALSE
            )
        """, fetch=False)
        print(f"   ✅ Created reminders table")
        
        # Create index for efficient querying of pending reminders
        try:
            db.execute_query("""
                CREATE INDEX ASYNC IF NOT EXISTS idx_reminders_pending 
                ON main.reminders(remind_at, is_sent) 
                WHERE is_sent = FALSE
            """, fetch=False)
            print(f"   ✅ Created index on reminders(remind_at, is_sent)")
        except Exception as e:
            print(f"   ⚠️  Index creation queued: {e}")

class Migration014(Migration):
    def __init__(self):
        super().__init__("014", "Add timers table")
    
    def up(self):
        # Create timers table
        db.execute_query("""
            CREATE TABLE IF NOT EXISTS main.timers (
                id INTEGER PRIMARY KEY,
                user_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_id BIGINT,
                label TEXT,
                end_time TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_complete BOOLEAN DEFAULT FALSE
            )
        """, fetch=False)
        print(f"   ✅ Created timers table")
        
        # Create index for efficient querying of active timers
        try:
            db.execute_query("""
                CREATE INDEX ASYNC IF NOT EXISTS idx_timers_active 
                ON main.timers(is_complete, end_time) 
                WHERE is_complete = FALSE
            """, fetch=False)
            print(f"   ✅ Created index on timers(is_complete, end_time)")
        except Exception as e:
            print(f"   ⚠️  Index creation queued: {e}")

# Migration: Clean up non-booster roles
class Migration015(Migration):
    def __init__(self):
        super().__init__("015", "Delete booster roles without icon hash (likely not real booster roles)")
    
    def up(self):
        print(f"   🗑️  Deleting booster roles without icon hash...")
        
        # Delete roles that don't have an icon hash (likely permission roles, not booster roles)
        db.execute_query("""
            DELETE FROM main.booster_roles
            WHERE icon_hash IS NULL
        """, fetch=False)
        
        print(f"   ✅ Deleted non-booster roles from database")

# Migration: Task execution log table
class Migration016(Migration):
    def __init__(self):
        super().__init__("016", "Create task_logs table for tracking automated task execution")
    
    def up(self):
        print(f"   📋 Creating task_logs table...")
        
        # Create task_logs table (no auto-increment, IDs generated in code)
        db.execute_query("""
            CREATE TABLE IF NOT EXISTS main.task_logs (
                id BIGINT PRIMARY KEY,
                task_name VARCHAR(100) NOT NULL,
                guild_id BIGINT,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                status VARCHAR(20) NOT NULL,
                details TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """, fetch=False)
        print(f"   ✅ Created task_logs table")
        
        # Create indexes for efficient querying (without sort order - not supported)
        try:
            db.execute_query("""
                CREATE INDEX ASYNC IF NOT EXISTS idx_task_logs_task_name 
                ON main.task_logs(task_name, started_at)
            """, fetch=False)
            print(f"   ✅ Created index on task_logs(task_name, started_at)")
            
            db.execute_query("""
                CREATE INDEX ASYNC IF NOT EXISTS idx_task_logs_guild 
                ON main.task_logs(guild_id, started_at)
            """, fetch=False)
            print(f"   ✅ Created index on task_logs(guild_id, started_at)")
            
            db.execute_query("""
                CREATE INDEX ASYNC IF NOT EXISTS idx_task_logs_status 
                ON main.task_logs(status, started_at)
            """, fetch=False)
            print(f"   ✅ Created index on task_logs(status, started_at)")
        except Exception as e:
            print(f"   ⚠️  Index creation queued: {e}")

# Admin access (legacy)
class Migration017(Migration):
    def __init__(self):
        super().__init__("017", "Grant admin all privileges on all tables")
    
    def up(self):
        print(f"   📋 Granting admin full access to all tables...")

class Migration018(Migration):
    def __init__(self):
        super().__init__("018", "Create saved_emojis table for storing emojis and stickers")
    
    def up(self):
        print(f"   📋 Creating saved_emojis table...")
        
        # Create saved_emojis table (supports both emojis and stickers)
        db.execute_query("""
            CREATE TABLE IF NOT EXISTS main.saved_emojis (
                id BIGINT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                image_data BYTEA NOT NULL,
                animated BOOLEAN DEFAULT FALSE,
                is_sticker BOOLEAN DEFAULT FALSE,
                sticker_description TEXT,
                saved_by_user_id BIGINT NOT NULL,
                saved_from_guild_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            )
        """, fetch=False)
        print(f"   ✅ Created saved_emojis table")
        
        # Create index on name for searching
        try:
            db.execute_query("""
                CREATE INDEX ASYNC IF NOT EXISTS idx_saved_emojis_name 
                ON main.saved_emojis(name)
            """, fetch=False)
            print(f"   ✅ Created index on saved_emojis(name)")
        except Exception as e:
            print(f"   ⚠️  Index creation queued: {e}")

class Migration019(Migration):
    def __init__(self):
        super().__init__("019", "Create conditional role assignment tables")
    
    def up(self):
        print(f"   📋 Creating conditional role assignment tables...")
        
        # Create role configurations table
        db.execute_query("""
            CREATE TABLE IF NOT EXISTS main.conditional_role_configs (
                guild_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                role_name VARCHAR(100),
                blocking_role_ids TEXT,
                deferral_role_ids TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(guild_id, role_id)
            )
        """, fetch=False)
        print(f"   ✅ Created conditional_role_configs table")
        
        # Create eligibility tracking table
        db.execute_query("""
            CREATE TABLE IF NOT EXISTS main.conditional_role_eligibility (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                eligible BOOLEAN DEFAULT TRUE,
                marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                marked_by_user_id BIGINT,
                notes TEXT,
                PRIMARY KEY (guild_id, user_id, role_id)
            )
        """, fetch=False)
        print(f"   ✅ Created conditional_role_eligibility table")


class Migration020(Migration):
    """Add users who had roles removed to conditional_role_eligibility"""
    
    def __init__(self):
        super().__init__("020", "Add manually removed users to eligibility and remove users who shouldn't be tracked")
    
    def up(self):
        """Add users to conditional_role_eligibility and remove others"""
        add_user_ids = [
            1365353222973296741,
            1070813316026478723,
            894271255014940673,
            657952912793927680
        ]
        delete_user_ids = [
            512086807085711372
        ]
        guild_id = 1285083698500472853
        role_id = 1383620483013935285
        
        for user_id in add_user_ids:
            try:
                query = """
                INSERT INTO main.conditional_role_eligibility (guild_id, user_id, role_id, eligible, marked_at, notes)
                VALUES (%s, %s, %s, TRUE, CURRENT_TIMESTAMP, 'Manually added - role was removed during deferral')
                ON CONFLICT (guild_id, user_id, role_id) DO NOTHING
                """
                db.execute_query(query, (guild_id, user_id, role_id), fetch=False)
                print(f"   ✅ Added user {user_id} to conditional_role_eligibility")
            except Exception as e:
                print(f"   ⚠️  Failed to add user {user_id}: {e}")
        
        for user_id in delete_user_ids:
            try:
                query = """
                DELETE FROM main.conditional_role_eligibility
                WHERE guild_id = %s AND user_id = %s AND role_id = %s
                """
                db.execute_query(query, (guild_id, user_id, role_id), fetch=False)
                print(f"   ✅ Deleted user {user_id} from conditional_role_eligibility")
            except Exception as e:
                print(f"   ⚠️  Failed to delete user {user_id}: {e}")


# List of all migrations in order
MIGRATIONS = [
    Migration001(),
    Migration002(),
    Migration004(),  # Clean up duplicate settings
    Migration005(),  # Booster roles table
    Migration006(),  # Rename to user_settings and add guild_settings
    Migration007(),  # Add secondary and tertiary color columns
    Migration008(),  # Update color_type based on color data
    Migration010(),  # Poll tables
    Migration011(),  # Add auto-close functionality to polls
    Migration012(),  # Add allow_multiple_responses to polls
    Migration013(),  # Add reminders table
    Migration014(),  # Add timers table
    Migration015(),  # Clean up non-booster roles
    Migration016(),  # Task execution log
    Migration017(),  # Role assignment rules
    Migration018(),  # Saved emojis table
    Migration019(),  # Conditional role assignment tables
    Migration020(),  # Add manually removed users to eligibility
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
