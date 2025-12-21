"""
Database connection and utilities for BradBot
Supports Aurora DSQL with IAM authentication
"""
import os
import json
import time
import boto3
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

class Database:
    """Database connection manager for BradBot"""
    
    def __init__(self):
        self.host = os.getenv('DB_HOST')
        self.port = int(os.getenv('DB_PORT', '5432'))
        self.database = os.getenv('DB_NAME', 'postgres')
        self.user = os.getenv('DB_USER', 'bradbotrole')
        self.use_iam_auth = os.getenv('USE_IAM_AUTH', 'true').lower() == 'true'
        self.region = os.getenv('AWS_REGION', 'us-east-1')
        self.connection_pool: Optional[pool.SimpleConnectionPool] = None
        self.persistent_panel_ids = set()
        self._persistent_panels_table_initialized = False
        self._echo_logs_table_initialized = False
        self._tts_logs_table_initialized = False
        
    def _get_iam_token(self) -> str:
        """Generate IAM authentication token for Aurora DSQL"""
        session = boto3.Session(region_name=self.region)
        dsql_client = session.client('dsql', region_name=self.region)
        
        # Generate authentication token
        token = dsql_client.generate_db_connect_auth_token(
            self.host, self.region
        )
        
        return token
    
    def get_connection_params(self) -> dict:
        """Get connection parameters for database"""
        params = {
            'host': self.host,
            'port': self.port,
            'database': self.database,
            'user': self.user,
            'sslmode': 'require',  # Require SSL but don't verify certificate
            'connect_timeout': 10
        }
        
        if self.use_iam_auth:
            # Use IAM authentication
            params['password'] = self._get_iam_token()
        else:
            # Use password authentication
            password = os.getenv('DB_PASSWORD')
            if not password:
                raise ValueError("DB_PASSWORD must be set when USE_IAM_AUTH=false")
            params['password'] = password
        
        return params
    
    def init_pool(self, minconn=1, maxconn=10):
        """Initialize connection pool"""
        if self.connection_pool:
            return
        
        params = self.get_connection_params()
        self.connection_pool = pool.SimpleConnectionPool(
            minconn,
            maxconn,
            **params
        )
    
    def get_connection(self):
        """Get a connection from the pool, handling IAM token expiration"""
        if not self.connection_pool:
            self.init_pool()
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                conn = self.connection_pool.getconn()
                # Test if connection is still valid
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                return conn
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                # Connection is bad, close the pool and reinitialize with fresh IAM token
                print(f"Database connection error (attempt {attempt + 1}/{max_retries}): {e}")
                try:
                    self.close_pool()
                except Exception:
                    pass
                if attempt < max_retries - 1:
                    self.init_pool()
                else:
                    raise
    
    def release_connection(self, conn):
        """Release a connection back to the pool"""
        if self.connection_pool:
            try:
                self.connection_pool.putconn(conn)
            except Exception:
                # If we can't release, just close it
                try:
                    conn.close()
                except Exception:
                    pass
    
    def close_pool(self):
        """Close all connections in the pool"""
        if self.connection_pool:
            self.connection_pool.closeall()
            self.connection_pool = None
    
    def execute_query(self, query: str, params: tuple = None, fetch: bool = True):
        """Execute a query and return results"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                if fetch:
                    result = cursor.fetchall()
                    conn.commit()
                    return result
                conn.commit()
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise e
        finally:
            if conn:
                self.release_connection(conn)
    
    def execute_many(self, query: str, params_list: list):
        """Execute a query with multiple parameter sets"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.executemany(query, params_list)
                conn.commit()
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise e
        finally:
            if conn:
                self.release_connection(conn)
    
    # User preference methods
    def get_user_reply_notifications(self, user_id: int, guild_id: Optional[int]) -> bool:
        """Get user's reply notification preference. Defaults to True if not set.
        guild_id=None checks global setting.
        """
        query = """
        SELECT setting_value FROM main.user_settings 
        WHERE entity_type = 'user' 
        AND entity_id = %s 
        AND guild_id IS NOT DISTINCT FROM %s 
        AND setting_name = 'reply_notifications'
        ORDER BY updated_at DESC
        LIMIT 1
        """
        result = self.execute_query(query, (user_id, guild_id))
        if result:
            return result[0][0].lower() == 'true'
        return True  # Default: notifications enabled
    
    def set_user_reply_notifications(self, user_id: int, guild_id: Optional[int], enabled: bool):
        """Set user's reply notification preference. guild_id=None sets global setting."""
        # Aurora DSQL doesn't support ON CONFLICT, so delete old entries first
        delete_query = """
        DELETE FROM main.user_settings 
        WHERE entity_type = 'user' 
        AND entity_id = %s 
        AND guild_id IS NOT DISTINCT FROM %s 
        AND setting_name = 'reply_notifications'
        """
        self.execute_query(delete_query, (user_id, guild_id), fetch=False)
        
        # Then insert the new value
        insert_query = """
        INSERT INTO main.user_settings (entity_type, entity_id, guild_id, setting_name, setting_value, created_at, updated_at)
        VALUES ('user', %s, %s, 'reply_notifications', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        self.execute_query(insert_query, (user_id, guild_id, 'true' if enabled else 'false'), fetch=False)
    
    def get_user_setting(self, user_id: int, guild_id: Optional[int], setting_name: str, default_value: bool = True) -> bool:
        """Get a user setting. Defaults to default_value if not set.
        guild_id=None checks global setting.
        """
        query = """
        SELECT setting_value FROM main.user_settings 
        WHERE entity_type = 'user' 
        AND entity_id = %s 
        AND guild_id IS NOT DISTINCT FROM %s 
        AND setting_name = %s
        ORDER BY updated_at DESC
        LIMIT 1
        """
        result = self.execute_query(query, (user_id, guild_id, setting_name))
        if result:
            return result[0][0].lower() == 'true'
        return default_value
    
    def set_user_setting(self, user_id: int, guild_id: Optional[int], setting_name: str, enabled: bool):
        """Set a user setting. guild_id=None sets global setting."""
        # Aurora DSQL doesn't support ON CONFLICT, so delete old entries first
        delete_query = """
        DELETE FROM main.user_settings 
        WHERE entity_type = 'user' 
        AND entity_id = %s 
        AND guild_id IS NOT DISTINCT FROM %s 
        AND setting_name = %s
        """
        self.execute_query(delete_query, (user_id, guild_id, setting_name), fetch=False)
        
        # Then insert the new value
        insert_query = """
        INSERT INTO main.user_settings (entity_type, entity_id, guild_id, setting_name, setting_value, created_at, updated_at)
        VALUES ('user', %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        self.execute_query(insert_query, (user_id, guild_id, setting_name, 'true' if enabled else 'false'), fetch=False)
    
    # Guild settings methods
    def get_guild_link_replacement_enabled(self, guild_id: int) -> bool:
        """Get whether link replacement is enabled for a guild. Defaults to True."""
        query = """
        SELECT setting_value FROM main.guild_settings 
        WHERE guild_id = %s 
        AND setting_name = 'link_replacement_enabled'
        ORDER BY updated_at DESC
        LIMIT 1
        """
        result = self.execute_query(query, (guild_id,))
        if result:
            return result[0][0].lower() == 'true'
        return True  # Default: link replacement enabled
    
    def set_guild_link_replacement(self, guild_id: int, enabled: bool, changed_by_user_id: int = None, changed_by_username: str = None):
        """Set guild's link replacement preference"""
        # Aurora DSQL doesn't support ON CONFLICT, so delete old entries first
        delete_query = """
        DELETE FROM main.guild_settings 
        WHERE guild_id = %s 
        AND setting_name = 'link_replacement_enabled'
        """
        self.execute_query(delete_query, (guild_id,), fetch=False)
        
        # Then insert the new value
        insert_query = """
        INSERT INTO main.guild_settings (guild_id, setting_name, setting_value, created_at, updated_at)
        VALUES (%s, 'link_replacement_enabled', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        self.execute_query(insert_query, (guild_id, 'true' if enabled else 'false'), fetch=False)
        
        # Log who made the change
        if changed_by_user_id:
            status = 'enabled' if enabled else 'disabled'
            username_info = f" ({changed_by_username})" if changed_by_username else ""
            print(f"🔧 Guild {guild_id}: Link replacement {status} by user {changed_by_user_id}{username_info}")
    
    def get_guild_setting(self, guild_id: int, setting_name: str, default_value: str = 'true') -> str:
        """Get a guild setting value. Returns default_value if not set."""
        query = """
        SELECT setting_value FROM main.guild_settings 
        WHERE guild_id = %s 
        AND setting_name = %s
        ORDER BY updated_at DESC
        LIMIT 1
        """
        result = self.execute_query(query, (guild_id, setting_name))
        if result:
            return result[0][0]
        return default_value
    
    def set_guild_setting(self, guild_id: int, setting_name: str, setting_value: str):
        """Set a guild setting"""
        # Aurora DSQL doesn't support ON CONFLICT, so delete old entries first
        delete_query = """
        DELETE FROM main.guild_settings 
        WHERE guild_id = %s 
        AND setting_name = %s
        """
        self.execute_query(delete_query, (guild_id, setting_name), fetch=False)
        
        # Then insert the new value
        insert_query = """
        INSERT INTO main.guild_settings (guild_id, setting_name, setting_value, created_at, updated_at)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        self.execute_query(insert_query, (guild_id, setting_name, setting_value), fetch=False)
    
    # Message tracking methods
    def store_message_tracking(self, bot_message_id: int, user_id: int, guild_id: int, 
                               original_url: str, fixed_url: str):
        """Store tracking information for a bot's replacement message"""
        # Aurora DSQL doesn't support ON CONFLICT, so check if exists first
        check_query = "SELECT 1 FROM main.message_tracking WHERE message_id = %s"
        exists = self.execute_query(check_query, (bot_message_id,))
        
        if not exists:
            query = """
            INSERT INTO main.message_tracking (message_id, user_id, guild_id, original_url, fixed_url)
            VALUES (%s, %s, %s, %s, %s)
            """
            self.execute_query(query, (bot_message_id, user_id, guild_id, original_url, fixed_url), fetch=False)
    
    def get_message_original_user(self, bot_message_id: int) -> Optional[tuple]:
        """Get original user info for a bot message. Returns (user_id, guild_id) or None"""
        query = "SELECT user_id, guild_id FROM main.message_tracking WHERE message_id = %s"
        result = self.execute_query(query, (bot_message_id,))
        if result:
            return result[0]
        return None
    
    # Booster role methods
    def store_booster_role(self, user_id: int, guild_id: int, role_id: int, 
                          role_name: str, color_hex: str, color_type: str = 'solid',
                          icon_hash: str = None, icon_data: bytes = None,
                          secondary_color_hex: str = None, tertiary_color_hex: str = None):
        """Store or update booster role configuration in database"""
        # Aurora DSQL doesn't support ON CONFLICT, so check if exists first
        check_query = "SELECT created_at FROM main.booster_roles WHERE user_id = %s AND guild_id = %s"
        existing = self.execute_query(check_query, (user_id, guild_id))
        
        if existing:
            # Get the original created_at timestamp
            original_created_at = existing[0][0]
            
            # Delete existing record
            delete_query = "DELETE FROM main.booster_roles WHERE user_id = %s AND guild_id = %s"
            self.execute_query(delete_query, (user_id, guild_id), fetch=False)
            
            # Insert with preserved created_at
            query = """
            INSERT INTO main.booster_roles 
            (user_id, guild_id, role_id, role_name, color_hex, color_type, icon_hash, icon_data, 
             secondary_color_hex, tertiary_color_hex, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """
            self.execute_query(query, (user_id, guild_id, role_id, role_name, color_hex, 
                                       color_type, icon_hash, icon_data, 
                                       secondary_color_hex, tertiary_color_hex, original_created_at), fetch=False)
        else:
            # Insert new record with current timestamp
            query = """
            INSERT INTO main.booster_roles 
            (user_id, guild_id, role_id, role_name, color_hex, color_type, icon_hash, icon_data, 
             secondary_color_hex, tertiary_color_hex, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
            self.execute_query(query, (user_id, guild_id, role_id, role_name, color_hex, 
                                       color_type, icon_hash, icon_data, 
                                       secondary_color_hex, tertiary_color_hex), fetch=False)
    
    def get_booster_role(self, user_id: int, guild_id: int) -> Optional[dict]:
        """Get booster role configuration from database. Returns dict or None"""
        query = """
        SELECT role_id, role_name, color_hex, color_type, icon_hash, icon_data, 
               secondary_color_hex, tertiary_color_hex, created_at, updated_at
        FROM main.booster_roles 
        WHERE user_id = %s AND guild_id = %s
        """
        result = self.execute_query(query, (user_id, guild_id))
        if result:
            row = result[0]
            return {
                'role_id': row[0],
                'role_name': row[1],
                'color_hex': row[2],
                'color_type': row[3],
                'icon_hash': row[4],
                'icon_data': row[5],
                'secondary_color_hex': row[6],
                'tertiary_color_hex': row[7],
                'created_at': row[8],
                'updated_at': row[9]
            }
        return None
    
    def delete_booster_role(self, user_id: int, guild_id: int):
        """Delete booster role configuration from database"""
        query = "DELETE FROM main.booster_roles WHERE user_id = %s AND guild_id = %s"
        self.execute_query(query, (user_id, guild_id), fetch=False)
    
    def get_all_booster_roles(self, guild_id: int) -> list:
        """Get all booster role configurations for a guild. Returns list of dicts"""
        query = """
        SELECT user_id, role_id, role_name, color_hex, color_type, icon_hash, icon_data, 
               secondary_color_hex, tertiary_color_hex, created_at, updated_at
        FROM main.booster_roles 
        WHERE guild_id = %s
        """
        result = self.execute_query(query, (guild_id,))
        if result:
            return [{
                'user_id': row[0],
                'role_id': row[1],
                'role_name': row[2],
                'color_hex': row[3],
                'color_type': row[4],
                'icon_hash': row[5],
                'icon_data': row[6],
                'secondary_color_hex': row[7],
                'tertiary_color_hex': row[8],
                'created_at': row[9],
                'updated_at': row[10]
            } for row in result]
        return []
    
    def update_booster_role_id(self, user_id: int, guild_id: int, new_role_id: int):
        """Update the role_id for a booster role (when role is recreated)"""
        query = """
        UPDATE main.booster_roles 
        SET role_id = %s, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = %s AND guild_id = %s
        """
        self.execute_query(query, (new_role_id, user_id, guild_id), fetch=False)
    
    def init_starboard_tables(self):
        """Initialize starboard tables if needed"""
        if getattr(self, '_starboard_tables_initialized', False):
            return
        create_boards = """
        CREATE TABLE IF NOT EXISTS main.starboard_boards (
            id INTEGER PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            emoji TEXT NOT NULL,
            threshold INTEGER NOT NULL,
            allow_nsfw BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        create_posts = """
        CREATE TABLE IF NOT EXISTS main.starboard_posts (
            message_id BIGINT NOT NULL,
            board_id INTEGER NOT NULL,
            star_message_id BIGINT,
            guild_id BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            author_id BIGINT NOT NULL,
            current_count INTEGER DEFAULT 0,
            forced BOOLEAN DEFAULT FALSE,
            blocked BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (message_id, board_id)
        )
        """
        self.execute_query(create_boards, fetch=False)
        self.execute_query(create_posts, fetch=False)
        self._starboard_tables_initialized = True

    def init_echo_logs_table(self):
        """Create the echo_logs table if it does not exist."""
        if self._echo_logs_table_initialized:
            return
        query = """
        CREATE TABLE IF NOT EXISTS main.echo_logs (
            id BIGINT PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            username TEXT NOT NULL,
            channel_id BIGINT NOT NULL,
            message_id BIGINT,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        self.execute_query(query, fetch=False)
        try:
            self.execute_query(
                "ALTER TABLE main.echo_logs ADD COLUMN IF NOT EXISTS message_id BIGINT",
                fetch=False
            )
            self.execute_query(
                "ALTER TABLE main.echo_logs ADD COLUMN IF NOT EXISTS username TEXT NOT NULL DEFAULT ''",
                fetch=False
            )
        except Exception as e:
            print(f"Failed to ensure echo_logs columns: {e}")
        self._echo_logs_table_initialized = True

    def init_tts_logs_table(self):
        """Create the tts_logs table if it does not exist."""
        if self._tts_logs_table_initialized:
            return
        query = """
        CREATE TABLE IF NOT EXISTS main.tts_logs (
            id BIGINT PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            username TEXT NOT NULL,
            channel_id BIGINT NOT NULL,
            voice_channel_id BIGINT,
            message_id BIGINT,
            text TEXT NOT NULL,
            voice TEXT,
            engine TEXT,
            language TEXT,
            announce_author BOOLEAN DEFAULT FALSE,
            post_text BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        self.execute_query(query, fetch=False)
        try:
            self.execute_query(
                "ALTER TABLE main.tts_logs ADD COLUMN IF NOT EXISTS username TEXT NOT NULL DEFAULT ''",
                fetch=False
            )
            self.execute_query(
                "ALTER TABLE main.tts_logs ADD COLUMN IF NOT EXISTS voice_channel_id BIGINT",
                fetch=False
            )
            self.execute_query(
                "ALTER TABLE main.tts_logs ADD COLUMN IF NOT EXISTS message_id BIGINT",
                fetch=False
            )
            self.execute_query(
                "ALTER TABLE main.tts_logs ADD COLUMN IF NOT EXISTS voice TEXT",
                fetch=False
            )
            self.execute_query(
                "ALTER TABLE main.tts_logs ADD COLUMN IF NOT EXISTS engine TEXT",
                fetch=False
            )
            self.execute_query(
                "ALTER TABLE main.tts_logs ADD COLUMN IF NOT EXISTS language TEXT",
                fetch=False
            )
            self.execute_query(
                "ALTER TABLE main.tts_logs ADD COLUMN IF NOT EXISTS announce_author BOOLEAN DEFAULT FALSE",
                fetch=False
            )
            self.execute_query(
                "ALTER TABLE main.tts_logs ADD COLUMN IF NOT EXISTS post_text BOOLEAN DEFAULT TRUE",
                fetch=False
            )
        except Exception as e:
            print(f"Failed to ensure tts_logs columns: {e}")
        self._tts_logs_table_initialized = True

    # Poll methods
    def create_poll(self, guild_id: int, channel_id: int, creator_id: int, question: str, 
                    max_responses: int = None, close_at = None, show_responses: bool = False,
                    public_results: bool = True, allow_multiple_responses: bool = True) -> int:
        """Create a new poll and return its ID"""
        # Get next ID (Aurora DSQL doesn't support sequences)
        max_id_query = "SELECT COALESCE(MAX(id), 0) + 1 FROM main.polls"
        next_id = self.execute_query(max_id_query)[0][0]
        
        # Insert with explicit ID
        query = """
        INSERT INTO main.polls (id, guild_id, channel_id, creator_id, question, is_active, 
                               max_responses, close_at, show_responses, public_results, 
                               allow_multiple_responses, created_at)
        VALUES (%s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """
        self.execute_query(query, (next_id, guild_id, channel_id, creator_id, question, 
                                  max_responses, close_at, show_responses, public_results,
                                  allow_multiple_responses), fetch=False)
        return next_id
    
    def update_poll_message_id(self, poll_id: int, message_id: int):
        """Update the message ID for a poll"""
        query = "UPDATE main.polls SET message_id = %s WHERE id = %s"
        self.execute_query(query, (message_id, poll_id), fetch=False)
    
    def get_poll(self, poll_id: int) -> Optional[dict]:
        """Get poll information by ID"""
        query = """
        SELECT id, guild_id, channel_id, creator_id, question, message_id, is_active, 
               created_at, max_responses, close_at, show_responses, public_results,
               allow_multiple_responses
        FROM main.polls WHERE id = %s
        """
        result = self.execute_query(query, (poll_id,))
        if result:
            return {
                'id': result[0][0],
                'guild_id': result[0][1],
                'channel_id': result[0][2],
                'creator_id': result[0][3],
                'question': result[0][4],
                'message_id': result[0][5],
                'is_active': result[0][6],
                'created_at': result[0][7],
                'max_responses': result[0][8],
                'close_at': result[0][9],
                'show_responses': result[0][10],
                'public_results': result[0][11],
                'allow_multiple_responses': result[0][12]
            }
        return None
    
    def store_poll_response(self, poll_id: int, user_id: int, username: str, response_text: str):
        """Store a user's response to a poll"""
        # Check if poll is still active
        poll = self.get_poll(poll_id)
        if not poll or not poll['is_active']:
            raise Exception("This poll is closed or does not exist")
        
        # Check if user already responded
        check_query = "SELECT id FROM main.poll_responses WHERE poll_id = %s AND user_id = %s"
        existing = self.execute_query(check_query, (poll_id, user_id))
        
        if existing:
            # Check if multiple responses are allowed
            if not poll.get('allow_multiple_responses', True):
                raise Exception("You have already submitted a response to this poll")
            
            # Update existing response
            query = """
            UPDATE main.poll_responses 
            SET response_text = %s, username = %s, submitted_at = CURRENT_TIMESTAMP
            WHERE poll_id = %s AND user_id = %s
            """
            self.execute_query(query, (response_text, username, poll_id, user_id), fetch=False)
        else:
            # Get next ID (Aurora DSQL doesn't support sequences)
            max_id_query = "SELECT COALESCE(MAX(id), 0) + 1 FROM main.poll_responses"
            next_id = self.execute_query(max_id_query)[0][0]
            
            # Insert new response with explicit ID
            query = """
            INSERT INTO main.poll_responses (id, poll_id, user_id, username, response_text, submitted_at)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """
            self.execute_query(query, (next_id, poll_id, user_id, username, response_text), fetch=False)
        
        # Check if poll should auto-close due to max_responses
        if poll['max_responses']:
            response_count = self.get_poll_response_count(poll_id)
            if response_count >= poll['max_responses']:
                self.close_poll(poll_id)

    # Starboard methods
    def upsert_starboard_board(self, guild_id: int, channel_id: int, emoji: str, threshold: int, allow_nsfw: bool) -> int:
        """Create or update a starboard for a guild/channel."""
        self.init_starboard_tables()
        existing = self.execute_query(
            "SELECT id FROM main.starboard_boards WHERE guild_id = %s AND channel_id = %s",
            (guild_id, channel_id)
        )
        if existing:
            board_id = existing[0][0]
            update_query = """
            UPDATE main.starboard_boards
            SET emoji = %s, threshold = %s, allow_nsfw = %s, created_at = created_at
            WHERE id = %s
            """
            self.execute_query(update_query, (emoji, threshold, allow_nsfw, board_id), fetch=False)
            return board_id
        next_id = self.execute_query("SELECT COALESCE(MAX(id), 0) + 1 FROM main.starboard_boards")[0][0]
        insert_query = """
        INSERT INTO main.starboard_boards (id, guild_id, channel_id, emoji, threshold, allow_nsfw)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        self.execute_query(insert_query, (next_id, guild_id, channel_id, emoji, threshold, allow_nsfw), fetch=False)
        return next_id

    def delete_starboard_board(self, guild_id: int, channel_id: int):
        self.execute_query(
            "DELETE FROM main.starboard_boards WHERE guild_id = %s AND channel_id = %s",
            (guild_id, channel_id),
            fetch=False
        )

    def get_starboard_boards(self, guild_id: int) -> list[dict]:
        self.init_starboard_tables()
        query = """
        SELECT id, channel_id, emoji, threshold, allow_nsfw
        FROM main.starboard_boards
        WHERE guild_id = %s
        ORDER BY channel_id
        """
        rows = self.execute_query(query, (guild_id,))
        return [
            {
                'id': row[0],
                'channel_id': row[1],
                'emoji': row[2],
                'threshold': row[3],
                'allow_nsfw': row[4]
            } for row in rows
        ]

    def get_starboard_board(self, guild_id: int, channel_id: int) -> Optional[dict]:
        query = """
        SELECT id, channel_id, emoji, threshold, allow_nsfw
        FROM main.starboard_boards
        WHERE guild_id = %s AND channel_id = %s
        """
        rows = self.execute_query(query, (guild_id, channel_id))
        if rows:
            row = rows[0]
            return {
                'id': row[0],
                'channel_id': row[1],
                'emoji': row[2],
                'threshold': row[3],
                'allow_nsfw': row[4]
            }
        return None

    def get_starboard_boards_by_emoji(self, guild_id: int, emoji: str) -> list[dict]:
        query = """
        SELECT id, channel_id, emoji, threshold, allow_nsfw
        FROM main.starboard_boards
        WHERE guild_id = %s AND emoji = %s
        """
        rows = self.execute_query(query, (guild_id, emoji))
        return [
            {
                'id': row[0],
                'channel_id': row[1],
                'emoji': row[2],
                'threshold': row[3],
                'allow_nsfw': row[4]
            } for row in rows
        ]

    def get_starboard_post(self, message_id: int, board_id: int) -> Optional[dict]:
        query = """
        SELECT message_id, board_id, star_message_id, guild_id, channel_id, author_id,
               current_count, forced, blocked
        FROM main.starboard_posts
        WHERE message_id = %s AND board_id = %s
        """
        rows = self.execute_query(query, (message_id, board_id))
        if rows:
            row = rows[0]
            return {
                'message_id': row[0],
                'board_id': row[1],
                'star_message_id': row[2],
                'guild_id': row[3],
                'channel_id': row[4],
                'author_id': row[5],
                'current_count': row[6],
                'forced': row[7],
                'blocked': row[8],
            }
        return None

    def upsert_starboard_post(
        self,
        message_id: int,
        board_id: int,
        guild_id: int,
        channel_id: int,
        author_id: int,
        star_message_id: int = None,
        count: int = 0,
        forced: bool = False,
        blocked: bool = False
    ):
        existing = self.get_starboard_post(message_id, board_id)
        if existing:
            update_query = """
            UPDATE main.starboard_posts
            SET star_message_id = %s,
                current_count = %s,
                forced = %s,
                blocked = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE message_id = %s AND board_id = %s
            """
            self.execute_query(
                update_query,
                (star_message_id, count, forced, blocked, message_id, board_id),
                fetch=False
            )
        else:
            insert_query = """
            INSERT INTO main.starboard_posts
            (message_id, board_id, star_message_id, guild_id, channel_id, author_id, current_count, forced, blocked)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            self.execute_query(
                insert_query,
                (message_id, board_id, star_message_id, guild_id, channel_id, author_id, count, forced, blocked),
                fetch=False
            )

    def update_starboard_post(self, message_id: int, board_id: int, **fields):
        if not fields:
            return
        updates = []
        params = []
        for key, value in fields.items():
            updates.append(f"{key} = %s")
            params.append(value)
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.extend([message_id, board_id])
        query = f"""
        UPDATE main.starboard_posts
        SET {', '.join(updates)}
        WHERE message_id = %s AND board_id = %s
        """
        self.execute_query(query, tuple(params), fetch=False)

    def delete_starboard_post(self, message_id: int, board_id: int):
        self.execute_query(
            "DELETE FROM main.starboard_posts WHERE message_id = %s AND board_id = %s",
            (message_id, board_id),
            fetch=False
        )

    def list_top_starboard_posts(self, board_id: int, limit: int = 10) -> list[dict]:
        query = """
        SELECT message_id, star_message_id, channel_id, author_id, current_count, forced, blocked
        FROM main.starboard_posts
        WHERE board_id = %s
        ORDER BY current_count DESC, created_at ASC
        LIMIT %s
        """
        rows = self.execute_query(query, (board_id, limit))
        return [
            {
                'message_id': row[0],
                'star_message_id': row[1],
                'channel_id': row[2],
                'author_id': row[3],
                'current_count': row[4],
                'forced': row[5],
                'blocked': row[6],
            } for row in rows
        ]

    # Echo log methods
    def log_echo_message(
        self,
        guild_id: int,
        user_id: int,
        username: str,
        channel_id: int,
        message: str,
        message_id: int | None = None
    ):
        """Store a record of an /echo command."""
        self.init_echo_logs_table()
        next_id = self.execute_query("SELECT COALESCE(MAX(id), 0) + 1 FROM main.echo_logs")[0][0]
        query = """
        INSERT INTO main.echo_logs (id, guild_id, user_id, username, channel_id, message_id, message)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        self.execute_query(
            query,
            (next_id, guild_id, user_id, username, channel_id, message_id, message),
            fetch=False
        )

    def log_tts_message(
        self,
        guild_id: int,
        user_id: int,
        username: str,
        channel_id: int,
        voice_channel_id: int | None,
        message_id: int | None,
        text: str,
        voice: str | None,
        engine: str | None,
        language: str | None,
        announce_author: bool,
        post_text: bool
    ):
        """Store a record of a /voice tts command."""
        self.init_tts_logs_table()
        next_id = self.execute_query("SELECT COALESCE(MAX(id), 0) + 1 FROM main.tts_logs")[0][0]
        query = """
        INSERT INTO main.tts_logs (
            id,
            guild_id,
            user_id,
            username,
            channel_id,
            voice_channel_id,
            message_id,
            text,
            voice,
            engine,
            language,
            announce_author,
            post_text
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        self.execute_query(
            query,
            (
                next_id,
                guild_id,
                user_id,
                username,
                channel_id,
                voice_channel_id,
                message_id,
                text,
                voice,
                engine,
                language,
                announce_author,
                post_text
            ),
            fetch=False
        )
    
    def get_poll_responses(self, poll_id: int) -> list:
        """Get all responses for a poll"""
        query = """
        SELECT user_id, username, response_text, submitted_at
        FROM main.poll_responses
        WHERE poll_id = %s
        ORDER BY submitted_at ASC
        """
        results = self.execute_query(query, (poll_id,))
        if results:
            return [
                {
                    'user_id': row[0],
                    'username': row[1],
                    'response_text': row[2],
                    'submitted_at': row[3]
                }
                for row in results
            ]
        return []
    
    def get_poll_response_count(self, poll_id: int) -> int:
        """Get the number of responses for a poll"""
        query = "SELECT COUNT(*) FROM main.poll_responses WHERE poll_id = %s"
        result = self.execute_query(query, (poll_id,))
        return result[0][0] if result else 0
    
    def close_poll(self, poll_id: int):
        """Close a poll to prevent new responses"""
        query = "UPDATE main.polls SET is_active = FALSE WHERE id = %s"
        self.execute_query(query, (poll_id,), fetch=False)
    
    def reopen_poll(self, poll_id: int):
        """Reopen a poll to allow new responses"""
        query = "UPDATE main.polls SET is_active = TRUE WHERE id = %s"
        self.execute_query(query, (poll_id,), fetch=False)

    def set_poll_show_responses(self, poll_id: int, show_responses: bool):
        """Update whether a poll shows responses on its message"""
        query = "UPDATE main.polls SET show_responses = %s WHERE id = %s"
        self.execute_query(query, ('true' if show_responses else 'false', poll_id), fetch=False)

    def get_active_polls(self, guild_id: int) -> list:
        """Get all active polls in a guild"""
        query = """
        SELECT id, channel_id, creator_id, question, created_at
        FROM main.polls
        WHERE guild_id = %s AND is_active = TRUE
        ORDER BY created_at DESC
        """
        results = self.execute_query(query, (guild_id,))
        if results:
            return [
                {
                    'id': row[0],
                    'channel_id': row[1],
                    'creator_id': row[2],
                    'question': row[3],
                    'created_at': row[4]
                }
                for row in results
            ]
        return []

    # Persistent panel methods
    def init_persistent_panels_table(self):
        """Create the persistent_panels table if it does not exist."""
        if self._persistent_panels_table_initialized:
            return
        query = """
        CREATE TABLE IF NOT EXISTS main.persistent_panels (
            message_id BIGINT PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            panel_type VARCHAR(100) NOT NULL,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        self.execute_query(query, fetch=False)
        # Make sure updated_at exists for legacy tables
        try:
            alter_query = """
            ALTER TABLE main.persistent_panels
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            """
            self.execute_query(alter_query, fetch=False)
        except Exception as e:
            print(f"Note: Could not ensure updated_at column (may already exist): {e}")
        self._persistent_panels_table_initialized = True
        print("✅ persistent_panels table initialized")

    def save_persistent_panel(self, message_id: int, guild_id: int, channel_id: int,
                               panel_type: str, metadata: Optional[dict] = None):
        """Insert or update a persistent panel record."""
        query = """
        INSERT INTO main.persistent_panels (message_id, guild_id, channel_id, panel_type, metadata, updated_at)
        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (message_id)
        DO UPDATE SET
            guild_id = EXCLUDED.guild_id,
            channel_id = EXCLUDED.channel_id,
            panel_type = EXCLUDED.panel_type,
            metadata = EXCLUDED.metadata,
            updated_at = CURRENT_TIMESTAMP
        """
        metadata_json = json.dumps(metadata) if metadata else None
        self.execute_query(query, (message_id, guild_id, channel_id, panel_type, metadata_json), fetch=False)
        self.persistent_panel_ids.add(message_id)

    def delete_persistent_panel(self, message_id: int):
        """Remove a persistent panel record."""
        query = "DELETE FROM main.persistent_panels WHERE message_id = %s"
        self.execute_query(query, (message_id,), fetch=False)
        self.persistent_panel_ids.discard(message_id)

    def get_persistent_panels(self, panel_type: Optional[str] = None) -> list:
        """Fetch stored persistent panels, optionally filtered by type."""
        if panel_type:
            query = """
            SELECT message_id, guild_id, channel_id, panel_type, metadata
            FROM main.persistent_panels
            WHERE panel_type = %s
            ORDER BY created_at ASC
            """
            params = (panel_type,)
        else:
            query = """
            SELECT message_id, guild_id, channel_id, panel_type, metadata
            FROM main.persistent_panels
            ORDER BY created_at ASC
            """
            params = None
        results = self.execute_query(query, params)
        if not results:
            return []
        panels = []
        for row in results:
            metadata = json.loads(row[4]) if row[4] else None
            panels.append({
                'message_id': row[0],
                'guild_id': row[1],
                'channel_id': row[2],
                'panel_type': row[3],
                'metadata': metadata
            })
            self.persistent_panel_ids.add(row[0])
        return panels
    
    # Reminder methods
    def create_reminder(self, user_id: int, message: str, remind_at, guild_id: int = None, channel_id: int = None) -> int:
        """Create a new reminder and return its ID"""
        # Get next ID
        max_id_query = "SELECT COALESCE(MAX(id), 0) + 1 FROM main.reminders"
        next_id = self.execute_query(max_id_query)[0][0]
        
        # Insert reminder
        query = """
        INSERT INTO main.reminders (id, user_id, guild_id, channel_id, message, remind_at, created_at, is_sent)
        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, FALSE)
        """
        self.execute_query(query, (next_id, user_id, guild_id, channel_id, message, remind_at), fetch=False)
        return next_id
    
    def get_pending_reminders(self):
        """Get all reminders that are due and haven't been sent"""
        query = """
        SELECT id, user_id, guild_id, channel_id, message, remind_at
        FROM main.reminders
        WHERE is_sent = FALSE AND remind_at <= CURRENT_TIMESTAMP
        ORDER BY remind_at ASC
        """
        results = self.execute_query(query)
        if results:
            return [
                {
                    'id': row[0],
                    'user_id': row[1],
                    'guild_id': row[2],
                    'channel_id': row[3],
                    'message': row[4],
                    'remind_at': row[5]
                }
                for row in results
            ]
        return []
    
    def mark_reminder_sent(self, reminder_id: int):
        """Mark a reminder as sent"""
        query = "UPDATE main.reminders SET is_sent = TRUE WHERE id = %s"
        self.execute_query(query, (reminder_id,), fetch=False)
    
    def delete_reminder(self, reminder_id: int):
        """Delete a reminder"""
        query = "DELETE FROM main.reminders WHERE id = %s"
        self.execute_query(query, (reminder_id,), fetch=False)
    
    # Timer methods
    def create_timer(self, user_id: int, guild_id: int, channel_id: int, label: str, end_time) -> int:
        """Create a new timer and return its ID"""
        # Get next ID
        max_id_query = "SELECT COALESCE(MAX(id), 0) + 1 FROM main.timers"
        next_id = self.execute_query(max_id_query)[0][0]
        
        # Insert timer
        query = """
        INSERT INTO main.timers (id, user_id, guild_id, channel_id, label, end_time, created_at, is_complete)
        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, FALSE)
        """
        self.execute_query(query, (next_id, user_id, guild_id, channel_id, label, end_time), fetch=False)
        return next_id
    
    def update_timer_message_id(self, timer_id: int, message_id: int):
        """Update the message ID for a timer"""
        query = "UPDATE main.timers SET message_id = %s WHERE id = %s"
        self.execute_query(query, (message_id, timer_id), fetch=False)
    
    def get_active_timers(self):
        """Get all active timers"""
        query = """
        SELECT id, user_id, guild_id, channel_id, message_id, label, end_time
        FROM main.timers
        WHERE is_complete = FALSE
        ORDER BY end_time ASC
        """
        results = self.execute_query(query)
        if results:
            return [
                {
                    'id': row[0],
                    'user_id': row[1],
                    'guild_id': row[2],
                    'channel_id': row[3],
                    'message_id': row[4],
                    'label': row[5],
                    'end_time': row[6]
                }
                for row in results
            ]
        return []
    
    def mark_timer_complete(self, timer_id: int):
        """Mark a timer as complete"""
        query = "UPDATE main.timers SET is_complete = TRUE WHERE id = %s"
        self.execute_query(query, (timer_id,), fetch=False)
    
    # Task logging methods
    def log_task_start(self, task_name: str, guild_id: Optional[int] = None, details: Optional[dict] = None) -> int:
        """Log the start of an automated task. Returns the log ID."""
        # Generate timestamp-based ID (microseconds since epoch)
        log_id = int(time.time() * 1_000_000)
        
        query = """
        INSERT INTO main.task_logs (id, task_name, guild_id, started_at, status, details)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP, 'running', %s)
        """
        self.execute_query(query, (log_id, task_name, guild_id, json.dumps(details) if details else None), fetch=False)
        return log_id
    
    def log_task_complete(self, log_id: int, status: str = 'success', details: Optional[dict] = None, error_message: Optional[str] = None):
        """Log the completion of an automated task."""
        query = """
        UPDATE main.task_logs 
        SET completed_at = CURRENT_TIMESTAMP, status = %s, details = %s, error_message = %s
        WHERE id = %s
        """
        self.execute_query(query, (status, json.dumps(details) if details else None, error_message, log_id), fetch=False)
    
    def get_recent_task_logs(self, task_name: Optional[str] = None, limit: int = 50):
        """Get recent task logs, optionally filtered by task name."""
        if task_name:
            query = """
            SELECT id, task_name, guild_id, started_at, completed_at, status, details, error_message
            FROM main.task_logs
            WHERE task_name = %s
            ORDER BY started_at DESC
            LIMIT %s
            """
            results = self.execute_query(query, (task_name, limit))
        else:
            query = """
            SELECT id, task_name, guild_id, started_at, completed_at, status, details, error_message
            FROM main.task_logs
            ORDER BY started_at DESC
            LIMIT %s
            """
            results = self.execute_query(query, (limit,))
        
        if results:
            return [
                {
                    'id': row[0],
                    'task_name': row[1],
                    'guild_id': row[2],
                    'started_at': row[3],
                    'completed_at': row[4],
                    'status': row[5],
                    'details': json.loads(row[6]) if row[6] else None,
                    'error_message': row[7]
                }
                for row in results
            ]
        return []
    
    # Saved emoji/sticker methods
    def save_emoji(self, name: str, image_data: bytes, animated: bool, saved_by_user_id: int, 
                   saved_from_guild_id: Optional[int] = None, notes: Optional[str] = None,
                   is_sticker: bool = False, sticker_description: Optional[str] = None) -> int:
        """Save an emoji or sticker to the database. Returns the emoji ID."""
        # Generate timestamp-based ID
        emoji_id = int(time.time() * 1_000_000)
        
        query = """
        INSERT INTO main.saved_emojis (id, name, image_data, animated, is_sticker, sticker_description, saved_by_user_id, saved_from_guild_id, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        self.execute_query(query, (emoji_id, name, image_data, animated, is_sticker, sticker_description, saved_by_user_id, saved_from_guild_id, notes), fetch=False)
        return emoji_id
    
    def get_saved_emoji(self, emoji_id: int):
        """Get a saved emoji or sticker by ID."""
        query = """
        SELECT id, name, image_data, animated, is_sticker, sticker_description, saved_by_user_id, saved_from_guild_id, created_at, notes
        FROM main.saved_emojis
        WHERE id = %s
        """
        results = self.execute_query(query, (emoji_id,))
        if results:
            row = results[0]
            return {
                'id': row[0],
                'name': row[1],
                'image_data': row[2],
                'animated': row[3],
                'is_sticker': row[4],
                'sticker_description': row[5],
                'saved_by_user_id': row[6],
                'saved_from_guild_id': row[7],
                'created_at': row[8],
                'notes': row[9]
            }
        return None
    
    # ============================================================================
    # CHANNEL RESTRICTIONS
    # ============================================================================
    
    def init_channel_restrictions_table(self):
        """Initialize channel_restrictions table for role-based channel access control."""
        query = """
        CREATE TABLE IF NOT EXISTS main.channel_restrictions (
            guild_id BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            blocking_role_id BIGINT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (guild_id, channel_id, blocking_role_id)
        )
        """
        self.execute_query(query, fetch=False)
        print("✅ Channel restrictions table initialized")
    
    def add_channel_restriction(self, guild_id: int, channel_id: int, blocking_role_id: int):
        """Add a channel restriction: members with blocking_role_id cannot view channel_id."""
        # Aurora DSQL doesn't support ON CONFLICT, so delete old entry first
        delete_query = """
        DELETE FROM main.channel_restrictions
        WHERE guild_id = %s AND channel_id = %s AND blocking_role_id = %s
        """
        self.execute_query(delete_query, (guild_id, channel_id, blocking_role_id), fetch=False)
        
        # Insert new restriction
        insert_query = """
        INSERT INTO main.channel_restrictions (guild_id, channel_id, blocking_role_id, created_at)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        """
        self.execute_query(insert_query, (guild_id, channel_id, blocking_role_id), fetch=False)
        print(f"✅ Added channel restriction: guild={guild_id}, channel={channel_id}, blocking_role={blocking_role_id}")
    
    def remove_channel_restriction(self, guild_id: int, channel_id: int, blocking_role_id: int):
        """Remove a channel restriction."""
        query = """
        DELETE FROM main.channel_restrictions
        WHERE guild_id = %s AND channel_id = %s AND blocking_role_id = %s
        """
        self.execute_query(query, (guild_id, channel_id, blocking_role_id), fetch=False)
        print(f"✅ Removed channel restriction: guild={guild_id}, channel={channel_id}, blocking_role={blocking_role_id}")
    
    def get_channel_restrictions(self, guild_id: int):
        """Get all channel restrictions for a guild."""
        query = """
        SELECT channel_id, blocking_role_id, created_at
        FROM main.channel_restrictions
        WHERE guild_id = %s
        ORDER BY created_at DESC
        """
        result = self.execute_query(query, (guild_id,))
        
        if result:
            return [
                {
                    'channel_id': row[0],
                    'blocking_role_id': row[1],
                    'created_at': row[2]
                }
                for row in result
            ]
        return []
    
    # ============================================================================
    # Message Mirroring
    # ============================================================================
    
    def init_message_mirrors_table(self):
        """Initialize the message mirrors table."""
        query = """
        CREATE TABLE IF NOT EXISTS main.message_mirrors (
            guild_id BIGINT NOT NULL,
            source_channel_id BIGINT NOT NULL,
            target_channel_id BIGINT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (guild_id, source_channel_id, target_channel_id)
        )
        """
        self.execute_query(query, fetch=False)
        
        # Create index on guild_id for faster lookups
        try:
            index_query = """
            CREATE INDEX ASYNC IF NOT EXISTS idx_message_mirrors_guild 
            ON main.message_mirrors (guild_id)
            """
            self.execute_query(index_query, fetch=False)
        except Exception as e:
            pass  # Index creation queued
        
        # Create index on source_channel_id for faster lookups
        try:
            source_index_query = """
            CREATE INDEX ASYNC IF NOT EXISTS idx_message_mirrors_source 
            ON main.message_mirrors (source_channel_id)
            """
            self.execute_query(source_index_query, fetch=False)
        except Exception as e:
            pass  # Index creation queued
        
        print("✅ message_mirrors table initialized")
    
    def init_mirrored_messages_table(self):
        """Initialize the mirrored messages tracking table."""
        query = """
        CREATE TABLE IF NOT EXISTS main.mirrored_messages (
            original_message_id BIGINT NOT NULL,
            original_channel_id BIGINT NOT NULL,
            mirror_message_id BIGINT NOT NULL,
            mirror_channel_id BIGINT NOT NULL,
            guild_id BIGINT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (original_message_id, mirror_channel_id)
        )
        """
        self.execute_query(query, fetch=False)
        
        # Create index on original_message_id for faster lookups
        try:
            index_query = """
            CREATE INDEX ASYNC IF NOT EXISTS idx_mirrored_messages_original 
            ON main.mirrored_messages (original_message_id)
            """
            self.execute_query(index_query, fetch=False)
        except Exception as e:
            pass  # Index creation queued
        
        # Create index on mirror_message_id for reverse lookups
        try:
            mirror_index_query = """
            CREATE INDEX ASYNC IF NOT EXISTS idx_mirrored_messages_mirror 
            ON main.mirrored_messages (mirror_message_id)
            """
            self.execute_query(mirror_index_query, fetch=False)
        except Exception as e:
            pass  # Index creation queued
        
        print("✅ mirrored_messages table initialized")

    # ============================================================================
    # Alarms
    # ============================================================================

    def init_alarms_table(self):
        """Initialize the alarms table for persisted scheduled alarms."""
        query = """
        CREATE TABLE IF NOT EXISTS main.alarms (
            id TEXT PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            creator_id BIGINT,
            channel_id BIGINT,
            message TEXT,
            tts BOOLEAN DEFAULT FALSE,
            tone BOOLEAN DEFAULT FALSE,
            alternate BOOLEAN DEFAULT FALSE,
            repeat INTEGER DEFAULT 1,
            interval_seconds INTEGER DEFAULT NULL,
            fire_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fired BOOLEAN DEFAULT FALSE
        )
        """
        self.execute_query(query, fetch=False)

        # Indexes for faster lookup
        try:
            idx_q = """
            CREATE INDEX ASYNC IF NOT EXISTS idx_alarms_guild
            ON main.alarms (guild_id)
            """
            self.execute_query(idx_q, fetch=False)
        except Exception:
            pass

        try:
            idx_q2 = """
            CREATE INDEX ASYNC IF NOT EXISTS idx_alarms_fire_at
            ON main.alarms (fire_at)
            """
            self.execute_query(idx_q2, fetch=False)
        except Exception:
            pass

        print("✅ alarms table initialized")

    def add_alarm(self, alarm_id: str, guild_id: int, creator_id: int, channel_id: int, message: str, tts: bool, tone: bool, alternate: bool, repeat: int, interval_seconds: int, fire_at: str):
        """Persist a new alarm. `fire_at` should be a timestamp string accepted by the DB (ISO)."""
        # Delete any existing row with same id just in case
        try:
            delete_q = "DELETE FROM main.alarms WHERE id = %s"
            self.execute_query(delete_q, (alarm_id,), fetch=False)
        except Exception:
            pass

        insert_q = """
        INSERT INTO main.alarms (id, guild_id, creator_id, channel_id, message, tts, tone, alternate, repeat, interval_seconds, fire_at, created_at, fired)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, FALSE)
        """
        # store booleans as 'true'/'false' strings for Aurora DSQL compatibility
        self.execute_query(insert_q, (
            alarm_id,
            guild_id,
            creator_id,
            channel_id,
            message,
            'true' if tts else 'false',
            'true' if tone else 'false',
            'true' if alternate else 'false',
            int(repeat),
            int(interval_seconds) if interval_seconds is not None else None,
            fire_at
        ), fetch=False)

    def get_all_pending_alarms(self):
        """Return all non-fired alarms as list of rows."""
        # include repeat column
        query = "SELECT id, guild_id, creator_id, channel_id, message, tts, tone, alternate, repeat, interval_seconds, fire_at FROM main.alarms WHERE fired = FALSE"
        return self.execute_query(query)

    def get_alarms_for_guild(self, guild_id: int):
        # include repeat column
        query = "SELECT id, guild_id, creator_id, channel_id, message, tts, tone, alternate, repeat, interval_seconds, fire_at FROM main.alarms WHERE fired = FALSE AND guild_id = %s ORDER BY fire_at"
        return self.execute_query(query, (guild_id,))

    def mark_alarm_fired(self, alarm_id: str):
        query = "UPDATE main.alarms SET fired = TRUE WHERE id = %s"
        self.execute_query(query, (alarm_id,), fetch=False)

    def delete_alarm(self, alarm_id: str):
        query = "DELETE FROM main.alarms WHERE id = %s"
        self.execute_query(query, (alarm_id,), fetch=False)
    
    def add_message_mirror(self, guild_id: int, source_channel_id: int, target_channel_id: int):
        """Add a message mirror configuration."""
        # Aurora DSQL pattern: Delete then insert
        delete_query = """
        DELETE FROM main.message_mirrors
        WHERE guild_id = %s AND source_channel_id = %s AND target_channel_id = %s
        """
        self.execute_query(delete_query, (guild_id, source_channel_id, target_channel_id), fetch=False)
        
        insert_query = """
        INSERT INTO main.message_mirrors (guild_id, source_channel_id, target_channel_id, created_at)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        """
        self.execute_query(insert_query, (guild_id, source_channel_id, target_channel_id), fetch=False)
        print(f"✅ Added message mirror: guild={guild_id}, source={source_channel_id}, target={target_channel_id}")
    
    def remove_message_mirror(self, guild_id: int, source_channel_id: int, target_channel_id: int):
        """Remove a message mirror configuration."""
        query = """
        DELETE FROM main.message_mirrors
        WHERE guild_id = %s AND source_channel_id = %s AND target_channel_id = %s
        """
        self.execute_query(query, (guild_id, source_channel_id, target_channel_id), fetch=False)
        print(f"✅ Removed message mirror: guild={guild_id}, source={source_channel_id}, target={target_channel_id}")
    
    def get_message_mirrors(self, guild_id: int, source_channel_id: int = None):
        """Get message mirror configurations for a guild or specific source channel."""
        if source_channel_id:
            query = """
            SELECT source_channel_id, target_channel_id, created_at
            FROM main.message_mirrors
            WHERE guild_id = %s AND source_channel_id = %s
            ORDER BY created_at ASC
            """
            result = self.execute_query(query, (guild_id, source_channel_id))
        else:
            query = """
            SELECT source_channel_id, target_channel_id, created_at
            FROM main.message_mirrors
            WHERE guild_id = %s
            ORDER BY source_channel_id, created_at ASC
            """
            result = self.execute_query(query, (guild_id,))
        
        if result:
            return [
                {
                    'source_channel_id': row[0],
                    'target_channel_id': row[1],
                    'created_at': row[2]
                }
                for row in result
            ]
        return []
    
    def track_mirrored_message(self, original_message_id: int, original_channel_id: int, 
                               mirror_message_id: int, mirror_channel_id: int, guild_id: int):
        """Track a mirrored message for future updates/deletes."""
        # Aurora DSQL pattern: Delete then insert
        delete_query = """
        DELETE FROM main.mirrored_messages
        WHERE original_message_id = %s AND mirror_channel_id = %s
        """
        self.execute_query(delete_query, (original_message_id, mirror_channel_id), fetch=False)
        
        insert_query = """
        INSERT INTO main.mirrored_messages 
        (original_message_id, original_channel_id, mirror_message_id, mirror_channel_id, guild_id, created_at)
        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """
        self.execute_query(insert_query, (original_message_id, original_channel_id, 
                                          mirror_message_id, mirror_channel_id, guild_id), fetch=False)
    
    def get_mirrored_messages(self, original_message_id: int):
        """Get all mirror copies of an original message."""
        query = """
        SELECT mirror_message_id, mirror_channel_id, guild_id
        FROM main.mirrored_messages
        WHERE original_message_id = %s
        """
        result = self.execute_query(query, (original_message_id,))
        
        if result:
            return [
                {
                    'mirror_message_id': row[0],
                    'mirror_channel_id': row[1],
                    'guild_id': row[2]
                }
                for row in result
            ]
        return []
    
    def delete_mirrored_message_tracking(self, original_message_id: int):
        """Delete all tracking entries for an original message."""
        query = """
        DELETE FROM main.mirrored_messages
        WHERE original_message_id = %s
        """
        self.execute_query(query, (original_message_id,), fetch=False)
    
    def search_saved_emojis(self, search_term: Optional[str] = None, limit: int = 25, only_stickers: bool = False, only_emojis: bool = False):
        """Search saved emojis/stickers by name."""
        conditions = []
        params = []
        
        if search_term:
            conditions.append("name ILIKE %s")
            params.append(f'%{search_term}%')
        
        if only_stickers:
            conditions.append("is_sticker = TRUE")
        elif only_emojis:
            conditions.append("is_sticker = FALSE")
        
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(limit)
        
        query = f"""
        SELECT id, name, image_data, animated, is_sticker, sticker_description, saved_by_user_id, saved_from_guild_id, created_at, notes
        FROM main.saved_emojis
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %s
        """
        results = self.execute_query(query, tuple(params))
        
        if results:
            return [
                {
                    'id': row[0],
                    'name': row[1],
                    'image_data': row[2],
                    'animated': row[3],
                    'is_sticker': row[4],
                    'sticker_description': row[5],
                    'saved_by_user_id': row[6],
                    'saved_from_guild_id': row[7],
                    'created_at': row[8],
                    'notes': row[9]
                }
                for row in results
            ]
        return []
    
    def delete_saved_emoji(self, emoji_id: int):
        """Delete a saved emoji."""
        query = "DELETE FROM main.saved_emojis WHERE id = %s"
        self.execute_query(query, (emoji_id,), fetch=False)

    # ========================================================================
    # ROLE RULES
    # ========================================================================
    
    def init_role_rules_table(self):
        """Create role_rules table if it doesn't exist (Aurora DSQL compatible)."""
        query = """
        CREATE TABLE IF NOT EXISTS main.role_rules (
            id BIGINT PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            rule_name VARCHAR(100) NOT NULL,
            trigger_role_id BIGINT NOT NULL,
            roles_to_add TEXT,
            roles_to_remove TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(guild_id, rule_name)
        )
        """
        self.execute_query(query, fetch=False)
        print("✅ role_rules table initialized")
    
    def add_role_rule(self, guild_id: int, rule_name: str, trigger_role_id: int, 
                      roles_to_add: list[int] = None, roles_to_remove: list[int] = None):
        """
        Add or update a role rule.
        
        Args:
            guild_id: Guild ID
            rule_name: Name for this rule (e.g., "verified_roles")
            trigger_role_id: Role ID that triggers this rule when added
            roles_to_add: List of role IDs to add when triggered
            roles_to_remove: List of role IDs to remove when triggered
        """
        roles_to_add = roles_to_add or []
        roles_to_remove = roles_to_remove or []
        
        # Convert lists to comma-separated strings
        add_str = ','.join(str(rid) for rid in roles_to_add) if roles_to_add else ''
        remove_str = ','.join(str(rid) for rid in roles_to_remove) if roles_to_remove else ''
        
        # Generate ID from MAX + 1
        max_id_query = "SELECT COALESCE(MAX(id), 0) FROM main.role_rules"
        max_id_result = self.execute_query(max_id_query)
        new_id = (max_id_result[0][0] if max_id_result else 0) + 1
        
        query = """
        INSERT INTO main.role_rules (id, guild_id, rule_name, trigger_role_id, roles_to_add, roles_to_remove, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (guild_id, rule_name) 
        DO UPDATE SET 
            trigger_role_id = EXCLUDED.trigger_role_id,
            roles_to_add = EXCLUDED.roles_to_add,
            roles_to_remove = EXCLUDED.roles_to_remove,
            updated_at = CURRENT_TIMESTAMP
        """
        self.execute_query(query, (new_id, guild_id, rule_name, trigger_role_id, add_str, remove_str), fetch=False)
    
    def remove_role_rule(self, guild_id: int, rule_name: str):
        """Remove a role rule by name."""
        query = "DELETE FROM main.role_rules WHERE guild_id = %s AND rule_name = %s"
        self.execute_query(query, (guild_id, rule_name), fetch=False)
    
    def get_role_rules(self, guild_id: int):
        """Get all role rules for a guild."""
        query = """
        SELECT id, rule_name, trigger_role_id, roles_to_add, roles_to_remove, created_at, updated_at
        FROM main.role_rules
        WHERE guild_id = %s
        ORDER BY rule_name
        """
        results = self.execute_query(query, (guild_id,))
        
        if results:
            rules = []
            for row in results:
                # Parse comma-separated strings back to lists of ints
                add_str = row[3] or ''
                remove_str = row[4] or ''
                
                add_ids = [int(rid) for rid in add_str.split(',') if rid] if add_str else []
                remove_ids = [int(rid) for rid in remove_str.split(',') if rid] if remove_str else []
                
                rules.append({
                    'id': row[0],
                    'rule_name': row[1],
                    'trigger_role_id': row[2],
                    'roles_to_add': add_ids,
                    'roles_to_remove': remove_ids,
                    'created_at': row[5],
                    'updated_at': row[6]
                })
            return rules
        return []
    
    def get_role_rule(self, guild_id: int, rule_name: str):
        """Get a specific role rule."""
        query = """
        SELECT id, rule_name, trigger_role_id, roles_to_add, roles_to_remove, created_at, updated_at
        FROM main.role_rules
        WHERE guild_id = %s AND rule_name = %s
        """
        result = self.execute_query(query, (guild_id, rule_name))
        
        if result:
            row = result[0]
            # Parse comma-separated strings back to lists of ints
            add_str = row[3] or ''
            remove_str = row[4] or ''
            
            add_ids = [int(rid) for rid in add_str.split(',') if rid] if add_str else []
            remove_ids = [int(rid) for rid in remove_str.split(',') if rid] if remove_str else []
            
            return {
                'id': row[0],
                'rule_name': row[1],
                'trigger_role_id': row[2],
                'roles_to_add': add_ids,
                'roles_to_remove': remove_ids,
                'created_at': row[5],
                'updated_at': row[6]
            }
        return None

    # ========================================================================
    # CONDITIONAL ROLE ASSIGNMENTS
    # ========================================================================
    
    def init_conditional_roles_tables(self):
        """Create conditional role assignment tables."""
        # Table for role configurations (which roles have conditional assignment)
        config_query = """
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
        """
        self.execute_query(config_query, fetch=False)
        
        # Add deferral_role_ids column if it doesn't exist (for existing tables)
        try:
            alter_query = """
            ALTER TABLE main.conditional_role_configs 
            ADD COLUMN IF NOT EXISTS deferral_role_ids TEXT
            """
            self.execute_query(alter_query, fetch=False)
        except Exception as e:
            print(f"Note: Could not add deferral_role_ids column (may already exist): {e}")
        
        # Table for user eligibility
        eligibility_query = """
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
        """
        self.execute_query(eligibility_query, fetch=False)
        print("✅ conditional_role_configs and conditional_role_eligibility tables initialized")
    
    # Configuration management
    def add_conditional_role_config(self, guild_id: int, role_id: int, role_name: str = None, 
                                   blocking_role_ids: list[int] = None, deferral_role_ids: list[int] = None):
        """Add or update a conditional role configuration.
        
        Args:
            guild_id: Guild ID
            role_id: Role to configure
            role_name: Name of the role
            blocking_role_ids: Roles that prevent assignment
            deferral_role_ids: Roles that trigger deferred assignment (mark eligible but don't assign)
        """
        blocking_role_ids = blocking_role_ids or []
        deferral_role_ids = deferral_role_ids or []
        
        # Convert lists to comma-separated strings
        blocking_str = ','.join(str(rid) for rid in blocking_role_ids) if blocking_role_ids else ''
        deferral_str = ','.join(str(rid) for rid in deferral_role_ids) if deferral_role_ids else ''
        
        query = """
        INSERT INTO main.conditional_role_configs (guild_id, role_id, role_name, blocking_role_ids, deferral_role_ids, updated_at)
        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (guild_id, role_id) 
        DO UPDATE SET 
            role_name = EXCLUDED.role_name,
            blocking_role_ids = EXCLUDED.blocking_role_ids,
            deferral_role_ids = EXCLUDED.deferral_role_ids,
            updated_at = CURRENT_TIMESTAMP
        """
        self.execute_query(query, (guild_id, role_id, role_name, blocking_str, deferral_str), fetch=False)
    
    def remove_conditional_role_config(self, guild_id: int, role_id: int):
        """Remove a conditional role configuration and all associated eligibility records."""
        # Delete eligibility records first
        self.execute_query("DELETE FROM main.conditional_role_eligibility WHERE guild_id = %s AND role_id = %s", 
                          (guild_id, role_id), fetch=False)
        # Delete config
        self.execute_query("DELETE FROM main.conditional_role_configs WHERE guild_id = %s AND role_id = %s", 
                          (guild_id, role_id), fetch=False)
    
    def get_conditional_role_config(self, guild_id: int, role_id: int):
        """Get a specific conditional role configuration."""
        query = """
        SELECT role_id, role_name, blocking_role_ids, deferral_role_ids, created_at, updated_at
        FROM main.conditional_role_configs
        WHERE guild_id = %s AND role_id = %s
        """
        result = self.execute_query(query, (guild_id, role_id))
        
        if result:
            row = result[0]
            # Parse comma-separated strings back to lists of ints
            blocking_str = row[2] or ''
            deferral_str = row[3] or ''
            
            blocking_ids = [int(rid) for rid in blocking_str.split(',') if rid] if blocking_str else []
            deferral_ids = [int(rid) for rid in deferral_str.split(',') if rid] if deferral_str else []
            
            return {
                'role_id': row[0],
                'role_name': row[1],
                'blocking_role_ids': blocking_ids,
                'deferral_role_ids': deferral_ids,
                'created_at': row[4],
                'updated_at': row[5]
            }
        return None
    
    def get_all_conditional_role_configs(self, guild_id: int):
        """Get all conditional role configurations for a guild."""
        query = """
        SELECT role_id, role_name, blocking_role_ids, deferral_role_ids, created_at, updated_at
        FROM main.conditional_role_configs
        WHERE guild_id = %s
        ORDER BY role_name
        """
        results = self.execute_query(query, (guild_id,))
        
        if results:
            configs = []
            for row in results:
                # Parse comma-separated strings back to lists of ints
                blocking_str = row[2] or ''
                deferral_str = row[3] or ''
                
                blocking_ids = [int(rid) for rid in blocking_str.split(',') if rid] if blocking_str else []
                deferral_ids = [int(rid) for rid in deferral_str.split(',') if rid] if deferral_str else []
                
                configs.append({
                    'role_id': row[0],
                    'role_name': row[1],
                    'blocking_role_ids': blocking_ids,
                    'deferral_role_ids': deferral_ids,
                    'created_at': row[4],
                    'updated_at': row[5]
                })
            return configs
        return []
    
    # Eligibility management
    def mark_conditional_role_eligible(self, guild_id: int, user_id: int, role_id: int, 
                                       marked_by_user_id: int = None, notes: str = None):
        """Mark a user as deferred for a conditional role (tracks them in eligibility table)."""
        query = """
        INSERT INTO main.conditional_role_eligibility (guild_id, user_id, role_id, marked_at, marked_by_user_id, notes)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s, %s)
        ON CONFLICT (guild_id, user_id, role_id) 
        DO UPDATE SET 
            marked_at = CURRENT_TIMESTAMP,
            marked_by_user_id = EXCLUDED.marked_by_user_id,
            notes = EXCLUDED.notes
        """
        self.execute_query(query, (guild_id, user_id, role_id, marked_by_user_id, notes), fetch=False)
    
    def unmark_conditional_role_eligible(self, guild_id: int, user_id: int, role_id: int):
        """Remove conditional role eligibility for a user."""
        query = "DELETE FROM main.conditional_role_eligibility WHERE guild_id = %s AND user_id = %s AND role_id = %s"
        self.execute_query(query, (guild_id, user_id, role_id), fetch=False)
    
    def is_conditional_role_eligible(self, guild_id: int, user_id: int, role_id: int) -> bool:
        """Check if a user is tracked for deferred conditional role (presence in table = deferred)."""
        query = """
        SELECT 1 FROM main.conditional_role_eligibility 
        WHERE guild_id = %s AND user_id = %s AND role_id = %s
        """
        result = self.execute_query(query, (guild_id, user_id, role_id))
        return bool(result)
    
    def get_conditional_role_eligibility(self, guild_id: int, user_id: int, role_id: int):
        """Get eligibility details for a user and conditional role."""
        query = """
        SELECT marked_at, marked_by_user_id, notes
        FROM main.conditional_role_eligibility
        WHERE guild_id = %s AND user_id = %s AND role_id = %s
        """
        result = self.execute_query(query, (guild_id, user_id, role_id))
        if result:
            return {
                'marked_at': result[0][0],
                'marked_by_user_id': result[0][1],
                'notes': result[0][2]
            }
        return None
    
    def get_conditional_role_eligible_users(self, guild_id: int, role_id: int):
        """Get all users eligible for a specific conditional role."""
        query = """
        SELECT user_id, marked_at, marked_by_user_id, notes
        FROM main.conditional_role_eligibility
        WHERE guild_id = %s AND role_id = %s AND eligible = TRUE
        ORDER BY marked_at DESC
        """
        results = self.execute_query(query, (guild_id, role_id))
        
        if results:
            return [
                {
                    'user_id': row[0],
                    'marked_at': row[1],
                    'marked_by_user_id': row[2],
                    'notes': row[3]
                }
                for row in results
            ]
        return []
    
    def get_user_conditional_role_eligibilities(self, guild_id: int, user_id: int):
        """Get all conditional roles a user is eligible for."""
        query = """
        SELECT role_id, marked_at, marked_by_user_id, notes
        FROM main.conditional_role_eligibility
        WHERE guild_id = %s AND user_id = %s AND eligible = TRUE
        ORDER BY marked_at DESC
        """
        results = self.execute_query(query, (guild_id, user_id))
        
        if results:
            return [
                {
                    'role_id': row[0],
                    'marked_at': row[1],
                    'marked_by_user_id': row[2],
                    'notes': row[3]
                }
                for row in results
            ]
        return []

# Global database instance
db = Database()

if __name__ == "__main__":
    # Test database connection
    print("Testing database connection...")
    try:
        db.init_pool()
        result = db.execute_query("SELECT version(), current_database(), current_user")
        print(f"✅ Connected to database successfully!")
        print(f"   Database version: {result[0][0]}")
        print(f"   Current database: {result[0][1]}")
        print(f"   Current user: {result[0][2]}")
        
        db.close_pool()
    except Exception as e:
        print(f"❌ Connection failed: {e}")
