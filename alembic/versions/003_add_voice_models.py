"""Add voice processing models

Revision ID: 003_add_voice_models
Revises: 002_add_financial_models
Create Date: 2025-10-29 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_add_voice_models'
down_revision = '182de6f89ae4'
branch_labels = None
depends_on = None


def upgrade():
    # Create voice_sessions table
    op.create_table('voice_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(length=255), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('appointment_id', sa.Integer(), nullable=True),
        sa.Column('encrypted_audio_data', sa.LargeBinary(), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('confidence_score', sa.String(length=10), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id')
    )
    op.create_index(op.f('ix_voice_sessions_session_id'), 'voice_sessions', ['session_id'], unique=True)
    op.create_index(op.f('ix_voice_sessions_user_id'), 'voice_sessions', ['user_id'], unique=False)
    op.create_index(op.f('ix_voice_sessions_appointment_id'), 'voice_sessions', ['appointment_id'], unique=False)

    # Create voice_commands table
    op.create_table('voice_commands',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(length=255), nullable=False),
        sa.Column('command_type', sa.String(length=50), nullable=False),
        sa.Column('raw_text', sa.Text(), nullable=False),
        sa.Column('processed_content', sa.Text(), nullable=False),
        sa.Column('confidence_score', sa.String(length=10), nullable=True),
        sa.Column('medical_terms', sa.Text(), nullable=True),
        sa.Column('icd10_codes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['voice_sessions.session_id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_voice_commands_session_id'), 'voice_commands', ['session_id'], unique=False)

    # Create medical_terms table
    op.create_table('medical_terms',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('term', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('icd10_codes', sa.Text(), nullable=True),
        sa.Column('synonyms', sa.Text(), nullable=True),
        sa.Column('confidence', sa.String(length=10), nullable=True),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('region', sa.String(length=10), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_medical_terms_term'), 'medical_terms', ['term'], unique=False)
    op.create_index(op.f('ix_medical_terms_category'), 'medical_terms', ['category'], unique=False)

    # Create voice_configurations table
    op.create_table('voice_configurations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('clinic_id', sa.Integer(), nullable=True),
        sa.Column('provider', sa.String(length=20), nullable=True),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('model', sa.String(length=50), nullable=True),
        sa.Column('enable_auto_punctuation', sa.String(length=10), nullable=True),
        sa.Column('enable_word_time_offsets', sa.String(length=10), nullable=True),
        sa.Column('confidence_threshold', sa.String(length=10), nullable=True),
        sa.Column('custom_terms', sa.Text(), nullable=True),
        sa.Column('enable_icd10_suggestions', sa.String(length=10), nullable=True),
        sa.Column('enable_medication_recognition', sa.String(length=10), nullable=True),
        sa.Column('auto_delete_after_hours', sa.Integer(), nullable=True),
        sa.Column('enable_encryption', sa.String(length=10), nullable=True),
        sa.Column('enable_audit_logging', sa.String(length=10), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_voice_configurations_user_id'), 'voice_configurations', ['user_id'], unique=False)
    op.create_index(op.f('ix_voice_configurations_clinic_id'), 'voice_configurations', ['clinic_id'], unique=False)

    # Insert default medical terms
    op.execute("""
        INSERT INTO medical_terms (term, category, icd10_codes, synonyms, confidence, language, region, created_at, updated_at)
        VALUES 
        ('dor abdominal', 'symptom', '["R10.9", "K59.0"]', '["dor no abdome", "abdominalgia", "dor de barriga"]', '0.95', 'pt-BR', 'BR', NOW(), NOW()),
        ('apendicite', 'diagnosis', '["K35.9"]', '["apendicite aguda", "inflamação do apêndice"]', '0.98', 'pt-BR', 'BR', NOW(), NOW()),
        ('febre', 'symptom', '["R50.9"]', '["hipertermia", "temperatura elevada"]', '0.92', 'pt-BR', 'BR', NOW(), NOW()),
        ('náusea', 'symptom', '["R11.0"]', '["enjoo", "vontade de vomitar"]', '0.90', 'pt-BR', 'BR', NOW(), NOW()),
        ('vômito', 'symptom', '["R11.0"]', '["emese", "vomitar"]', '0.88', 'pt-BR', 'BR', NOW(), NOW()),
        ('cefaleia', 'symptom', '["R51"]', '["dor de cabeça", "cefalalgia"]', '0.94', 'pt-BR', 'BR', NOW(), NOW()),
        ('hipertensão', 'diagnosis', '["I10"]', '["pressão alta", "HAS"]', '0.96', 'pt-BR', 'BR', NOW(), NOW()),
        ('diabetes', 'diagnosis', '["E11.9"]', '["DM", "diabetes mellitus"]', '0.97', 'pt-BR', 'BR', NOW(), NOW()),
        ('hiperglicemia', 'symptom', '["R73.9"]', '["glicose alta", "açúcar alto"]', '0.93', 'pt-BR', 'BR', NOW(), NOW()),
        ('hipoglicemia', 'symptom', '["E16.2"]', '["glicose baixa", "açúcar baixo"]', '0.91', 'pt-BR', 'BR', NOW(), NOW()),
        ('taquicardia', 'symptom', '["R00.0"]', '["coração acelerado", "pulso rápido"]', '0.89', 'pt-BR', 'BR', NOW(), NOW()),
        ('bradicardia', 'symptom', '["R00.1"]', '["coração lento", "pulso lento"]', '0.87', 'pt-BR', 'BR', NOW(), NOW()),
        ('dispneia', 'symptom', '["R06.0"]', '["falta de ar", "dificuldade respiratória"]', '0.92', 'pt-BR', 'BR', NOW(), NOW()),
        ('tosse', 'symptom', '["R05"]', '["tosse seca", "tosse produtiva"]', '0.85', 'pt-BR', 'BR', NOW(), NOW()),
        ('hemoptise', 'symptom', '["R04.2"]', '["tosse com sangue", "expectoração sanguinolenta"]', '0.94', 'pt-BR', 'BR', NOW(), NOW())
    """)


def downgrade():
    # Drop tables in reverse order
    op.drop_table('voice_configurations')
    op.drop_table('medical_terms')
    op.drop_table('voice_commands')
    op.drop_table('voice_sessions')
