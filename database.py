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
        AND setting_name = 'link_replacement'
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
        AND setting_name = 'link_replacement'
        """
        self.execute_query(delete_query, (guild_id,), fetch=False)
        
        # Then insert the new value
        insert_query = """
        INSERT INTO main.guild_settings (guild_id, setting_name, setting_value, created_at, updated_at)
        VALUES (%s, 'link_replacement', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
