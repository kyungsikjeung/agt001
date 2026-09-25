"""유입·전환 단계 이벤트 (DECISIONS.md D16)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "funnel_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("visitor_id", sa.Text()),
        sa.Column("session_id", sa.Text()),
        sa.Column("source", sa.Text()),
        sa.Column("campaign", sa.Text()),
        sa.Column("template_id", sa.Text()),
    )
    op.create_index("ix_funnel_events_event_ts", "funnel_events", ["event", "ts"])
    op.create_index("ix_funnel_events_visitor", "funnel_events", ["visitor_id"])
    op.create_index("ix_funnel_events_ts", "funnel_events", ["ts"])


def downgrade() -> None:
    op.drop_index("ix_funnel_events_ts", table_name="funnel_events")
    op.drop_index("ix_funnel_events_visitor", table_name="funnel_events")
    op.drop_index("ix_funnel_events_event_ts", table_name="funnel_events")
    op.drop_table("funnel_events")
