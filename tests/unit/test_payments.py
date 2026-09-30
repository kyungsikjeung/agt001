"""결제 코어 (PAY_WAVE3_CONTRACT §6 테스트 4·5·6). 실제 포트원은 부르지 않는다."""
import base64
import hashlib
import hmac
import json
import time

import httpx
import pytest
from sqlalchemy import select, update

from app import store
from app.config import settings
from app.db.models import OrderRow, PaymentRow, SessionRow, ShopSettingsRow
from app.db.session import get_sessionmaker
from app.services import orders, payments

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
    return room_id, key


def _order(client, qty=2, item="아메리카노"):
    _, key = _site(client)
    pay_id = orders.create(key, [(item, qty)], "김손님", "010-1234-5678")
    with get_sessionmaker()() as db:
        total = db.scalar(select(PaymentRow.amount).where(PaymentRow.provider_payment_id == pay_id))
    return key, pay_id, total


def _paid_transport(total):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={"id": "cancel_1"})
        return httpx.Response(200, json={"status": "PAID", "amount": {"total": total}, "currency": "KRW"})
    return httpx.MockTransport(handler)


def test_ready_needs_all_three(client, monkeypatch):
    from app.services import keystore
    monkeypatch.setattr(settings, "portone_store_id", "")
    monkeypatch.setattr(settings, "portone_channel_key", "")
    monkeypatch.setattr(settings, "portone_api_secret", "")
    keystore.invalidate()
    assert payments.ready() is False
    monkeypatch.setattr(settings, "portone_store_id", "store-test")
    monkeypatch.setattr(settings, "portone_channel_key", "channel-test")
    monkeypatch.setattr(settings, "portone_api_secret", "secret-test")
    keystore.invalidate()
    assert payments.ready() is True


# §6 테스트 4: complete
def test_complete_amount_mismatch_failed(client, monkeypatch):
    key, pay_id, _total = _order(client)
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(1))  # 다른 금액
    assert payments.complete(pay_id) == "failed"
    with get_sessionmaker()() as db:
        pay = db.scalar(select(PaymentRow).where(PaymentRow.provider_payment_id == pay_id))
        assert pay.status == "failed" and pay.raw["status"] == "PAID"


def test_complete_paid_then_already_once_notify(client, monkeypatch):
    from app.services import notify
    key, pay_id, total = _order(client)
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(total))
    calls = []
    monkeypatch.setattr(notify, "owner_kakao", lambda room_id, text: calls.append((room_id, text)))
    assert payments.complete(pay_id) == "paid"
    assert payments.complete(pay_id) == "already"  # 두 번째는 포트원을 부르지 않음
    assert len(calls) == 1 and "테스트 결제" in calls[0][1]
    with get_sessionmaker()() as db:
        pay = db.scalar(select(PaymentRow).where(PaymentRow.provider_payment_id == pay_id))
        order = db.get(OrderRow, pay.order_id)
        assert pay.status == "paid" and order.status == "paid"


def test_complete_pending_when_portone_not_ready(client, monkeypatch):
    _key, pay_id, _total = _order(client)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "READY", "amount": {"total": 9000}, "currency": "KRW"})

    monkeypatch.setattr(payments, "_TRANSPORT", httpx.MockTransport(handler))
    assert payments.complete(pay_id) == "pending"
    with get_sessionmaker()() as db:
        assert db.scalar(select(PaymentRow.status).where(PaymentRow.provider_payment_id == pay_id)) == "ready"


def test_complete_unknown_pay_id(client, monkeypatch):
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(100))
    assert payments.complete("ord_nope") == "unknown"


# §6 테스트 5: 웹훅 서명 + 같은 웹훅 두 번 와도 paid 한 번
def _webhook_setup(monkeypatch):
    from app.services import keystore
    raw = b"test-webhook-secret-0123456789ab"
    monkeypatch.setattr(settings, "portone_webhook_secret", "whsec_" + base64.b64encode(raw).decode())
    keystore.invalidate()
    return raw


def _sign(raw: bytes, wid: str, ts: str, body: bytes) -> dict:
    msg = f"{wid}.{ts}.{body.decode()}".encode()
    digest = base64.b64encode(hmac.new(raw, msg, hashlib.sha256).digest()).decode()
    return {"webhook-id": wid, "webhook-timestamp": ts, "webhook-signature": f"v1,{digest}"}


def test_verify_webhook_bad_signature(client, monkeypatch):
    raw = _webhook_setup(monkeypatch)
    body = json.dumps({"data": {"paymentId": "ord_x"}}).encode()
    wid, ts = "msg_1", str(int(time.time()))
    good = _sign(raw, wid, ts, body)
    assert payments.verify_webhook(good, body)["data"]["paymentId"] == "ord_x"
    bad = dict(good, **{"webhook-signature": "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="})
    with pytest.raises(ValueError):
        payments.verify_webhook(bad, body)
    with pytest.raises(ValueError):  # 5분 지난 시각
        payments.verify_webhook(_sign(raw, wid, str(int(time.time()) - 600), body), body)
    v2 = dict(good, **{"webhook-signature": good["webhook-signature"].replace("v1,", "v2,")})
    with pytest.raises(ValueError):  # v1만 받는다
        payments.verify_webhook(v2, body)


def test_verify_webhook_rejects_empty_secret(client, monkeypatch):
    """비밀값이 없을 때 빈 열쇠로 만든 서명을 받으면 누구나 웹훅을 위조한다."""
    from app.services import keystore
    monkeypatch.setattr(settings, "portone_webhook_secret", None)
    keystore.invalidate()
    body = json.dumps({"data": {"paymentId": "ord_x"}}).encode()
    wid, ts = "msg_1", str(int(time.time()))
    with pytest.raises(ValueError):
        payments.verify_webhook(_sign(b"", wid, ts, body), body)


def test_webhook_twice_paid_once(client, monkeypatch):
    from app.services import notify
    raw = _webhook_setup(monkeypatch)
    _, pay_id, total = _order(client)
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(total))
    calls = []
    monkeypatch.setattr(notify, "owner_kakao", lambda room_id, text: calls.append(text))
    body = json.dumps({"data": {"paymentId": pay_id}}).encode()
    wid, ts = "msg_2", str(int(time.time()))
    headers = _sign(raw, wid, ts, body)
    assert payments.verify_webhook(headers, body)["data"]["paymentId"] == pay_id
    assert payments.complete(pay_id) == "paid"
    # 같은 웹훅이 다시 와도
    assert payments.verify_webhook(headers, body)["data"]["paymentId"] == pay_id
    assert payments.complete(pay_id) == "already"
    assert len(calls) == 1


# §6 테스트 6: refund
def _order_id(key):
    with get_sessionmaker()() as db:
        return db.scalar(select(OrderRow.id).where(OrderRow.site_key == key))


def test_refund_partial_then_full(client, monkeypatch):
    key, pay_id, total = _order(client)  # 9000원
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(total))
    assert payments.complete(pay_id) == "paid"
    order_id = _order_id(key)
    out = payments.refund(key, order_id, 3000, "맛이 이상", "owner1")
    assert out == {"order_id": order_id, "payment_id": out["payment_id"],
                   "refunded": 3000, "remaining": total - 3000, "status": "paid"}
    out = payments.refund(key, order_id, None, "나머지 취소", "owner1")  # 남은 전액
    assert out["remaining"] == 0 and out["status"] == "canceled"
    with pytest.raises(ValueError):  # 다 환불됐는데 또 하면 거절
        payments.refund(key, order_id, 100, "또", "owner1")


def test_refund_over_remaining_rejected(client, monkeypatch):
    key, pay_id, total = _order(client)
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(total))
    assert payments.complete(pay_id) == "paid"
    with pytest.raises(ValueError):
        payments.refund(key, _order_id(key), total + 1, "너무 큼", "owner1")


def test_shop_a_cannot_refund_shop_b(client, monkeypatch):
    _, key_a = _site(client)
    _, key_b = _site(client)
    pay_b = orders.create(key_b, [("아메리카노", 1)], "이손님", "010-9999-8888")
    with get_sessionmaker()() as db:
        total_b = db.scalar(select(PaymentRow.amount).where(PaymentRow.provider_payment_id == pay_b))
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(total_b))
    assert payments.complete(pay_b) == "paid"
    order_b = _order_id(key_b)
    with pytest.raises(LookupError):
        payments.refund(key_a, order_b, 1000, "남의 가게", "ownerA")
    with pytest.raises(LookupError):
        payments.refund(key_b, 999999999, 1000, "없는 주문", "ownerB")
