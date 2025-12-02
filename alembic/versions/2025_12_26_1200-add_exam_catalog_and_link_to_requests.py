"""Add exam catalog table and link to exam_requests

Revision ID: add_exam_catalog
Revises: add_doctor_consultation_room
Create Date: 2025-12-26 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_exam_catalog"
down_revision: Union[str, None] = "add_doctor_consultation_room"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create exam_catalog table and add exam_catalog_id to exam_requests."""
    op.create_table(
        "exam_catalog",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clinic_id", sa.Integer(), sa.ForeignKey("clinics.id"), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("preparation", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_exam_catalog_id", "exam_catalog", ["id"], unique=False)
    op.create_index("ix_exam_catalog_clinic_id", "exam_catalog", ["clinic_id"], unique=False)
    op.create_index("ix_exam_catalog_name", "exam_catalog", ["name"], unique=False)
    op.create_index("ix_exam_catalog_code", "exam_catalog", ["code"], unique=False)

    # Link exam_requests to exam_catalog (optional)
    op.add_column(
        "exam_requests",
        sa.Column("exam_catalog_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_exam_requests_exam_catalog_id", "exam_requests", ["exam_catalog_id"], unique=False)
    op.create_foreign_key(
        "fk_exam_requests_exam_catalog",
        "exam_requests",
        "exam_catalog",
        ["exam_catalog_id"],
        ["id"],
    )


def downgrade() -> None:
    """Drop exam_catalog_id from exam_requests and remove exam_catalog."""
    op.drop_constraint("fk_exam_requests_exam_catalog", "exam_requests", type_="foreignkey")
    op.drop_index("ix_exam_requests_exam_catalog_id", table_name="exam_requests")
    op.drop_column("exam_requests", "exam_catalog_id")

    op.drop_index("ix_exam_catalog_code", table_name="exam_catalog")
    op.drop_index("ix_exam_catalog_name", table_name="exam_catalog")
    op.drop_index("ix_exam_catalog_clinic_id", table_name="exam_catalog")
    op.drop_index("ix_exam_catalog_id", table_name="exam_catalog")
    op.drop_table("exam_catalog")


