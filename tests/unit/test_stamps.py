"""스탬프·쿠폰 코어 (STAMP_WAVE4_CONTRACT §5 테스트 1~6)."""
import datetime
import threading
import uuid

import pytest
from sqlalchemy import func, select

from app.db.models import CouponRow, OrderItemRow, OrderRow, PaymentRow, StampEventRow
from app.db.session import get_sessionmaker
from app.services import stamps
from app.services.customers import touch

PHONE_A = "010-1111-2222"
PHONE_B = "010-3333-4444"


def _key() -> str:
    return "st" + uuid.uuid4().hex[:10]


def _setup(client, **fields) -> str:
    key = _key()
    params = {"active": True, "goal": 10, "per": "order"}
    params.update(fields)
    stamps.set_rule("tester", key, **params)
    return key


def _customer(key: str, phone: str) -> int:
    with get_sessionmaker()() as db, db.begin():
        return touch(db, key, phone, "손님")


def _order(key: str, cid: int, lines: list, pay_status: str = "ready") -> int:
    sub = sum(p * q for _, p, q in lines)
    with get_sessionmaker()() as db, db.begin():
        o = OrderRow(site_key=key, customer_id=cid, channel="online", status="open",
                     subtotal=sub, discount=0, total=sub)
        db.add(o)
        db.flush()
        for name, price, qty in lines:
            db.add(OrderItemRow(order_id=o.id, site_key=key, name=name,
                                unit_price=price, qty=qty, amount=price * qty))
        db.add(PaymentRow(site_key=key, order_id=o.id, kind="order", provider="portone",
                          provider_payment_id="ord_" + uuid.uuid4().hex, amount=sub,
                          status=pay_status))
        return o.id


def _balance(key: str, cid: int) -> int:
    with get_sessionmaker()() as db:
        return stamps.balance(db, key, cid)


def _earn(oid: int) -> list:
    with get_sessionmaker()() as db, db.begin():
        return stamps.earn(db, oid)


# §5 테스트 1: earn은 한 번만, per=item은 수량 합, 규칙 꺼지면 0
def test_earn_twice_counts_once(client):
    key = _setup(client)
    cid = _customer(key, PHONE_A)
    oid = _order(key, cid, [("아메리카노", 4500, 1)])
    assert _earn(oid) == []
    assert _earn(oid) == []
    assert _balance(key, cid) == 1


def test_earn_per_item_sums_qty(client):
    key = _setup(client, per="item")
    cid = _customer(key, PHONE_A)
    oid = _order(key, cid, [("아메리카노", 4500, 2), ("카페라떼", 5000, 3)])
    _earn(oid)
    assert _balance(key, cid) == 5


def test_earn_rule_off_gives_nothing(client):
    key = _setup(client)
    cid = _customer(key, PHONE_A)
    stamps.set_rule("tester", key, active=False)
    oid = _order(key, cid, [("아메리카노", 4500, 1)])
    assert _earn(oid) == []
    assert _balance(key, cid) == 0


# §5 테스트 2: 목표 10에 도장 25개 → 쿠폰 2장·남은 도장 5
def test_manual_25_gives_two_coupons(client):
    key = _setup(client)
    with get_sessionmaker()() as db, db.begin():
        out1 = stamps.manual(db, key, PHONE_A, 10, "owner1")
        out2 = stamps.manual(db, key, PHONE_A, 10, "owner1")
        out3 = stamps.manual(db, key, PHONE_A, 5, "owner1")
    assert (out1["issued"], out2["issued"], out3["issued"]) == (1, 1, 0)
    cid = out1["customer_id"]
    assert out3["balance"] == 5
    with get_sessionmaker()() as db:
        assert len(stamps.usable(db, key, cid)) == 2
    with pytest.raises(ValueError):
        with get_sessionmaker()() as db, db.begin():
            stamps.manual(db, key, PHONE_A, 11, "owner1")


# §5 테스트 3: revoke는 한 번만, 부분 환불은 그대로, 쓴 쿠폰 되돌림
def test_revoke_twice_counts_once(client):
    key = _setup(client)
    cid = _customer(key, PHONE_A)
    oid = _order(key, cid, [("아메리카노", 4500, 1)])
    _earn(oid)
    with get_sessionmaker()() as db, db.begin():
        stamps.revoke(db, oid)
    assert _balance(key, cid) == 0
    with get_sessionmaker()() as db, db.begin():
        stamps.revoke(db, oid)
    assert _balance(key, cid) == 0
    with get_sessionmaker()() as db:
        n = db.scalar(select(func.count()).select_from(StampEventRow).where(
            StampEventRow.order_id == oid, StampEventRow.reason == "refund"))
        assert n == 1


def test_partial_refund_keeps_stamps_and_used_coupon_returns(client):
    key = _setup(client)
    cid = _customer(key, PHONE_A)
    oid = _order(key, cid, [("아메리카노", 4500, 2)])
    _earn(oid)
    # 부분 환불은 revoke를 부르지 않음 → 그대로
    assert _balance(key, cid) == 1
    with get_sessionmaker()() as db, db.begin():
        coid = stamps.issue(db, key, cid, source="stamp")
        stamps.hold(db, oid, coid)
        stamps.settle_held(db, oid)
    with get_sessionmaker()() as db:
        assert db.get(CouponRow, coid).status == "used"
    with get_sessionmaker()() as db, db.begin():
        stamps.revoke(db, oid)
    with get_sessionmaker()() as db:
        assert db.get(CouponRow, coid).status == "issued"
    assert _balance(key, cid) == 0


# §5 테스트 4: redeem
def test_redeem_once_then_rejected(client):
    key = _setup(client)
    cid = _customer(key, PHONE_A)
    with get_sessionmaker()() as db, db.begin():
        coid = stamps.issue(db, key, cid, source="stamp")
        code = db.get(CouponRow, coid).code
    with get_sessionmaker()() as db, db.begin():
        out = stamps.redeem(db, key, code, "staff1")
    assert out["title"] == "음료 1잔 무료" and out["phone_last4"] == "2222"
    with get_sessionmaker()() as db, db.begin():
        with pytest.raises(ValueError, match="이미 쓴"):
            stamps.redeem(db, key, code, "staff1")


def test_redeem_other_shop_lookup_and_bad_code(client):
    key = _setup(client)
    other = _setup(client)
    cid = _customer(key, PHONE_A)
    with get_sessionmaker()() as db, db.begin():
        coid = stamps.issue(db, key, cid, source="stamp")
        code = db.get(CouponRow, coid).code
    with get_sessionmaker()() as db, db.begin():
        with pytest.raises(LookupError):
            stamps.redeem(db, other, code, "staff1")
        with pytest.raises(LookupError):
            stamps.redeem(db, key, "000000000000", "staff1")
        with pytest.raises(ValueError):
            stamps.redeem(db, key, "123", "staff1")
        with pytest.raises(ValueError):
            stamps.redeem(db, key, "abcd efgh ijkl", "staff1")


def test_redeem_expired_rejected(client):
    key = _setup(client)
    cid = _customer(key, PHONE_A)
    with get_sessionmaker()() as db, db.begin():
        coid = stamps.issue(db, key, cid, source="stamp")
        c = db.get(CouponRow, coid)
        c.expires_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        code = c.code
    with get_sessionmaker()() as db, db.begin():
        with pytest.raises(ValueError, match="기간이 지난"):
            stamps.redeem(db, key, code, "staff1")


def test_redeem_concurrent_only_once(client):
    """두 스레드가 동시에 써도 한 번만 성공."""
    key = _setup(client)
    cid = _customer(key, PHONE_A)
    with get_sessionmaker()() as db, db.begin():
        coid = stamps.issue(db, key, cid, source="stamp")
        code = db.get(CouponRow, coid).code
    barrier = threading.Barrier(2)
    results = [None, None]

    def _try(i):
        try:
            with get_sessionmaker()() as db, db.begin():
                barrier.wait(timeout=15)
                out = stamps.redeem(db, key, code, f"staff{i}")
            results[i] = ("ok", out)
        except Exception as e:  # noqa: BLE001 — 성공·실패만 센다
            results[i] = ("err", e)

    ts = [threading.Thread(target=_try, args=(i,)) for i in (0, 1)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=30)
    oks = [r for r in results if r[0] == "ok"]
    errs = [r for r in results if r[0] == "err"]
    assert len(oks) == 1 and len(errs) == 1
    assert isinstance(errs[0][1], ValueError)


# §5 테스트 5: discount 경계
def test_discount_free_picks_most_expensive(client):
    items = [{"unit_price": 5000, "qty": 1, "amount": 5000},
             {"unit_price": 3000, "qty": 2, "amount": 6000}]
    assert stamps.discount({"kind": "free", "value": 0}, items, 11000) == 5000
    assert stamps.discount({"kind": "free", "value": 4000}, items, 11000) == 4000
    assert stamps.discount({"kind": "free", "value": 0}, [], 11000) == 0


def test_discount_amount_percent_bounds(client):
    assert stamps.discount({"kind": "amount", "value": 3000}, [], 10000) == 3000
    assert stamps.discount({"kind": "amount", "value": 20000}, [], 10000) == 10000
    assert stamps.discount({"kind": "percent", "value": 10}, [], 10001) == 1000
    assert stamps.discount({"kind": "percent", "value": 0}, [], 10000) == 0
    assert stamps.discount({"kind": "percent", "value": 101}, [], 10000) == 0
    assert stamps.discount({"kind": "unknown", "value": 5}, [], 10000) == 0
    assert stamps.discount({"kind": "amount", "value": -5}, [], 10000) == 0
    assert stamps.discount({"kind": "amount", "value": 100}, [], 0) == 0
    assert stamps.discount({"kind": "amount", "value": 100}, [], -50) == 0


# §5 테스트 6: hold
def test_hold_change_remove_restores_amounts(client):
    key = _setup(client)
    cid = _customer(key, PHONE_A)
    oid = _order(key, cid, [("아메리카노", 5000, 1), ("카페라떼", 3000, 1)])  # 합계 8000
    with get_sessionmaker()() as db, db.begin():
        amt_id = stamps.issue(db, key, cid, source="owner", kind="amount", value=1000,
                              title="천원 할인")
        pct_id = stamps.issue(db, key, cid, source="owner", kind="percent", value=10,
                              title="십퍼센트")
    with get_sessionmaker()() as db, db.begin():
        out = stamps.hold(db, oid, amt_id)
    assert out == {"subtotal": 8000, "discount": 1000, "total": 7000}
    with get_sessionmaker()() as db, db.begin():
        out = stamps.hold(db, oid, pct_id)  # 바꾸기
    assert out == {"subtotal": 8000, "discount": 800, "total": 7200}
    with get_sessionmaker()() as db:
        assert db.get(CouponRow, amt_id).status == "issued"
    with get_sessionmaker()() as db, db.begin():
        out = stamps.hold(db, oid, None)  # 빼기
    assert out == {"subtotal": 8000, "discount": 0, "total": 8000}
    with get_sessionmaker()() as db:
        order = db.get(OrderRow, oid)
        pay = db.scalar(select(PaymentRow).where(PaymentRow.order_id == oid))
        assert (order.discount, order.total, pay.amount) == (0, 8000, 8000)
        assert db.get(CouponRow, pct_id).status == "issued"


def test_hold_other_customer_coupon_rejected(client):
    key = _setup(client)
    cid_a = _customer(key, PHONE_A)
    cid_b = _customer(key, PHONE_B)
    oid = _order(key, cid_a, [("아메리카노", 5000, 1)])
    with get_sessionmaker()() as db, db.begin():
        other_id = stamps.issue(db, key, cid_b, source="owner")
    with get_sessionmaker()() as db, db.begin():
        with pytest.raises(ValueError):
            stamps.hold(db, oid, other_id)


def test_hold_not_ready_rejected(client):
    key = _setup(client)
    cid = _customer(key, PHONE_A)
    oid = _order(key, cid, [("아메리카노", 5000, 1)], pay_status="paid")
    with get_sessionmaker()() as db, db.begin():
        coid = stamps.issue(db, key, cid, source="owner")
        with pytest.raises(ValueError):
            stamps.hold(db, oid, coid)


def test_held_coupon_redeem_rejected_then_usable_after_15min(client):
    key = _setup(client)
    cid = _customer(key, PHONE_A)
    oid = _order(key, cid, [("아메리카노", 5000, 1)])
    with get_sessionmaker()() as db, db.begin():
        coid = stamps.issue(db, key, cid, source="owner", kind="amount", value=1000,
                            title="천원 할인")
        code = db.get(CouponRow, coid).code
        stamps.hold(db, oid, coid)
    with get_sessionmaker()() as db, db.begin():
        with pytest.raises(ValueError, match="결제 대기 중"):
            stamps.redeem(db, key, code, "staff1")
    with get_sessionmaker()() as db, db.begin():
        c = db.get(CouponRow, coid)
        c.held_until = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)
    with get_sessionmaker()() as db:
        assert [c["id"] for c in stamps.usable(db, key, cid)] == [coid]
    with get_sessionmaker()() as db, db.begin():
        out = stamps.redeem(db, key, code, "staff1")
    assert out["phone_last4"] == "2222"


def test_hold_rejected_after_payment_page_expired(client):
    """결제 페이지가 만료된(15분 지난) 주문에는 쿠폰을 새로 잡지 않는다. 잡은 쿠폰은 그보다 긴 60분 동안 묶인다."""
    key = _setup(client)
    cid = _customer(key, PHONE_A)
    oid = _order(key, cid, [("아메리카노", 5000, 1)])
    with get_sessionmaker()() as db, db.begin():
        pay = db.scalar(select(PaymentRow).where(PaymentRow.order_id == oid))
        pay.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=16)
    with get_sessionmaker()() as db, db.begin():
        coid = stamps.issue(db, key, cid, source="owner")
        with pytest.raises(ValueError, match="주문 시간이 지났어요"):
            stamps.hold(db, oid, coid)
    assert stamps.HOLD_MINUTES > 15
