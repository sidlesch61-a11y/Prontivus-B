"""
Helper script to create migration without database connection
Run this if you want to generate migration files before creating the database
"""

import sys
from alembic import command
from alembic.config import Config

# Load alembic configuration
alembic_cfg = Config("alembic.ini")

# Set SQL Alchemy URL to a dummy value
alembic_cfg.set_main_option(
    "sqlalchemy.url", 
    "postgresql+asyncpg://postgres:password@localhost:5432/dummy"
)

try:
    # Generate migration
    command.revision(
        alembic_cfg,
        message="Initial migration: Create clinics, users, patients, and appointments tables",
        autogenerate=True
    )
    print("✅ Migration created successfully!")
    print("⚠️  Remember to create the database and run: alembic upgrade head")
except Exception as e:
    print(f"❌ Error creating migration: {e}")
    sys.exit(1)

