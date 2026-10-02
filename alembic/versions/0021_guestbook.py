"""청첩장 방명록 (EVENT_INVITE_PLAN 3단계).

하객이 공개 사이트에 남긴 이름·글. 사장님(신랑·신부)이 지울 수 있고, 1년 지나면 지운다(guestbook.purge_expired).

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guestbook",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("site_key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 20", name="ck_guestbook_name"),
        sa.CheckConstraint("char_length(message) BETWEEN 1 AND 300", name="ck_guestbook_message"),
    )
    op.create_index("ix_guestbook_site", "guestbook", ["site_key", sa.text("id DESC")])
    op.create_index("ix_guestbook_ts", "guestbook", ["ts"])


def downgrade() -> None:
    op.drop_index("ix_guestbook_ts", table_name="guestbook")
    op.drop_index("ix_guestbook_site", table_name="guestbook")
    op.drop_table("guestbook")
