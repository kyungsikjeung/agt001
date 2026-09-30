"""스탬프 적립·쿠폰 발급·사용·할인 (STAMP_WAVE4_CONTRACT §3.1).

도장 수는 stamp_events.delta 합계로만 본다. 따로 저장하지 않는다.
db를 받는 함수는 flush까지만 하고 커밋하지 않는다. 부른 쪽 트랜잭션 안에서 돈다.
"""
import datetime
import logging
import re
import secrets

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.models import CouponRow, CustomerRow, OrderItemRow, OrderRow, PaymentRow, StampEventRow, StampRuleRow
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)

CODE_LEN = 12
# 잡아 둔 쿠폰은 결제 페이지 만료(orders.READY_MINUTES=15분)보다 길게 둔다: 14분에 연 결제창이 16분에 끝나도
# 그 사이 쿠폰이 풀려 매장·다른 주문에서 한 번 더 쓰이지 않게. 새 결제창은 15분 뒤 열리지 않는다.
HOLD_MINUTES = 60

REASONS = ("order", "refund", "manual", "reward")
KINDS = ("free", "amount", "percent")
SOURCES = ("stamp", "owner")
_RULE_FIELDS = ("active", "goal", "per", "reward_title", "reward_kind", "reward_value", "coupon_days")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _aware(dt: datetime.datetime) -> datetime.datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _rule_dict(row: StampRuleRow) -> dict:
    return {"site_key": row.site_key, "active": row.active, "goal": row.goal, "per": row.per,
            "reward_title": row.reward_title, "reward_kind": row.reward_kind,
            "reward_value": row.reward_value, "coupon_days": row.coupon_days}


def _coupon_dict(row: CouponRow) -> dict:
    return {"id": row.id, "site_key": row.site_key, "customer_id": row.customer_id,
            "code": row.code, "title": row.title, "kind": row.kind, "value": row.value,
            "status": row.status, "issued_at": row.issued_at, "expires_at": row.expires_at}


def rule(site_key: str) -> dict | None:
    """켜진 규칙만 돌려준다. 없거나 꺼졌으면 None."""
    key = (site_key or "").strip()
    if not key:
        return None
    with get_sessionmaker()() as db:
        row = db.get(StampRuleRow, key)
        if row is None or not row.active:
            return None
        return _rule_dict(row)


def set_rule(user_id: str, site_key: str, **fields) -> dict:
    """규칙 보기·바꾸기. 범위를 벗어나면 사람 말 ValueError."""
    from app.services import shops

    key = (site_key or "").strip()
    if not key:
        raise ValueError("가게를 찾을 수 없어요.")
    for k in fields:
        if k not in _RULE_FIELDS:
            raise ValueError("알 수 없는 규칙 항목이에요.")
    with get_sessionmaker()() as db, db.begin():
        shops.ensure_in(db, key)
        row = db.get(StampRuleRow, key)
        cur = _rule_dict(row) if row is not None else {"active": False, "goal": 10, "per": "order",
                                                       "reward_title": "음료 1잔 무료", "reward_kind": "free",
                                                       "reward_value": 0, "coupon_days": 90}
        vals = _check_rule_fields(fields, cur)
        if row is None:
            row = StampRuleRow(site_key=key)
            db.add(row)
        for k, v in vals.items():
            setattr(row, k, v)
        row.updated_by = (str(user_id or "").strip()[:80] or None)
        row.updated_at = _now()
        db.flush()
        return _rule_dict(row)


def _check_rule_fields(fields: dict, cur: dict) -> dict:
    """바꾸는 값만 검사해 돌려준다."""
    out: dict = {}
    if "active" in fields:
        out["active"] = bool(fields["active"])
    if "goal" in fields:
        v = fields["goal"]
        if isinstance(v, bool) or not isinstance(v, int) or not 2 <= v <= 50:
            raise ValueError("목표 도장 수는 2개부터 50개까지 가능해요.")
        out["goal"] = v
    if "per" in fields:
        if fields["per"] not in ("order", "item"):
            raise ValueError("적립 기준은 order(주문마다) 또는 item(메뉴마다)이에요.")
        out["per"] = fields["per"]
    if "reward_title" in fields:
        t = str(fields["reward_title"] or "").strip()
        if not 1 <= len(t) <= 30:
            raise ValueError("혜택 이름은 1자부터 30자까지 적어 주세요.")
        out["reward_title"] = t
    kind = fields.get("reward_kind", cur.get("reward_kind"))
    if "reward_kind" in fields:
        if kind not in KINDS:
            raise ValueError("혜택 종류는 free, amount, percent 중에 골라 주세요.")
        out["reward_kind"] = kind
    if "reward_value" in fields:
        v = fields["reward_value"]
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError("혜택 값은 0부터 적어 주세요.")
        if kind == "percent" and not 1 <= v <= 100:
            raise ValueError("할인율은 1부터 100까지 적어 주세요.")
        out["reward_value"] = v
    if "coupon_days" in fields:
        v = fields["coupon_days"]
        if isinstance(v, bool) or not isinstance(v, int) or not 7 <= v <= 365:
            raise ValueError("쿠폰 기한은 7일부터 365일까지 가능해요.")
        out["coupon_days"] = v
    return out


def _active_rule_in(db, site_key: str) -> StampRuleRow | None:
    row = db.get(StampRuleRow, site_key)
    if row is None or not row.active:
        return None
    return row


def balance(db, site_key: str, customer_id: int) -> int:
    """delta 합계가 곧 도장 수."""
    return db.scalar(select(func.coalesce(func.sum(StampEventRow.delta), 0)).where(
        StampEventRow.site_key == site_key, StampEventRow.customer_id == customer_id)) or 0


def _is_usable(row: CouponRow, now: datetime.datetime) -> bool:
    """쓸 수 있음 = issued + 기한 안, 또는 held인데 버려진 결제(held_until 지남)."""
    if row.status == "issued":
        return row.expires_at is not None and _aware(row.expires_at) > now
    if row.status == "held":
        return row.held_until is not None and _aware(row.held_until) < now
    return False


def issue(db, site_key: str, customer_id: int, *, source: str,
          title=None, kind=None, value=None) -> int:
    """쿠폰 한 장. 번호는 서버 난수 12자리, 겹치면 다시(최대 5번)."""
    if source not in SOURCES:
        raise ValueError("쿠폰 출처는 stamp 또는 owner예요.")
    r = _active_rule_in(db, site_key)
    t = str(title or "").strip() or (r.reward_title if r is not None else "쿠폰")
    if not 1 <= len(t) <= 30:
        raise ValueError("혜택 이름은 1자부터 30자까지 적어 주세요.")
    k = (str(kind or "").strip() or (r.reward_kind if r is not None else "free"))
    if k not in KINDS:
        raise ValueError("혜택 종류는 free, amount, percent 중에 골라 주세요.")
    v = r.reward_value if (value is None and r is not None) else (value if value is not None else 0)
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise ValueError("혜택 값은 0부터 적어 주세요.")
    if k == "percent" and not 1 <= v <= 100:
        raise ValueError("할인율은 1부터 100까지 적어 주세요.")
    days = r.coupon_days if r is not None else 90
    now = _now()
    for _ in range(5):
        code = f"{secrets.randbelow(10 ** 12):012d}"
        try:
            with db.begin_nested():
                row = CouponRow(site_key=site_key, customer_id=customer_id, code=code,
                                title=t, kind=k, value=v, status="issued",
                                issued_at=now, expires_at=now + datetime.timedelta(days=days),
                                source=source)
                db.add(row)
                db.flush()
                return row.id
        except IntegrityError:
            continue
    raise ValueError("쿠폰 번호가 겹쳤어요. 다시 시도해 주세요.")


def _issue_while_full(db, site_key: str, customer_id: int, source: str) -> list[int]:
    """합계가 목표를 넘으면 같은 트랜잭션에서 쿠폰 발급(넘친 도장은 이월)."""
    ids: list[int] = []
    while True:
        r = _active_rule_in(db, site_key)
        if r is None or balance(db, site_key, customer_id) < r.goal:
            break
        cid = issue(db, site_key, customer_id, source=source)
        db.add(StampEventRow(site_key=site_key, customer_id=customer_id, order_id=None,
                             delta=-r.goal, reason="reward", coupon_id=cid))
        db.flush()
        ids.append(cid)
    return ids


def earn(db, order_id: int) -> list[int]:
    """주문 적립(reason=order, 유일 제약으로 한 번) → 목표 넘으면 발급. 새 쿠폰 id 목록."""
    order = db.get(OrderRow, order_id)
    if order is None:
        raise LookupError("주문을 찾을 수 없어요.")
    r = _active_rule_in(db, order.site_key)
    if r is None or order.customer_id is None:
        return []
    if r.per == "item":
        n = db.scalar(select(func.coalesce(func.sum(OrderItemRow.qty), 0)).where(
            OrderItemRow.order_id == order_id)) or 0
        n = int(n)
    else:
        n = 1
    if n <= 0:
        return []
    try:
        with db.begin_nested():
            db.add(StampEventRow(site_key=order.site_key, customer_id=order.customer_id,
                                 order_id=order_id, delta=n, reason="order"))
            db.flush()
    except IntegrityError:
        return []  # 이미 적립한 주문
    return _issue_while_full(db, order.site_key, order.customer_id, "stamp")


def revoke(db, order_id: int) -> None:
    """전액 환불: 그 주문 적립만큼 reason=refund 음수(한 번). 이 주문 쿠폰은 issued로 되돌림."""
    order = db.get(OrderRow, order_id)
    if order is None:
        raise LookupError("주문을 찾을 수 없어요.")
    got = db.scalar(select(StampEventRow.delta).where(
        StampEventRow.order_id == order_id, StampEventRow.reason == "order"))
    if got is not None and order.customer_id is not None:
        try:
            with db.begin_nested():
                db.add(StampEventRow(site_key=order.site_key, customer_id=order.customer_id,
                                     order_id=order_id, delta=-int(got), reason="refund"))
                db.flush()
        except IntegrityError:
            pass  # 이미 회수한 주문
    held = db.scalars(select(CouponRow).where(
        CouponRow.held_order_id == order_id, CouponRow.status == "held").with_for_update()).all()
    used = db.scalars(select(CouponRow).where(
        CouponRow.used_order_id == order_id, CouponRow.status == "used").with_for_update()).all()
    for c in list(held) + list(used):
        c.status = "issued"
        c.held_order_id = None
        c.held_until = None
        c.used_at = None
        c.used_by = None
        c.used_order_id = None


def manual(db, site_key: str, phone: str, count: int, by: str) -> dict:
    """사장님 수동 적립(현장 결제 손님). 1~10개, 발급 포함."""
    from app.services.customers import normalize_phone, touch

    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10:
        raise ValueError("수동 적립은 1개부터 10개까지 가능해요.")
    digits = normalize_phone(phone)
    if digits is None:
        raise ValueError("전화번호를 확인해 주세요.")
    key = (site_key or "").strip()
    cid = touch(db, key, digits, None)
    if cid is None:
        raise ValueError("전화번호를 확인해 주세요.")
    db.add(StampEventRow(site_key=key, customer_id=cid, order_id=None,
                         delta=count, reason="manual", by_user_id=(str(by or "")[:80] or None)))
    db.flush()
    issued = _issue_while_full(db, key, cid, "stamp")
    return {"balance": balance(db, key, cid), "issued": len(issued), "customer_id": cid}


def usable(db, site_key: str, customer_id: int) -> list[dict]:
    """쓸 수 있는 쿠폰만."""
    now = _now()
    rows = db.scalars(select(CouponRow).where(
        CouponRow.site_key == site_key, CouponRow.customer_id == customer_id,
        CouponRow.status.in_(("issued", "held"))).order_by(CouponRow.id.desc())).all()
    return [_coupon_dict(r) for r in rows if _is_usable(r, now)]


def _coupon_val(coupon, key: str):
    if isinstance(coupon, dict):
        return coupon.get(key)
    return getattr(coupon, key, None)


def discount(coupon: dict, items: list[dict], subtotal: int) -> int:
    """free: 가장 비싼 한 개 단가(value>0이면 상한). amount: min(value, 합계).
    percent: 합계*값//100. 결과는 0~합계."""
    sub = subtotal if isinstance(subtotal, int) and not isinstance(subtotal, bool) else 0
    sub = max(sub, 0)
    if sub == 0:
        return 0
    kind = _coupon_val(coupon, "kind")
    value = _coupon_val(coupon, "value") or 0
    if not isinstance(value, int) or isinstance(value, bool):
        value = 0
    if kind == "free":
        top = 0
        for it in items or []:
            if not isinstance(it, dict):
                continue
            unit = it.get("unit_price")
            if unit is None:
                amt = it.get("amount") or 0
                qty = it.get("qty") or 1
                unit = amt // qty if qty else amt
            if isinstance(unit, int) and not isinstance(unit, bool):
                top = max(top, unit)
        d = max(top, 0)
        if value > 0:
            d = min(d, value)
    elif kind == "amount":
        d = min(max(value, 0), sub)
    elif kind == "percent":
        d = sub * value // 100 if 1 <= value <= 100 else 0
    else:
        d = 0
    return max(0, min(d, sub))


def hold(db, order_id: int, coupon_id: int | None) -> dict:
    """결제 대기 주문에 쿠폰 잡기/바꾸기/빼기(None). orders·payments 금액 다시 계산."""
    order = db.scalar(select(OrderRow).where(OrderRow.id == order_id).with_for_update())
    if order is None:
        raise LookupError("주문을 찾을 수 없어요.")
    pay = db.scalar(select(PaymentRow).where(PaymentRow.order_id == order_id).with_for_update())
    if pay is None:
        raise LookupError("주문을 찾을 수 없어요.")
    if pay.status != "ready":
        raise ValueError("결제 대기 중인 주문에만 쿠폰을 쓸 수 있어요.")
    now = _now()
    from app.services.orders import READY_MINUTES
    if pay.created_at is not None and now - _aware(pay.created_at) > datetime.timedelta(minutes=READY_MINUTES):
        raise ValueError("주문 시간이 지났어요. 가게 사이트에서 다시 주문해 주세요.")
    items = db.scalars(select(OrderItemRow).where(OrderItemRow.order_id == order_id)).all()
    subtotal = sum(r.amount for r in items)
    current = db.scalar(select(CouponRow).where(
        CouponRow.held_order_id == order_id, CouponRow.status == "held").with_for_update())
    disc = 0
    if coupon_id is None:
        if current is not None:
            _release(current)
    else:
        c = db.scalar(select(CouponRow).where(CouponRow.id == coupon_id).with_for_update())
        if c is None:
            raise LookupError("쿠폰을 찾을 수 없어요.")
        if c.site_key != order.site_key or c.customer_id != order.customer_id:
            raise ValueError("이 주문에 쓸 수 있는 쿠폰이 아니에요.")
        if current is not None and current.id == c.id:
            pass  # 같은 쿠폰 계속 잡기
        elif not _is_usable(c, now):
            if c.status == "used":
                raise ValueError("이미 쓴 쿠폰이에요.")
            if c.expires_at is not None and _aware(c.expires_at) <= now:
                raise ValueError("기간이 지난 쿠폰이에요.")
            raise ValueError("다른 주문에 잡혀 있는 쿠폰이에요.")
        else:
            if current is not None:
                _release(current)
            c.status = "held"
            c.held_order_id = order_id
            c.held_until = now + datetime.timedelta(minutes=HOLD_MINUTES)
        disc = discount(_coupon_dict(c), [{"unit_price": r.unit_price, "qty": r.qty, "amount": r.amount}
                                          for r in items], subtotal)
    total = max(subtotal - disc, 0)
    order.discount = disc
    order.total = total
    pay.amount = total
    return {"subtotal": subtotal, "discount": disc, "total": total}


def _release(row: CouponRow) -> None:
    """잡아 둔 쿠폰 풀기."""
    row.status = "issued"
    row.held_order_id = None
    row.held_until = None


def settle_held(db, order_id: int) -> None:
    """paid 순간: 이 주문이 잡은 쿠폰 → used(used_by='order')."""
    rows = db.scalars(select(CouponRow).where(
        CouponRow.held_order_id == order_id, CouponRow.status == "held").with_for_update()).all()
    now = _now()
    order = db.get(OrderRow, order_id)
    if not rows and order is not None and order.discount:
        # 할인은 받았는데 잡은 쿠폰이 없다(잡은 시간이 지나 풀린 뒤 결제가 끝남). 돈은 이미 오갔으니 기록만 남긴다.
        log.warning("쿠폰 없이 할인된 결제 order=%s discount=%s", order_id, order.discount)
    for c in rows:
        c.status = "used"
        c.used_at = now
        c.used_by = "order"
        c.used_order_id = order_id


def redeem(db, site_key: str, code: str, by: str) -> dict:
    """매장 사용. 숫자 12자리가 아니면 ValueError, 다른 가게·없음은 LookupError."""
    digits = re.sub(r"\D", "", code or "")
    if len(digits) != CODE_LEN:
        raise ValueError("쿠폰 번호 12자리를 확인해 주세요.")
    key = (site_key or "").strip()
    c = db.scalar(select(CouponRow).where(
        CouponRow.site_key == key, CouponRow.code == digits).with_for_update())
    if c is None:
        raise LookupError("쿠폰을 찾을 수 없어요.")
    now = _now()
    if c.status == "used":
        raise ValueError("이미 쓴 쿠폰이에요.")
    if c.expires_at is not None and _aware(c.expires_at) <= now:
        raise ValueError("기간이 지난 쿠폰이에요.")
    if c.status == "held" and not _is_usable(c, now):
        raise ValueError("결제 대기 중인 쿠폰이에요.")
    if c.status not in ("issued", "held"):
        raise ValueError("쓸 수 없는 쿠폰이에요.")
    c.status = "used"
    c.held_order_id = None
    c.held_until = None
    c.used_at = now
    c.used_by = (str(by or "").strip()[:80] or None)
    cust = db.get(CustomerRow, c.customer_id)
    phone = cust.phone if cust is not None and cust.phone else ""
    return {"title": c.title, "phone_last4": phone[-4:] if phone else "", "used_at": now}
