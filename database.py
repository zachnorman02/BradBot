"""
Database con    def __init__(self):
        self.host = os.getenv('DB_HOST')
        self.port = int(os.getenv('DB_PORT', '5432'))
        self.database = os.getenv('DB_NAME', 'postgres')
        self.user = os.getenv('DB_USER', 'bradbotrole')
        self.use_iam_auth = os.getenv('USE_IAM_AUTH', 'true').lower() == 'true'n and utilities for BradBot
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
        self.user = os.getenv('DB_USER', 'BradBotRole')
        self.use_iam_auth = os.getenv('USE_IAM_AUTH', 'true').lower() == 'true'
        self.region = os.getenv('AWS_REGION', 'us-east-1')
        self.connection_pool: Optional[pool.SimpleConnectionPool] = None
        
    def _get_iam_token(self) -> str:
        """Generate IAM authentication token for Aurora DSQL"""
        
        # Use the default credential chain (EC2 instance role)
        session = boto3.Session(region_name=self.region)
        
        # Use RDS client to generate token - this works for DSQL endpoints too
        rds_client = session.client('rds', region_name=self.region)
        
        # Generate authentication token
        token = rds_client.generate_db_auth_token(
            DBHostname=self.host,
            Port=self.port,
            DBUsername=self.user,
            Region=self.region
        )
        return token
    
    def get_connection_params(self) -> dict:
        """Get connection parameters for database"""
        params = {
            'host': self.host,
            'port': self.port,
            'database': self.database,
            'user': self.user,
            'sslmode': 'require'
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
        """Get a connection from the pool"""
        if not self.connection_pool:
            self.init_pool()
        return self.connection_pool.getconn()
    
    def release_connection(self, conn):
        """Release a connection back to the pool"""
        if self.connection_pool:
            self.connection_pool.putconn(conn)
    
    def close_pool(self):
        """Close all connections in the pool"""
        if self.connection_pool:
            self.connection_pool.closeall()
            self.connection_pool = None
    
    def execute_query(self, query: str, params: tuple = None, fetch: bool = True):
        """Execute a query and return results"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                if fetch:
                    return cursor.fetchall()
                conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self.release_connection(conn)
    
    def execute_many(self, query: str, params_list: list):
        """Execute a query with multiple parameter sets"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.executemany(query, params_list)
                conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
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
        """
        result = self.execute_query(query, (user_id, guild_id))
        if result:
            return result[0][0].lower() == 'true'
        return True  # Default: notifications enabled
    
    def set_user_reply_notifications(self, user_id: int, guild_id: int, enabled: bool):
        """Set user's reply notification preference"""
        query = """
        INSERT INTO main.settings (entity_type, entity_id, guild_id, setting_name, setting_value, created_at, updated_at)
        VALUES ('user', %s, %s, 'reply_notifications', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (entity_type, entity_id, guild_id, setting_name) 
        DO UPDATE SET 
            setting_value = EXCLUDED.setting_value,
            updated_at = CURRENT_TIMESTAMP
        """
        self.execute_query(query, (user_id, guild_id, 'true' if enabled else 'false'), fetch=False)
    
    # Message tracking methods
    def store_message_tracking(self, bot_message_id: int, user_id: int, guild_id: int, 
                               original_url: str, fixed_url: str):
        """Store tracking information for a bot's replacement message"""
        query = """
        INSERT INTO message_tracking (message_id, user_id, guild_id, original_url, fixed_url)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (message_id) DO NOTHING
        """
        self.execute_query(query, (bot_message_id, user_id, guild_id, original_url, fixed_url), fetch=False)
    
    def get_message_original_user(self, bot_message_id: int) -> Optional[tuple]:
        """Get original user info for a bot message. Returns (user_id, guild_id) or None"""
        query = "SELECT user_id, guild_id FROM message_tracking WHERE message_id = %s"
        result = self.execute_query(query, (bot_message_id,))
        if result:
            return result[0]
        return None

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
