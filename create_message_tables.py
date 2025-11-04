"""
Script to create message_threads and messages tables
Run this script to create the necessary tables for the messaging system
"""
import asyncio
from sqlalchemy import text
from database import AsyncSessionLocal, engine

async def create_message_tables():
    """Create message_threads and messages tables"""
    async with AsyncSessionLocal() as db:
        try:
            # Create message_threads table
            await db.execute(text("""
                CREATE TABLE IF NOT EXISTS message_threads (
                    id SERIAL PRIMARY KEY,
                    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                    provider_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    topic VARCHAR(200),
                    is_urgent BOOLEAN NOT NULL DEFAULT FALSE,
                    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE,
                    last_message_at TIMESTAMP WITH TIME ZONE,
                    clinic_id INTEGER NOT NULL REFERENCES clinics(id) ON DELETE CASCADE
                )
            """))
            
            # Create indexes
            await db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_message_threads_patient_id 
                ON message_threads(patient_id)
            """))
            
            await db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_message_threads_provider_id 
                ON message_threads(provider_id)
            """))
            
            await db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_message_threads_clinic_id 
                ON message_threads(clinic_id)
            """))
            
            # Create messages table
            await db.execute(text("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    thread_id INTEGER NOT NULL REFERENCES message_threads(id) ON DELETE CASCADE,
                    sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    sender_type VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'sent',
                    attachments JSONB,
                    medical_context JSONB,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    read_at TIMESTAMP WITH TIME ZONE
                )
            """))
            
            # Create indexes for messages
            await db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_messages_thread_id 
                ON messages(thread_id)
            """))
            
            await db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_messages_sender_id 
                ON messages(sender_id)
            """))
            
            await db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_messages_created_at 
                ON messages(created_at)
            """))
            
            await db.commit()
            print("✅ Message tables created successfully!")
            
        except Exception as e:
            await db.rollback()
            print(f"❌ Error creating tables: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(create_message_tables())

