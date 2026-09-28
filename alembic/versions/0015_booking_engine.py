"""예약 엔진: 명세 판·막기·이벤트·채팅 상태 + bookings 시간 구간·겹침 차단 (BOOKING_BOT_IMPL_PLAN W3)

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def _now():
    return sa.text("now()")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "bot_specs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("shop_id", sa.BigInteger(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("spec", JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.UniqueConstraint("shop_id", "version", name="uq_bot_specs_version"),
        sa.CheckConstraint("status IN ('draft', 'active', 'archived')", name="ck_bot_specs_status"),
    )
    op.create_index("uq_bot_specs_active", "bot_specs", ["shop_id"], unique=True,
                    postgresql_where=sa.text("status = 'active'"))
    op.create_index("uq_bot_specs_draft", "bot_specs", ["shop_id"], unique=True,
                    postgresql_where=sa.text("status = 'draft'"))
    op.create_table(
        "booking_closures",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("shop_id", sa.BigInteger(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_key", sa.Text()),  # null = 가게 전체
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("created_by", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.CheckConstraint("end_at > start_at", name="ck_booking_closures_range"),
    )
    op.create_index("ix_booking_closures_shop", "booking_closures", ["shop_id", "start_at"])

    op.add_column("bookings", sa.Column("shop_id", sa.BigInteger(), sa.ForeignKey("shops.id", ondelete="SET NULL")))
    op.add_column("bookings", sa.Column("start_at", sa.DateTime(timezone=True)))
    op.add_column("bookings", sa.Column("end_at", sa.DateTime(timezone=True)))
    op.add_column("bookings", sa.Column("resource_key", sa.Text()))
    op.add_column("bookings", sa.Column("source", sa.Text()))  # web·chat·phone·owner
    op.add_column("bookings", sa.Column("hold_expires_at", sa.DateTime(timezone=True)))
    op.add_column("bookings", sa.Column("chat_token_hash", sa.Text()))
    op.create_index("ix_bookings_shop_start", "bookings", ["shop_id", "start_at"])
    op.create_index("ix_bookings_chat_token", "bookings", ["chat_token_hash"])
    # 같은 가게·같은 담당자·겹치는 시간은 DB가 거절한다 (BOOK-2). 옛 예약(resource_key 없음)은 대상 밖.
    op.execute(
        "ALTER TABLE bookings ADD CONSTRAINT ex_bookings_resource_overlap EXCLUDE USING gist "
        "(shop_id WITH =, resource_key WITH =, tstzrange(start_at, end_at) WITH &&) "
        "WHERE (status IN ('held', 'requested', 'confirmed') AND resource_key IS NOT NULL)")

    op.create_table(
        "booking_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("booking_id", sa.BigInteger(), sa.ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),  # customer·owner·ai·system
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("detail", JSONB()),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
    )
    op.create_index("ix_booking_events_booking", "booking_events", ["booking_id", "id"])
    op.create_table(
        "agent_threads",
        sa.Column("token_hash", sa.Text(), primary_key=True),
        sa.Column("shop_id", sa.BigInteger(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("draft", JSONB()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
    )


def downgrade() -> None:
    op.drop_table("agent_threads")
    op.drop_table("booking_events")
    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ex_bookings_resource_overlap")
    op.drop_index("ix_bookings_chat_token", "bookings")
    op.drop_index("ix_bookings_shop_start", "bookings")
    for col in ("chat_token_hash", "hold_expires_at", "source", "resource_key", "end_at", "start_at", "shop_id"):
        op.drop_column("bookings", col)
    op.drop_table("booking_closures")
    op.drop_table("bot_specs")
