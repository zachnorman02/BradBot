"""
Database migration to add poll tables
Run this with: python3 add_poll_tables.py
"""
from database import db

def create_poll_tables():
    """Create the polls and poll_responses tables"""
    
    # Create polls table
    polls_table = """
    CREATE TABLE IF NOT EXISTS main.polls (
        id SERIAL PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        channel_id BIGINT NOT NULL,
        creator_id BIGINT NOT NULL,
        question TEXT NOT NULL,
        message_id BIGINT,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    
    # Create poll_responses table
    responses_table = """
    CREATE TABLE IF NOT EXISTS main.poll_responses (
        id SERIAL PRIMARY KEY,
        poll_id INTEGER NOT NULL,
        user_id BIGINT NOT NULL,
        username TEXT NOT NULL,
        response_text TEXT NOT NULL,
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(poll_id, user_id)
    )
    """
    
    # Create indexes for better query performance
    poll_guild_index = """
    CREATE INDEX IF NOT EXISTS idx_polls_guild_active 
    ON main.polls(guild_id, is_active)
    """
    
    response_poll_index = """
    CREATE INDEX IF NOT EXISTS idx_poll_responses_poll_id 
    ON main.poll_responses(poll_id)
    """
    
    try:
        print("🔧 Creating poll tables...")
        
        # Initialize database connection
        db.init_pool()
        
        # Create tables
        db.execute_query(polls_table, fetch=False)
        print("✅ Created polls table")
        
        db.execute_query(responses_table, fetch=False)
        print("✅ Created poll_responses table")
        
        # Create indexes
        db.execute_query(poll_guild_index, fetch=False)
        print("✅ Created guild/active index on polls")
        
        db.execute_query(response_poll_index, fetch=False)
        print("✅ Created poll_id index on poll_responses")
        
        print("\n🎉 Poll tables created successfully!")
        print("You can now use /poll create to create polls!")
        
    except Exception as e:
        print(f"❌ Error creating poll tables: {e}")
        raise

if __name__ == "__main__":
    create_poll_tables()
