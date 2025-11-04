"""Add patient calling table

Revision ID: 004_add_patient_calling
Revises: 182de6f89ae4
Create Date: 2025-01-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_add_patient_calling'
down_revision = '182de6f89ae4'
branch_labels = None
depends_on = None


def upgrade():
    # Create patient_calls table
    op.create_table('patient_calls',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('appointment_id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('doctor_id', sa.Integer(), nullable=False),
        sa.Column('clinic_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('called_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('answered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notification_sent', sa.Boolean(), nullable=True),
        sa.Column('notification_type', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], ),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.ForeignKeyConstraint(['doctor_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_patient_calls_appointment_id'), 'patient_calls', ['appointment_id'], unique=False)
    op.create_index(op.f('ix_patient_calls_patient_id'), 'patient_calls', ['patient_id'], unique=False)
    op.create_index(op.f('ix_patient_calls_doctor_id'), 'patient_calls', ['doctor_id'], unique=False)
    op.create_index(op.f('ix_patient_calls_clinic_id'), 'patient_calls', ['clinic_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_patient_calls_clinic_id'), table_name='patient_calls')
    op.drop_index(op.f('ix_patient_calls_doctor_id'), table_name='patient_calls')
    op.drop_index(op.f('ix_patient_calls_patient_id'), table_name='patient_calls')
    op.drop_index(op.f('ix_patient_calls_appointment_id'), table_name='patient_calls')
    op.drop_table('patient_calls')

