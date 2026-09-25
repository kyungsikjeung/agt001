"""세션에 요구사항 카드(JSONB) 추가 (REQUIREMENTS_ENGINE_PLAN.md §5)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("prd", JSONB()))


def downgrade() -> None:
    op.drop_column("sessions", "prd")
