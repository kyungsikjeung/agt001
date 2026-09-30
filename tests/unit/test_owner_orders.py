"""사장님 주문 목록·환불·완료·다시 확인 (PAY_WAVE3_CONTRACT §6 테스트 6 사장님 쪽)."""
import datetime
import secrets

import httpx
from sqlalchemy import select, update

from app import store
from app.db.models import OrderRow, PaymentRow, SessionRow, ShopSettingsRow, UserRoomRow, UserRow
from app.db.session import get_sessionmaker
from app.services import auth as auth_svc
from app.services import orders, payments
from app.services.slots import KST

ORIGIN = {"Origin": "http://testserver"}
MENU = ["아메리카노", "카페라떼"]
PRICES = {"아메리카노": "4,500원", "카페라떼": "5,000원"}


def _site(client):
    """주문 받는 가게 + 사장님 계정. (room_key, uid)를 돌려준다."""
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    uid = f"u-{secrets.token_hex(4)}"
    prd = {"slots": {"shop_name": {"value": "우리 가게", "status": "filled"},
                     "offerings": {"value": list(MENU), "status": "filled"}},
           "price_pairs": dict(PRICES), "published": "v1"}
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(SessionRow).where(SessionRow.requirement_id == key).values(prd=prd))
        db.add(ShopSettingsRow(site_key=key, phone_verify=False, order_on=True))
        db.add(UserRow(id=uid, nickname="사장님"))
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRoomRow(user_id=uid, room_id=room_id, member_id="owner"))
    return key, uid


def _login(client, uid):
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(uid))


def _paid_transport(total):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={"id": "cancel_1"})
        return httpx.Response(200, json={"status": "PAID", "amount": {"total": total}, "currency": "KRW"})
    return httpx.MockTransport(handler)


def _today():
    return datetime.datetime.now(KST).date().isoformat()


def _order_id(key):
    with get_sessionmaker()() as db:
        return db.scalar(select(OrderRow.id).where(OrderRow.site_key == key))


def _pay_total(pay_id):
    with get_sessionmaker()() as db:
        return db.scalar(select(PaymentRow.amount).where(PaymentRow.provider_payment_id == pay_id))


def test_owner_lists_own_orders(client):
    key, uid = _site(client)
    pay_id = orders.create(key, [("아메리카노", 2)], "김손님", "010-1234-5678")
    assert pay_id.startswith("ord_")
    _login(client, uid)
    got = client.get(f"/api/owner/shops/{key}/orders", params={"date": _today()}).json()
    assert len(got["orders"]) == 1
    one = got["orders"][0]
    assert one["items"] == [{"name": "아메리카노", "qty": 2, "amount": 9000}]
    assert one["total"] == 9000 and one["status"] == "open"
    assert one["phone"] == "01012345678"  # 사장님께는 전화가 보인다
    # 날짜를 비우면 오늘(KST) 기본값
    assert len(client.get(f"/api/owner/shops/{key}/orders").json()["orders"]) == 1


def test_cross_shop_orders_404(client, monkeypatch):
    key_a, uid_a = _site(client)
    key_b, _uid_b = _site(client)
    pay_b = orders.create(key_b, [("아메리카노", 1)], "이손님", "010-9999-8888")
    total_b = _pay_total(pay_b)
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(total_b))
    assert payments.complete(pay_b) == "paid"
    order_b = _order_id(key_b)
    _login(client, uid_a)  # 가게 A 사장님
    assert client.get(f"/api/owner/shops/{key_b}/orders").status_code == 404
    assert client.post(f"/api/owner/shops/{key_b}/orders/{order_b}/refund",
                       json={"amount": None, "reason": "남의 가게"}, headers=ORIGIN).status_code == 404
    # 존재하지 않는 site_key여도 사이트키 경로가 다르면 404
    assert client.post(f"/api/owner/shops/{key_a}/orders/{order_b}/refund",
                       json={"amount": None, "reason": "남의 가게"}, headers=ORIGIN).status_code == 404
    assert client.post(f"/api/owner/shops/{key_a}/orders/{order_b}/complete",
                       headers=ORIGIN).status_code == 404
    assert client.post(f"/api/owner/shops/{key_a}/orders/{order_b}/recheck",
                       headers=ORIGIN).status_code == 404


def test_refund_full_then_list_shows_canceled(client, monkeypatch):
    key, uid = _site(client)
    pay_id = orders.create(key, [("아메리카노", 2)], "김손님", "010-1234-5678")
    total = _pay_total(pay_id)
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(total))
    assert payments.complete(pay_id) == "paid"
    _login(client, uid)
    order_id = _order_id(key)
    r = client.post(f"/api/owner/shops/{key}/orders/{order_id}/refund",
                    json={"amount": None, "reason": "품절"}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["remaining"] == 0 and r.json()["status"] == "canceled"
    got = client.get(f"/api/owner/shops/{key}/orders", params={"date": _today()}).json()
    assert got["orders"][0]["status"] == "canceled"


def test_complete_paid_ok_open_400(client, monkeypatch):
    key, uid = _site(client)
    pay_id = orders.create(key, [("아메리카노", 1)], "김손님", "010-1234-5678")
    _login(client, uid)
    order_id = _order_id(key)
    # 아직 결제 전(open)은 400
    r = client.post(f"/api/owner/shops/{key}/orders/{order_id}/complete", headers=ORIGIN)
    assert r.status_code == 400
    total = _pay_total(pay_id)
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(total))
    assert payments.complete(pay_id) == "paid"
    r = client.post(f"/api/owner/shops/{key}/orders/{order_id}/complete", headers=ORIGIN)
    assert r.status_code == 200 and r.json() == {"id": order_id, "status": "completed"}


def test_recheck_calls_complete(client, monkeypatch):
    key, uid = _site(client)
    pay_id = orders.create(key, [("아메리카노", 1)], "김손님", "010-1234-5678")
    _login(client, uid)
    order_id = _order_id(key)
    calls = []
    monkeypatch.setattr(payments, "complete", lambda pid: calls.append(pid) or "paid")
    r = client.post(f"/api/owner/shops/{key}/orders/{order_id}/recheck", headers=ORIGIN)
    assert r.status_code == 200 and r.json() == {"result": "paid"}
    assert calls == [pay_id]
