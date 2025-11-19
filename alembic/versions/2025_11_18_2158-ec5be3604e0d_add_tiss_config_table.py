"""add_tiss_config_table

Revision ID: ec5be3604e0d
Revises: add_support_tables
Create Date: 2025-11-18 21:58:36.230491

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ec5be3604e0d'
down_revision: Union[str, None] = 'add_support_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create tiss_config table
    op.create_table(
        'tiss_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clinic_id', sa.Integer(), nullable=False),
        sa.Column('prestador', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('operadora', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('defaults', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('tiss', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tiss_config_id'), 'tiss_config', ['id'], unique=False)
    op.create_index(op.f('ix_tiss_config_clinic_id'), 'tiss_config', ['clinic_id'], unique=True)
    op.create_unique_constraint('uq_tiss_config_clinic', 'tiss_config', ['clinic_id'])


def downgrade() -> None:
    # Drop tiss_config table
    op.drop_constraint('uq_tiss_config_clinic', 'tiss_config', type_='unique')
    op.drop_index(op.f('ix_tiss_config_clinic_id'), table_name='tiss_config')
    op.drop_index(op.f('ix_tiss_config_id'), table_name='tiss_config')
    op.drop_table('tiss_config')
