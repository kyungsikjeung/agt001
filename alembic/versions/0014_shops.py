"""가게·가게 권한 (OWNER_CONSOLE_PLAN §3.1, SALES_DB_PLAN §4.1)

가게 = site_key(sessions.requirement_id)를 그대로 PK로 쓴다. 기존 site_key 표는 고치지 않는다.
기존 데이터 채우기: 공개됐거나 예약·문의·손님·설정이 있는 가게 → shops, 방장이 로그인해 붙인 계정 → owner.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shops",
        sa.Column("site_key", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text()),
        sa.Column("kind", sa.Text()),  # slot·table·night·class (OWNER_CONSOLE_PLAN §4), 모르면 null
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "shop_members",
        sa.Column("site_key", sa.Text(), sa.ForeignKey("shops.site_key", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('owner', 'manager', 'staff')", name="ck_shop_members_role"),
    )
    op.create_index("ix_shop_members_user", "shop_members", ["user_id"])
    op.create_index("uq_shop_members_owner", "shop_members", ["site_key"], unique=True,
                    postgresql_where=sa.text("role = 'owner'"))

    op.execute("""
        INSERT INTO shops (site_key, name)
        SELECT s.requirement_id, NULLIF(btrim(s.prd #>> '{slots,shop_name,value}'), '')
        FROM sessions s
        WHERE s.prd ->> 'published' IS NOT NULL
           OR s.requirement_id IN (SELECT site_key FROM bookings UNION SELECT site_key FROM inquiries
                                   UNION SELECT site_key FROM customers UNION SELECT site_key FROM shop_settings)
        ON CONFLICT DO NOTHING
    """)
    # 방장 = room_members 맨 앞(rooms.owner_id). 그 방장 기기를 계정에 붙인 사람이 owner.
    op.execute("""
        INSERT INTO shop_members (site_key, user_id, role)
        SELECT DISTINCT ON (sh.site_key) sh.site_key, ur.user_id, 'owner'
        FROM shops sh
        JOIN sessions s ON s.requirement_id = sh.site_key
        JOIN rooms r ON r.session_id = s.id
        JOIN LATERAL (SELECT member_id FROM room_members m WHERE m.room_id = r.id
                      ORDER BY m.position LIMIT 1) o ON true
        JOIN user_rooms ur ON ur.room_id = r.id AND ur.member_id = o.member_id
        ORDER BY sh.site_key, ur.claimed_at
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("shop_members")
    op.drop_table("shops")
