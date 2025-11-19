"""change_message_status_to_varchar

Revision ID: 0bda79913943
Revises: c016d293bcd4
Create Date: 2025-11-19 10:19:19.330561

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0bda79913943'
down_revision: Union[str, None] = 'c016d293bcd4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # First, remove the default value that depends on the enum type
    op.execute("""
        ALTER TABLE messages 
        ALTER COLUMN status DROP DEFAULT
    """)
    
    # Alter the status column from ENUM to VARCHAR
    # Convert existing enum values to strings
    op.execute("""
        ALTER TABLE messages 
        ALTER COLUMN status TYPE VARCHAR(50) 
        USING status::text
    """)
    
    # Set the new default value as a string
    op.execute("""
        ALTER TABLE messages 
        ALTER COLUMN status SET DEFAULT 'sent'
    """)
    
    # Drop the enum type if it exists (only if not used elsewhere)
    # Check if enum is used in other tables
    connection = op.get_bind()
    result = connection.execute(sa.text("""
        SELECT COUNT(*) 
        FROM information_schema.columns 
        WHERE udt_name = 'messagestatus'
    """)).scalar()
    
    if result == 0:
        # No other columns use this enum, safe to drop
        op.execute("DROP TYPE IF EXISTS messagestatus")


def downgrade() -> None:
    # Recreate the enum type
    op.execute("""
        CREATE TYPE messagestatus AS ENUM ('sent', 'delivered', 'read')
    """)
    
    # Convert the column back to ENUM
    op.execute("""
        ALTER TABLE messages 
        ALTER COLUMN status TYPE messagestatus 
        USING status::messagestatus
    """)
