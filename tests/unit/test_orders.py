"""주문 코어 (PAY_WAVE3_CONTRACT §6 테스트 2·3)."""
import datetime

import pytest
from sqlalchemy import select, update

from app import store
from app.db.models import OrderRow, PaymentRow, SessionRow, ShopSettingsRow
from app.db.session import get_sessionmaker
from app.services import orders
from app.services.orders import OrderError

MENU = ["아메리카노", "카페라떼"]
PRICES = {"아메리카노": "4,500원", "카페라떼": "5,000원"}


def _site(client, order_on=True):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    prd = {"slots": {"shop_name": {"value": "우리 가게", "status": "filled"},
                     "offerings": {"value": list(MENU), "status": "filled"}},
           "price_pairs": dict(PRICES), "published": "v1"}
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(SessionRow).where(SessionRow.requirement_id == key).values(prd=prd))
        db.add(ShopSettingsRow(site_key=key, phone_verify=False, order_on=order_on))
    return key


def _form(**over):
    form = {"item_0": "아메리카노", "qty_0": "2", "item_1": "카페라떼", "qty_1": "1"}
    form.update(over)
    return form


# §6 테스트 2: parse_form
def test_parse_form_drops_zero_and_empty():
    assert orders.parse_form({"item_0": "아메리카노", "qty_0": "2",
                              "item_1": "카페라떼", "qty_1": "0",
                              "item_2": "라떼", "qty_2": ""}) == [("아메리카노", 2)]


@pytest.mark.parametrize("qty", ["21", "-1", "두개", "1.5"])
def test_parse_form_bad_qty_rejected(qty):
    with pytest.raises(OrderError):
        orders.parse_form({"item_0": "아메리카노", "qty_0": qty})


def test_parse_form_too_many_lines_rejected():
    form = {}
    for i in range(21):
        form[f"item_{i}"] = f"메뉴{i}"
        form[f"qty_{i}"] = "1"
    with pytest.raises(OrderError):
        orders.parse_form(form)


def test_parse_form_empty_rejected():
    with pytest.raises(OrderError):
        orders.parse_form({"item_0": "아메리카노", "qty_0": "0"})


# §6 테스트 3: create
def test_create_ignores_client_price_and_uses_card(client):
    key = _site(client)
    # 폼에 가격을 넣어도 parse_form은 이름·수량만 본다
    lines = orders.parse_form(dict(_form(), price_0="100원", total="9999999"))
    pay_id = orders.create(key, lines, "김손님", "010-1234-5678")
    assert pay_id.startswith("ord_")
    with get_sessionmaker()() as db:
        pay = db.scalar(select(PaymentRow).where(PaymentRow.provider_payment_id == pay_id))
        assert pay.amount == 4500 * 2 + 5000  # 카드 가격으로 합계
        assert pay.status == "ready" and pay.kind == "order" and pay.provider == "portone"
        order = db.get(OrderRow, pay.order_id)
        assert order.channel == "online" and order.status == "open" and order.total == 14000


def test_create_unknown_menu_rejected(client):
    key = _site(client)
    with pytest.raises(OrderError):
        orders.create(key, [("없는메뉴", 1)], "김손님", "010-1234-5678")


def test_create_over_max_total_rejected(client):
    """합계 500,000원 초과는 거절. 5,000원 × 20개 × 20줄 = 2,000,000원."""
    key = _site(client)
    with pytest.raises(OrderError):
        orders.create(key, [("카페라떼", 20)] * 20, "김손님", "010-1234-5678")


def test_create_order_off_rejected(client):
    key = _site(client, order_on=False)
    with pytest.raises(OrderError):
        orders.create(key, [("아메리카노", 1)], "김손님", "010-1234-5678")


def test_create_marks_customer_verified(client):
    from app.db.models import CustomerRow
    key = _site(client)
    orders.create(key, [("아메리카노", 1)], "김손님", "010-1234-5678")
    with get_sessionmaker()() as db:
        cust = db.scalar(select(CustomerRow).where(CustomerRow.site_key == key))
        assert cust is not None and cust.phone_verified_at is not None


def test_summary_and_owner_list_and_complete(client):
    key = _site(client)
    pay_id = orders.create(key, [("아메리카노", 2)], "김손님", "010-1234-5678")
    got = orders.summary(pay_id)
    assert got["total"] == 9000 and got["status"] == "ready" and got["expired"] is False
    assert "010" not in repr(got)  # 전화번호 없음
    assert got["items"] == [{"name": "아메리카노", "qty": 2, "amount": 9000}]
    assert orders.summary("ord_nope") is None
    today = (datetime.datetime.now(datetime.timezone.utc)
             + datetime.timedelta(hours=9)).date()
    listed = orders.owner_list(key, today)
    assert len(listed) == 1 and listed[0]["phone"] == "01012345678"
    assert listed[0]["items"] == [{"name": "아메리카노", "qty": 2, "amount": 9000}]
    with get_sessionmaker()() as db, db.begin():
        order_id = db.scalar(select(OrderRow.id).where(OrderRow.site_key == key))
        db.execute(update(OrderRow).where(OrderRow.id == order_id).values(status="paid"))
    out = orders.mark_completed(key, order_id, "사장님")
    assert out == {"id": order_id, "status": "completed"}
    with pytest.raises(OrderError):
        orders.mark_completed(key, order_id, "사장님")
    with pytest.raises(LookupError):
        orders.mark_completed("other-site", order_id, "사장님")
