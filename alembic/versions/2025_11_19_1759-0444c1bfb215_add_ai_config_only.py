"""add_ai_config_only

Revision ID: 0444c1bfb215
Revises: 8b0178c3735a
Create Date: 2025-11-19 17:59:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0444c1bfb215'
down_revision: Union[str, None] = 'add_password_reset_tokens'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ai_configs table
    op.create_table('ai_configs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('clinic_id', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=True),
    sa.Column('api_key_encrypted', sa.Text(), nullable=True),
    sa.Column('model', sa.String(length=100), nullable=True),
    sa.Column('base_url', sa.String(length=255), nullable=True),
    sa.Column('max_tokens', sa.Integer(), nullable=False),
    sa.Column('temperature', sa.Float(), nullable=False),
    sa.Column('features', sa.JSON(), nullable=False),
    sa.Column('usage_stats', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('clinic_id', name='uq_ai_config_clinic')
    )
    op.create_index(op.f('ix_ai_configs_clinic_id'), 'ai_configs', ['clinic_id'], unique=True)
    op.create_index(op.f('ix_ai_configs_id'), 'ai_configs', ['id'], unique=False)
    
    # Add ai_token_limit column (nullable)
    op.add_column('licenses', sa.Column('ai_token_limit', sa.Integer(), nullable=True))
    
    # Add ai_enabled column as nullable first
    op.add_column('licenses', sa.Column('ai_enabled', sa.Boolean(), nullable=True))
    # Update existing rows: set ai_enabled to False by default
    op.execute("UPDATE licenses SET ai_enabled = false WHERE ai_enabled IS NULL")
    # Now make it NOT NULL
    op.alter_column('licenses', 'ai_enabled', nullable=False)


def downgrade() -> None:
    # Drop ai_configs table
    op.drop_index(op.f('ix_ai_configs_id'), table_name='ai_configs')
    op.drop_index(op.f('ix_ai_configs_clinic_id'), table_name='ai_configs')
    op.drop_table('ai_configs')
    
    # Drop columns from licenses
    op.drop_column('licenses', 'ai_enabled')
    op.drop_column('licenses', 'ai_token_limit')
