"""매출·결제·정산·구독 (SALES_DB_PLAN §4, PAYMENT_PLAN)

돈은 원 단위 정수, 결제·환불 기록은 고치거나 지우지 않고 쌓는다(환불은 refunds 새 행).
주문(orders)은 예약(bookings, 방문 뒤 삭제)과 따로 산다: booking_id는 SET NULL.
시술·담당자는 아직 표가 없어(OWNER_CONSOLE O3) 이름을 스냅샷으로 두고, service_id는 외래키 없이 둔다.

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
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))


def _shop(nullable: bool = False):
    return sa.Column("site_key", sa.Text(), sa.ForeignKey("shops.site_key"), nullable=nullable)


def upgrade() -> None:
    op.add_column("customers", sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="SET NULL")))
    op.create_index("ix_customers_user", "customers", ["user_id"])

    op.create_table(
        "shop_payout",  # 손님 결제 정산 정보(포트원 파트너). 계좌는 Fernet 암호화
        sa.Column("site_key", sa.Text(), sa.ForeignKey("shops.site_key", ondelete="CASCADE"), primary_key=True),
        sa.Column("business_no", sa.Text()),
        sa.Column("owner_name", sa.Text()),
        sa.Column("bank", sa.Text()),
        sa.Column("account_enc", sa.Text()),
        sa.Column("account_last4", sa.Text()),
        sa.Column("holder", sa.Text()),
        sa.Column("portone_partner_id", sa.Text(), unique=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="none"),
        sa.Column("updated_by", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('none', 'pending', 'active', 'rejected')", name="ck_shop_payout_status"),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        _shop(),
        sa.Column("customer_id", sa.BigInteger(), sa.ForeignKey("customers.id", ondelete="SET NULL")),
        sa.Column("booking_id", sa.BigInteger(), sa.ForeignKey("bookings.id", ondelete="SET NULL")),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("subtotal", sa.Integer(), nullable=False),
        sa.Column("discount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("served_at", sa.DateTime(timezone=True)),  # 방문·시술 시각(매출 날짜 기준)
        sa.Column("staff_name", sa.Text()),
        _now(),
        sa.CheckConstraint("channel IN ('online', 'onsite', 'manual')", name="ck_orders_channel"),
        sa.CheckConstraint("status IN ('open', 'paid', 'completed', 'canceled', 'no_show')", name="ck_orders_status"),
        sa.CheckConstraint("discount >= 0 AND total >= 0 AND total = subtotal - discount", name="ck_orders_amounts"),
    )
    op.create_index("ix_orders_shop_served", "orders", ["site_key", "served_at"])
    op.create_index("ix_orders_shop_customer", "orders", ["site_key", "customer_id"])
    op.create_index("ix_orders_booking", "orders", ["booking_id"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        _shop(),
        sa.Column("service_id", sa.BigInteger()),  # booking_services가 생기면 외래키
        sa.Column("name", sa.Text(), nullable=False),  # 그때 이름
        sa.Column("unit_price", sa.Integer(), nullable=False),  # 그때 가격
        sa.Column("qty", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("staff_name", sa.Text()),
        sa.CheckConstraint("qty > 0 AND unit_price >= 0 AND amount >= 0", name="ck_order_items_amounts"),
    )
    op.create_index("ix_order_items_order", "order_items", ["order_id"])
    op.create_index("ix_order_items_shop_name", "order_items", ["site_key", "name"])

    op.create_table(
        "payments",  # A(구독·제작비)·B(손님 주문) 공통 결제 원장. site_key = 어느 가게의 돈인가
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        _shop(),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("orders.id")),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("method", sa.Text()),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_payment_id", sa.Text(), unique=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="ready"),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("raw", JSONB),
        _now(),
        sa.CheckConstraint("kind IN ('order', 'subscription', 'setup_fee')", name="ck_payments_kind"),
        sa.CheckConstraint("(kind = 'order') = (order_id IS NOT NULL)", name="ck_payments_order"),
        sa.CheckConstraint("method IS NULL OR method IN ('card', 'easy_pay', 'transfer', 'cash', 'onsite_card')",
                           name="ck_payments_method"),
        sa.CheckConstraint("provider IN ('portone', 'manual')", name="ck_payments_provider"),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount"),
        sa.CheckConstraint("status IN ('ready', 'paid', 'failed', 'canceled')", name="ck_payments_status"),
    )
    op.create_index("ix_payments_shop_paid", "payments", ["site_key", "paid_at"])
    op.create_index("ix_payments_order", "payments", ["order_id"])

    op.create_table(
        "refunds",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("payment_id", sa.BigInteger(), sa.ForeignKey("payments.id"), nullable=False),
        _shop(),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("by_user_id", sa.Text()),
        sa.Column("provider_cancel_id", sa.Text()),
        _now(),
        sa.CheckConstraint("amount > 0", name="ck_refunds_amount"),
    )
    op.create_index("ix_refunds_payment", "refunds", ["payment_id"])

    op.create_table(
        "settlements",  # 포트원 주문 정산 1건 = 1행
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        _shop(),
        sa.Column("payment_id", sa.BigInteger(), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("portone_transfer_id", sa.Text(), unique=True),
        sa.Column("kind", sa.Text(), nullable=False, server_default="order"),  # order·cancel
        sa.Column("gross", sa.Integer(), nullable=False),
        sa.Column("pg_fee", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("platform_fee", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("net", sa.Integer(), nullable=False),
        sa.Column("settle_date", sa.Date()),
        sa.Column("status", sa.Text(), nullable=False, server_default="scheduled"),
        _now(),
        sa.CheckConstraint("kind IN ('order', 'cancel')", name="ck_settlements_kind"),
        sa.CheckConstraint("status IN ('scheduled', 'in_process', 'settled', 'canceled')", name="ck_settlements_status"),
    )
    op.create_index("ix_settlements_shop_date", "settlements", ["site_key", "settle_date"])
    op.create_index("ix_settlements_payment", "settlements", ["payment_id"])

    op.create_table(
        "subscriptions",  # 우리 요금제(가게 단위). 결제는 payments(kind=subscription)
        sa.Column("site_key", sa.Text(), sa.ForeignKey("shops.site_key"), primary_key=True),
        sa.Column("payer_user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("plan", sa.Text(), nullable=False, server_default="free"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("billing_key_enc", sa.Text()),
        sa.Column("card_last4", sa.Text()),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),
        sa.Column("next_schedule_id", sa.Text()),  # 포트원 결제 예약 id
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("plan IN ('free', 'starter', 'pro', 'medical')", name="ck_subscriptions_plan"),
        sa.CheckConstraint("status IN ('active', 'past_due', 'canceled')", name="ck_subscriptions_status"),
    )

    # 가게별 하루 매출 (SALES_DB_PLAN §6). 날짜는 한국 시간, 환불은 그 주문의 환불 합계를 뺀다.
    # ponytail: 뷰로 매번 계산. 느려지면 밤마다 채우는 일별 집계 표로 바꾼다.
    op.execute("""
        CREATE VIEW v_shop_daily AS
        WITH o AS (
            SELECT o.*,
                   (COALESCE(o.served_at, o.created_at) AT TIME ZONE 'Asia/Seoul')::date AS day,
                   o.customer_id IS NOT NULL AND row_number() OVER (
                       PARTITION BY o.site_key, o.customer_id
                       ORDER BY COALESCE(o.served_at, o.created_at), o.id) = 1 AS first_visit,
                   COALESCE((SELECT sum(r.amount) FROM payments p JOIN refunds r ON r.payment_id = p.id
                             WHERE p.order_id = o.id), 0) AS refunded
            FROM orders o
            WHERE o.status IN ('paid', 'completed', 'no_show')
        )
        SELECT site_key, day,
               count(*) AS orders,
               sum(total) AS gross,
               sum(refunded) AS refunds,
               sum(total) - sum(refunded) AS net,
               count(*) FILTER (WHERE first_visit) AS new_customers,
               count(*) FILTER (WHERE customer_id IS NOT NULL AND NOT first_visit) AS returning_customers,
               count(*) FILTER (WHERE status = 'no_show') AS no_shows
        FROM o
        GROUP BY site_key, day
    """)


def downgrade() -> None:
    op.execute("DROP VIEW v_shop_daily")
    for t in ("subscriptions", "settlements", "refunds", "payments", "order_items", "orders", "shop_payout"):
        op.drop_table(t)
    op.drop_index("ix_customers_user", table_name="customers")
    op.drop_column("customers", "user_id")
