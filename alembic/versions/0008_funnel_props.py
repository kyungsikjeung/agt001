"""디자인 학습 기록(DECISIONS.md D44·D45): 유입 기록에 명세 값 칸

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("funnel_events", sa.Column("props", JSONB()))


def downgrade() -> None:
    op.drop_column("funnel_events", "props")
