"""Add consultation_room field to users (doctor default room)

Revision ID: add_doctor_consultation_room
Revises: add_symptom_tables
Create Date: 2025-12-25 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_doctor_consultation_room"
down_revision: Union[str, None] = "add_symptom_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add consultation_room column to users table."""
    op.add_column(
        "users",
        sa.Column("consultation_room", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    """Remove consultation_room column from users table."""
    op.drop_column("users", "consultation_room")


