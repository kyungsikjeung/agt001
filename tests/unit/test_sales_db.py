"""가게·매출 표 (Alembic 0014·0015, SALES_DB_PLAN §4): 기존 가게 채우기, 공개 때 가게 행, 금액 검사, 하루 매출 뷰."""
import datetime
import json
import uuid

import pytest
from alembic import command
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db import migrate as db_migrate
from app.db.models import OrderRow, PaymentRow, ShopMemberRow, ShopRow
from app.db.session import get_sessionmaker
from app.services import shops


def _seed_site(db, published=True, claimed=True):
    """세션 + 방(방장 m1, 참여자 m2) + (선택) 방장을 붙인 계정. site_key, room_id, user_id를 돌려준다."""
    u = uuid.uuid4().hex[:8]
    sid, key, rid, uid = f"s_{u}", f"k_{u}", f"r_{u}", f"u_{u}"
    prd = {"slots": {"shop_name": {"value": " 결 헤어 "}}}
    if published:
        prd["published"] = "v2"
    db.execute(text("INSERT INTO sessions (id, state, requirement_id, prd) VALUES (:i, 'DONE', :k, CAST(:p AS jsonb))"),
               {"i": sid, "k": key, "p": json.dumps(prd)})
    db.execute(text("INSERT INTO rooms (id, session_id) VALUES (:r, :s)"), {"r": rid, "s": sid})
    for pos, m in enumerate(["m1", "m2"]):
        db.execute(text("INSERT INTO room_members (room_id, member_id, nickname, joined_at, last_seen, position) "
                        "VALUES (:r, :m, :m, now(), now(), :p)"), {"r": rid, "m": m, "p": pos})
    db.execute(text("INSERT INTO users (id, nickname) VALUES (:u, '사장')"), {"u": uid})
    if claimed:
        db.execute(text("INSERT INTO user_rooms (user_id, room_id, member_id) VALUES (:u, :r, 'm1')"),
                   {"u": uid, "r": rid})
    return key, rid, uid


def test_backfill_published_sites_and_owner():
    cfg = db_migrate._config()
    command.downgrade(cfg, "0013")
    try:
        with get_sessionmaker()() as db, db.begin():
            key, _, uid = _seed_site(db)
            draft, _, _ = _seed_site(db, published=False)
            unclaimed, _, _ = _seed_site(db, claimed=False)
    finally:
        command.upgrade(cfg, "head")
    with get_sessionmaker()() as db:
        assert db.get(ShopRow, key).name == "결 헤어"
        assert db.scalar(select(ShopMemberRow.user_id).where(ShopMemberRow.site_key == key,
                                                             ShopMemberRow.role == "owner")) == uid
        assert db.get(ShopRow, draft) is None  # 공개 안 한 초안은 가게가 아니다
        assert db.get(ShopRow, unclaimed) is not None
        assert db.scalar(select(ShopMemberRow.user_id).where(ShopMemberRow.site_key == unclaimed)) is None


def test_ensure_is_idempotent():
    with get_sessionmaker()() as db, db.begin():
        key, rid, uid = _seed_site(db, published=False)
    shops.ensure(key, "결 헤어", rid)
    shops.ensure(key, "결 헤어 2호", rid)
    shops.ensure(key, "", rid)  # 이름이 비어도 있던 이름은 남는다
    with get_sessionmaker()() as db:
        assert db.get(ShopRow, key).name == "결 헤어 2호"
        owners = db.scalars(select(ShopMemberRow.user_id).where(ShopMemberRow.site_key == key)).all()
        assert owners == [uid]


def _shop(db):
    key = f"k_{uuid.uuid4().hex[:8]}"
    db.add(ShopRow(site_key=key))
    db.flush()
    return key


def test_amount_checks():
    with pytest.raises(IntegrityError):  # total != subtotal - discount
        with get_sessionmaker()() as db, db.begin():
            db.add(OrderRow(site_key=_shop(db), channel="onsite", subtotal=30000, discount=5000, total=30000))
    with pytest.raises(IntegrityError):  # 손님 주문 결제인데 주문이 없음
        with get_sessionmaker()() as db, db.begin():
            db.add(PaymentRow(site_key=_shop(db), kind="order", provider="manual", amount=1000))


def test_daily_view_net_new_and_returning():
    kst = datetime.timezone(datetime.timedelta(hours=9))
    day1 = datetime.datetime(2026, 9, 1, 23, 30, tzinfo=kst)  # UTC로는 전날이지만 한국 날짜 9/1
    day2 = datetime.datetime(2026, 9, 20, 11, 0, tzinfo=kst)
    with get_sessionmaker()() as db, db.begin():
        key = _shop(db)
        cid = db.execute(text("INSERT INTO customers (site_key, phone) VALUES (:k, '01012345678') RETURNING id"),
                         {"k": key}).scalar()
        o1 = OrderRow(site_key=key, customer_id=cid, channel="online", status="completed",
                      subtotal=50000, total=50000, served_at=day1)
        o2 = OrderRow(site_key=key, customer_id=cid, channel="onsite", status="completed",
                      subtotal=20000, total=20000, served_at=day2)
        o3 = OrderRow(site_key=key, channel="onsite", status="canceled", subtotal=9000, total=9000, served_at=day2)
        db.add_all([o1, o2, o3])
        db.flush()
        p = PaymentRow(site_key=key, order_id=o1.id, kind="order", provider="portone",
                       provider_payment_id=f"pay_{uuid.uuid4().hex}", amount=10000, status="paid")
        db.add(p)
        db.flush()
        db.execute(text("INSERT INTO refunds (payment_id, site_key, amount) VALUES (:p, :k, 3000)"),
                   {"p": p.id, "k": key})
    with get_sessionmaker()() as db:
        rows = db.execute(text("SELECT day, orders, gross, refunds, net, new_customers, returning_customers "
                               "FROM v_shop_daily WHERE site_key = :k ORDER BY day"), {"k": key}).all()
    assert [tuple(r) for r in rows] == [
        (datetime.date(2026, 9, 1), 1, 50000, 3000, 47000, 1, 0),
        (datetime.date(2026, 9, 20), 1, 20000, 0, 20000, 0, 1),  # 취소 주문은 빠진다
    ]
