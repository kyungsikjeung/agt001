"""스탬프 규칙·적립 기록·쿠폰 (STAMP_WAVE4_CONTRACT §2).

도장 수는 저장하지 않고 stamp_events.delta 합계로만 본다.
같은 주문 적립·회수는 부분 유일 인덱스가 한 번씩만 막는다.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def _now():
    return sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "stamp_rules",
        sa.Column("site_key", sa.Text(), sa.ForeignKey("shops.site_key"), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("goal", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("per", sa.Text(), nullable=False, server_default="order"),
        sa.Column("reward_title", sa.Text(), nullable=False, server_default="음료 1잔 무료"),
        sa.Column("reward_kind", sa.Text(), nullable=False, server_default="free"),
        sa.Column("reward_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coupon_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("updated_by", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.CheckConstraint("goal BETWEEN 2 AND 50", name="ck_stamp_rules_goal"),
        sa.CheckConstraint("per IN ('order', 'item')", name="ck_stamp_rules_per"),
        sa.CheckConstraint("char_length(reward_title) BETWEEN 1 AND 30", name="ck_stamp_rules_title"),
        sa.CheckConstraint("reward_kind IN ('free', 'amount', 'percent')", name="ck_stamp_rules_kind"),
        sa.CheckConstraint("reward_value >= 0", name="ck_stamp_rules_value"),
        sa.CheckConstraint("coupon_days BETWEEN 7 AND 365", name="ck_stamp_rules_days"),
    )
    op.create_table(
        "coupons",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("site_key", sa.Text(), sa.ForeignKey("shops.site_key"), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), sa.ForeignKey("customers.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("code", sa.Text(), nullable=False),  # 12자리 숫자, 서버 난수
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, server_default="free"),
        sa.Column("value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="issued"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("held_order_id", sa.BigInteger(), sa.ForeignKey("orders.id", ondelete="SET NULL")),
        sa.Column("held_until", sa.DateTime(timezone=True)),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("used_by", sa.Text()),
        sa.Column("used_order_id", sa.BigInteger(), sa.ForeignKey("orders.id", ondelete="SET NULL")),
        sa.Column("source", sa.Text(), nullable=False, server_default="stamp"),
        sa.CheckConstraint("code ~ '^[0-9]{12}$'", name="ck_coupons_code"),
        sa.CheckConstraint("kind IN ('free', 'amount', 'percent')", name="ck_coupons_kind"),
        sa.CheckConstraint("value >= 0", name="ck_coupons_value"),
        sa.CheckConstraint("status IN ('issued', 'held', 'used', 'expired')", name="ck_coupons_status"),
        sa.CheckConstraint("source IN ('stamp', 'owner')", name="ck_coupons_source"),
        sa.UniqueConstraint("site_key", "code", name="uq_coupons_site_code"),
    )
    op.create_index("ix_coupons_site_customer_status", "coupons", ["site_key", "customer_id", "status"])
    op.create_table(
        "stamp_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("site_key", sa.Text(), sa.ForeignKey("shops.site_key"), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), sa.ForeignKey("customers.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("orders.id", ondelete="SET NULL")),
        sa.Column("delta", sa.Integer(), nullable=False),  # 0 아님, 합계가 곧 도장 수
        sa.Column("reason", sa.Text(), nullable=False),  # order·refund·manual·reward
        sa.Column("coupon_id", sa.BigInteger(), sa.ForeignKey("coupons.id", ondelete="SET NULL")),
        sa.Column("by_user_id", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.CheckConstraint("delta <> 0", name="ck_stamp_events_delta"),
        sa.CheckConstraint("reason IN ('order', 'refund', 'manual', 'reward')",
                           name="ck_stamp_events_reason"),
    )
    # 같은 주문으로 적립·회수는 한 번씩만 된다.
    op.create_index("uq_stamp_events_order_reason", "stamp_events", ["order_id", "reason"],
                    unique=True, postgresql_where=sa.text("order_id IS NOT NULL"))


def downgrade() -> None:
    op.drop_table("stamp_events")
    op.drop_index("ix_coupons_site_customer_status", table_name="coupons")
    op.drop_table("coupons")
    op.drop_table("stamp_rules")
