"""change tiss template category to string

Revision ID: 9b28f911c2db
Revises: ec5be3604e0d
Create Date: 2025-11-18 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b28f911c2db'
down_revision: Union[str, None] = 'ec5be3604e0d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Change category column from enum to VARCHAR
    # This allows storing enum values as strings without PostgreSQL enum validation
    op.execute("""
        DO $$ 
        BEGIN
            -- Check if column exists and is enum type
            IF EXISTS (
                SELECT 1 
                FROM information_schema.columns 
                WHERE table_name = 'tiss_templates' 
                AND column_name = 'category'
                AND data_type = 'USER-DEFINED'
            ) THEN
                -- Alter column to VARCHAR
                ALTER TABLE tiss_templates 
                ALTER COLUMN category TYPE VARCHAR(50) 
                USING category::text;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Revert category column back to enum type
    # Note: This assumes the enum type still exists
    op.execute("""
        DO $$ 
        BEGIN
            -- Check if enum type exists
            IF EXISTS (
                SELECT 1 
                FROM pg_type 
                WHERE typname = 'tisstemplatecategory'
            ) THEN
                -- Alter column back to enum
                ALTER TABLE tiss_templates 
                ALTER COLUMN category TYPE tisstemplatecategory 
                USING category::tisstemplatecategory;
            END IF;
        END $$;
    """)
