"""Add TISS templates table

Revision ID: add_tiss_templates
Revises: 2a77b43d4b6f
Create Date: 2025-01-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_tiss_templates'
down_revision: Union[str, None] = '2a77b43d4b6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create tiss_templates table
    op.create_table('tiss_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.Enum('consultation', 'procedure', 'exam', 'emergency', 'custom', name='tisstemplatecategory'), nullable=False),
        sa.Column('xml_template', sa.Text(), nullable=False),
        sa.Column('variables', sa.JSON(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('clinic_id', sa.Integer(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], ),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tiss_templates_id'), 'tiss_templates', ['id'], unique=False)
    op.create_index(op.f('ix_tiss_templates_name'), 'tiss_templates', ['name'], unique=False)
    op.create_index(op.f('ix_tiss_templates_clinic_id'), 'tiss_templates', ['clinic_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tiss_templates_clinic_id'), table_name='tiss_templates')
    op.drop_index(op.f('ix_tiss_templates_name'), table_name='tiss_templates')
    op.drop_index(op.f('ix_tiss_templates_id'), table_name='tiss_templates')
    op.drop_table('tiss_templates')
    op.execute("DROP TYPE IF EXISTS tisstemplatecategory")

