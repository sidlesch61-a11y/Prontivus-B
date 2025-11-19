"""add_expenses_table

Revision ID: c016d293bcd4
Revises: 28d428fcbfe1
Create Date: 2025-11-19 09:31:18.891213

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c016d293bcd4'
down_revision: Union[str, None] = '28d428fcbfe1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create expenses table
    op.create_table(
        'expenses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('vendor', sa.String(length=200), nullable=True),
        sa.Column('paid_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('payment_method', sa.String(length=50), nullable=True),
        sa.Column('payment_reference', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('doctor_id', sa.Integer(), nullable=False),
        sa.Column('clinic_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['doctor_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_expenses_id'), 'expenses', ['id'], unique=False)
    op.create_index(op.f('ix_expenses_description'), 'expenses', ['description'], unique=False)
    op.create_index(op.f('ix_expenses_due_date'), 'expenses', ['due_date'], unique=False)
    op.create_index(op.f('ix_expenses_status'), 'expenses', ['status'], unique=False)
    op.create_index(op.f('ix_expenses_category'), 'expenses', ['category'], unique=False)
    op.create_index(op.f('ix_expenses_doctor_id'), 'expenses', ['doctor_id'], unique=False)
    op.create_index(op.f('ix_expenses_clinic_id'), 'expenses', ['clinic_id'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index(op.f('ix_expenses_clinic_id'), table_name='expenses')
    op.drop_index(op.f('ix_expenses_doctor_id'), table_name='expenses')
    op.drop_index(op.f('ix_expenses_category'), table_name='expenses')
    op.drop_index(op.f('ix_expenses_status'), table_name='expenses')
    op.drop_index(op.f('ix_expenses_due_date'), table_name='expenses')
    op.drop_index(op.f('ix_expenses_description'), table_name='expenses')
    op.drop_index(op.f('ix_expenses_id'), table_name='expenses')
    
    # Drop expenses table
    op.drop_table('expenses')
