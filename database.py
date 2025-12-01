"""
Database connection and utilities for BradBot
Supports Aurora DSQL with IAM authentication
"""
import os
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
    def get_user_reply_notifications(self, user_id: int, guild_id: int) -> bool:
        """Get user's reply notification preference. Defaults to True if not set."""
        query = """
        SELECT setting_value FROM main.settings 
        WHERE entity_type = 'user' 
        AND entity_id = %s 
        AND guild_id = %s 
        AND setting_name = 'reply_notifications'
        ORDER BY updated_at DESC
        LIMIT 1
        """
        result = self.execute_query(query, (user_id, guild_id))
        if result:
            return result[0][0].lower() == 'true'
        return True  # Default: notifications enabled
    
    def set_user_reply_notifications(self, user_id: int, guild_id: int, enabled: bool):
        """Set user's reply notification preference"""
        # Aurora DSQL doesn't support ON CONFLICT, so delete old entries first
        delete_query = """
        DELETE FROM main.settings 
        WHERE entity_type = 'user' 
        AND entity_id = %s 
        AND guild_id = %s 
        AND setting_name = 'reply_notifications'
        """
        self.execute_query(delete_query, (user_id, guild_id), fetch=False)
        
        # Then insert the new value
        insert_query = """
        INSERT INTO main.settings (entity_type, entity_id, guild_id, setting_name, setting_value, created_at, updated_at)
        VALUES ('user', %s, %s, 'reply_notifications', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        self.execute_query(insert_query, (user_id, guild_id, 'true' if enabled else 'false'), fetch=False)
    
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
                          icon_hash: str = None, icon_data: bytes = None):
        """Store or update booster role configuration in database"""
        # Aurora DSQL doesn't support ON CONFLICT, so check if exists first
        check_query = "SELECT 1 FROM main.booster_roles WHERE user_id = %s AND guild_id = %s"
        exists = self.execute_query(check_query, (user_id, guild_id))
        
        if exists:
            # Delete existing record
            delete_query = "DELETE FROM main.booster_roles WHERE user_id = %s AND guild_id = %s"
            self.execute_query(delete_query, (user_id, guild_id), fetch=False)
        
        # Insert new record
        query = """
        INSERT INTO main.booster_roles 
        (user_id, guild_id, role_id, role_name, color_hex, color_type, icon_hash, icon_data, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        self.execute_query(query, (user_id, guild_id, role_id, role_name, color_hex, 
                                   color_type, icon_hash, icon_data), fetch=False)
    
    def get_booster_role(self, user_id: int, guild_id: int) -> Optional[dict]:
        """Get booster role configuration from database. Returns dict or None"""
        query = """
        SELECT role_id, role_name, color_hex, color_type, icon_hash, icon_data, created_at, updated_at
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
                'created_at': row[6],
                'updated_at': row[7]
            }
        return None
    
    def delete_booster_role(self, user_id: int, guild_id: int):
        """Delete booster role configuration from database"""
        query = "DELETE FROM main.booster_roles WHERE user_id = %s AND guild_id = %s"
        self.execute_query(query, (user_id, guild_id), fetch=False)
    
    def get_all_booster_roles(self, guild_id: int) -> list:
        """Get all booster role configurations for a guild. Returns list of dicts"""
        query = """
        SELECT user_id, role_id, role_name, color_hex, color_type, icon_hash, icon_data, created_at, updated_at
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
                'created_at': row[7],
                'updated_at': row[8]
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
