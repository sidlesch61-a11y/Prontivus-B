"""add_support_tables

Revision ID: add_support_tables
Revises: dbd8b3e4aa07
Create Date: 2025-01-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'add_support_tables'
down_revision: Union[str, None] = 'add_tasks_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create support_tickets table
    op.create_table(
        'support_tickets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('clinic_id', sa.Integer(), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('open', 'in_progress', 'resolved', 'closed', name='ticketstatus'), nullable=False, server_default='open'),
        sa.Column('priority', sa.Enum('low', 'medium', 'high', 'urgent', name='ticketpriority'), nullable=False, server_default='medium'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_support_tickets_id'), 'support_tickets', ['id'], unique=False)
    op.create_index(op.f('ix_support_tickets_patient_id'), 'support_tickets', ['patient_id'], unique=False)
    op.create_index(op.f('ix_support_tickets_clinic_id'), 'support_tickets', ['clinic_id'], unique=False)

    # Create help_articles table
    op.create_table(
        'help_articles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clinic_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.Column('views', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('helpful_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_help_articles_id'), 'help_articles', ['id'], unique=False)
    op.create_index(op.f('ix_help_articles_clinic_id'), 'help_articles', ['clinic_id'], unique=False)


def downgrade() -> None:
    # Drop help_articles table
    op.drop_index(op.f('ix_help_articles_clinic_id'), table_name='help_articles')
    op.drop_index(op.f('ix_help_articles_id'), table_name='help_articles')
    op.drop_table('help_articles')

    # Drop support_tickets table
    op.drop_index(op.f('ix_support_tickets_clinic_id'), table_name='support_tickets')
    op.drop_index(op.f('ix_support_tickets_patient_id'), table_name='support_tickets')
    op.drop_index(op.f('ix_support_tickets_id'), table_name='support_tickets')
    op.drop_table('support_tickets')

    # Drop enums
    sa.Enum(name='ticketstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='ticketpriority').drop(op.get_bind(), checkfirst=True)

