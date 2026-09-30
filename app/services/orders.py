"""포장 주문 코어 (PAY_WAVE3_CONTRACT §3.1).

금액은 손님이 보낸 값이 아니라 지금 카드 메뉴 가격에서만 계산한다.
"""
import datetime
import re
import secrets

from sqlalchemy import select

from app.db.models import OrderItemRow, OrderRow, PaymentRow, SessionRow, ShopRow
from app.db.session import get_sessionmaker

MAX_QTY = 20
MAX_LINES = 20
MAX_TOTAL = 500_000
READY_MINUTES = 15


class OrderError(ValueError):
    """손님에게 보여 줄 한 줄 사유."""


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def paused() -> bool:
    """비상 스위치 켜짐 여부. 켜지면 새 주문·결제 시작만 막는다 (WAVE5_CONTRACT §2.1)."""
    from app.config import settings
    return bool(settings.commerce_paused)


def _kst_day(dt: datetime.datetime) -> datetime.date:
    # DB 시각은 timestamptz. naive면 UTC로 본다.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return (dt.astimezone(datetime.timezone(datetime.timedelta(hours=9)))).date()


def _load_card(site_key: str) -> dict | None:
    """site_key(세션 requirement_id)의 카드. 없으면 None."""
    with get_sessionmaker()() as db:
        prd = db.scalar(select(SessionRow.prd).where(SessionRow.requirement_id == site_key))
    return prd if isinstance(prd, dict) else None


def menu_prices(site_key: str) -> dict[str, int]:
    """지금 카드의 메뉴 이름 → 원. 못 읽는 가격은 뺀다."""
    from app.services import card_data
    card = _load_card(site_key)
    if not card:
        return {}
    try:
        catalog = card_data.build(card).get("catalog") or []
    except Exception:
        return {}
    out: dict[str, int] = {}
    for group in catalog:
        for item in (group or {}).get("items") or []:
            name = str((item or {}).get("name") or "").strip()
            price = (item or {}).get("price_won")
            if name and isinstance(price, int) and price and name not in out:
                out[name] = price
    return out


def parse_form(form: dict) -> list[tuple[str, int]]:
    """폼 → [(이름, 수량)]. item_<n>·qty_<n>만 본다. 0·빈 수량 줄은 버린다."""
    found: dict[str, int] = {}
    order: list[str] = []
    for key in list(form or {}):
        m = re.fullmatch(r"item_(\d+)", str(key))
        if not m:
            continue
        n = m.group(1)
        name = str((form.get(key) or "")).strip()[:60]
        qty_raw = form.get(f"qty_{n}", "")
        qty_s = str(qty_raw if qty_raw is not None else "").strip()
        if qty_s == "" or qty_s == "0":
            continue
        try:
            qty = int(qty_s)
        except ValueError:
            raise OrderError("수량은 숫자로 적어 주세요.")
        if qty < 0:
            raise OrderError("수량은 0보다 크게 적어 주세요.")
        if qty > MAX_QTY:
            raise OrderError(f"한 메뉴는 {MAX_QTY}개까지 주문할 수 있어요.")
        if not name:
            raise OrderError("메뉴 이름을 확인해 주세요.")
        if name in found:
            found[name] += qty
            if found[name] > MAX_QTY:
                raise OrderError(f"한 메뉴는 {MAX_QTY}개까지 주문할 수 있어요.")
        else:
            found[name] = qty
            order.append(name)
    lines = [(name, found[name]) for name in order]
    if not lines:
        raise OrderError("주문할 메뉴를 골라 주세요.")
    if len(lines) > MAX_LINES:
        raise OrderError(f"한 번에 {MAX_LINES}가지까지 주문할 수 있어요.")
    return lines


def _published(card: dict | None) -> bool:
    return bool(isinstance(card, dict) and card.get("published"))


def check(site_key: str, lines: list[tuple[str, int]], phone: str) -> tuple[list[tuple[str, int, int]], int]:
    """주문 검사(§1 2번)만: [(이름, 수량, 단가)], 합계. 인증 문자를 보내기 전에도 부른다(헛걸음·문자 비용 막기)."""
    from app.services import shop_settings
    from app.services.customers import normalize_phone

    key = (site_key or "").strip()
    card = _load_card(key)
    if card is None:
        raise OrderError("사이트를 찾을 수 없어요.")
    if not _published(card):
        raise OrderError("지금은 주문을 받지 않아요.")
    if not shop_settings.get(key).get("order_on"):
        raise OrderError("지금은 주문을 받지 않아요.")
    if not lines:
        raise OrderError("주문할 메뉴를 골라 주세요.")
    if len(lines) > MAX_LINES:
        raise OrderError(f"한 번에 {MAX_LINES}가지까지 주문할 수 있어요.")
    if normalize_phone(phone) is None:
        raise OrderError("연락받을 전화번호를 적어 주세요.")
    prices = menu_prices(key)
    total = 0
    checked: list[tuple[str, int, int]] = []
    for raw_name, qty in lines:
        item = str(raw_name or "").strip()
        if not isinstance(qty, int) or isinstance(qty, bool) or not 1 <= qty <= MAX_QTY:
            raise OrderError(f"한 메뉴는 1개부터 {MAX_QTY}개까지 주문할 수 있어요.")
        price = prices.get(item)
        if price is None:
            raise OrderError("주문할 수 없는 메뉴가 있어요. 메뉴에서 다시 골라 주세요.")
        total += price * qty
        checked.append((item, qty, price))
    if not 1 <= total <= MAX_TOTAL:
        raise OrderError("주문 금액은 1원부터 500,000원까지 가능해요.")
    return checked, total


def create(site_key: str, lines: list[tuple[str, int]], name: str | None, phone: str) -> str:
    """검사(check) → 한 트랜잭션으로 §1 5번 → pay_id. 가격은 menu_prices에서만."""
    from app.services import customers, shops

    key = (site_key or "").strip()
    checked, total = check(key, lines, phone)
    clean_name = (str(name or "").strip())[:40]
    pay_id = "ord_" + secrets.token_urlsafe(16)
    with get_sessionmaker()() as db, db.begin():
        shops.ensure_in(db, key)
        cid = customers.touch(db, key, phone, clean_name or None)
        customers.mark_verified(db, key, phone)
        order = OrderRow(site_key=key, customer_id=cid, channel="online", status="open",
                         subtotal=total, discount=0, total=total)
        db.add(order)
        db.flush()
        for item, qty, price in checked:
            db.add(OrderItemRow(order_id=order.id, site_key=key, name=item,
                                unit_price=price, qty=qty, amount=price * qty))
        db.add(PaymentRow(site_key=key, order_id=order.id, kind="order",
                          provider="portone", provider_payment_id=pay_id,
                          amount=total, status="ready"))
    return pay_id


def _shop_name(site_key: str, card: dict | None) -> str:
    slot = ((card or {}).get("slots") or {}).get("shop_name") or {}
    raw = slot.get("value") or ""
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    with get_sessionmaker()() as db:
        name = db.scalar(select(ShopRow.name).where(ShopRow.site_key == site_key))
    return name or ""


def summary(pay_id: str) -> dict | None:
    """결제 페이지용. 전화번호는 넣지 않는다."""
    pid = (pay_id or "").strip()
    if not pid:
        return None
    with get_sessionmaker()() as db:
        pay = db.scalar(select(PaymentRow).where(PaymentRow.provider_payment_id == pid))
        if pay is None:
            return None
        order = db.get(OrderRow, pay.order_id)
        items = db.scalars(select(OrderItemRow).where(OrderItemRow.order_id == pay.order_id)
                           .order_by(OrderItemRow.id)).all() if order is not None else []
        created = pay.created_at
    card = _load_card(pay.site_key)
    expired = False
    if pay.status == "ready" and created is not None:
        if created.tzinfo is None:
            created = created.replace(tzinfo=datetime.timezone.utc)
        expired = (_now() - created) > datetime.timedelta(minutes=READY_MINUTES)
    return {"shop_name": _shop_name(pay.site_key, card),
            "items": [{"name": r.name, "qty": r.qty, "amount": r.amount} for r in items],
            "total": pay.amount,
            "status": pay.status,
            "expired": expired,
            "site_url": f"/site/{pay.site_key}/"}


def owner_list(site_key: str, day: datetime.date) -> list[dict]:
    """그날(KST) 주문. 15분 지난 open은 뺀다. 손님 전화는 사장님께 보인다."""
    from app.db.models import CustomerRow, PaymentRow as PayRow
    key = (site_key or "").strip()
    now = _now()
    with get_sessionmaker()() as db:
        rows = db.scalars(select(OrderRow).where(OrderRow.site_key == key)
                          .order_by(OrderRow.id.desc())).all()
        out = []
        for o in rows:
            created = o.created_at
            if created is None or _kst_day(created) != day:
                continue
            ts = created if created.tzinfo else created.replace(tzinfo=datetime.timezone.utc)
            if o.status == "open" and (now - ts) > datetime.timedelta(minutes=READY_MINUTES):
                continue
            items = db.scalars(select(OrderItemRow).where(OrderItemRow.order_id == o.id)
                               .order_by(OrderItemRow.id)).all()
            pay = db.scalar(select(PayRow).where(PayRow.order_id == o.id))
            cust = db.get(CustomerRow, o.customer_id) if o.customer_id else None
            out.append({"order_id": o.id, "status": o.status,
                        "pay_status": pay.status if pay else "",
                        "items": [{"name": r.name, "qty": r.qty, "amount": r.amount} for r in items],
                        "total": o.total, "phone": cust.phone if cust else "",
                        "name": (cust.name if cust else "") or "",
                        "created_at": o.created_at})
    return out


def mark_completed(site_key: str, order_id: int, by: str) -> dict:
    """가져감 → completed. 결제된 주문만."""
    with get_sessionmaker()() as db, db.begin():
        row = db.scalar(select(OrderRow).where(OrderRow.id == order_id).with_for_update())
        if row is None or row.site_key != site_key:
            raise LookupError("주문을 찾을 수 없어요.")
        if row.status != "paid":
            raise OrderError("결제된 주문만 완료할 수 있어요.")
        row.status = "completed"
        row.served_at = _now()
        row.staff_name = (str(by or "").strip()[:40]) or None
    return {"id": order_id, "status": "completed"}
