"""온라인 결제 운영 신호 (WAVE5_CONTRACT §3.1·§5 5번). 실제 포트원은 부르지 않는다."""
import base64
import hashlib
import hmac
import json
import time

import httpx
import pytest
from sqlalchemy import delete, select, update

from app import store
from app.db.models import FunnelEventRow, PaymentRow, SessionRow, ShopSettingsRow
from app.db.session import get_sessionmaker
from app.services import funnel, orders, payments
from scripts import commerce_signals

MENU = ["아메리카노", "카페라떼"]
PRICES = {"아메리카노": "4,500원", "카페라떼": "5,000원"}


def _site(client):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    prd = {"slots": {"shop_name": {"value": "우리 가게", "status": "filled"},
                     "offerings": {"value": list(MENU), "status": "filled"}},
           "price_pairs": dict(PRICES), "published": "v1"}
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(SessionRow).where(SessionRow.requirement_id == key).values(prd=prd))
        db.add(ShopSettingsRow(site_key=key, phone_verify=False, order_on=True))
    return key


def _order(client, qty=2, item="아메리카노"):
    key = _site(client)
    pay_id = orders.create(key, [(item, qty)], "김손님", "010-1234-5678")
    with get_sessionmaker()() as db:
        total = db.scalar(select(PaymentRow.amount).where(PaymentRow.provider_payment_id == pay_id))
    return key, pay_id, total


def _paid_transport(total, currency="KRW"):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "PAID", "amount": {"total": total}, "currency": currency})
    return httpx.MockTransport(handler)


def _failed_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "FAILED", "amount": {"total": 1}, "currency": "KRW"})
    return httpx.MockTransport(handler)


def _mismatch_events(reason=None):
    with get_sessionmaker()() as db:
        rows = db.scalars(select(FunnelEventRow)
                          .where(FunnelEventRow.event == "payment_mismatch")
                          .order_by(FunnelEventRow.id)).all()
    if reason is not None:
        rows = [r for r in rows if (r.props or {}).get("reason") == reason]
    return rows


def _webhook_setup(monkeypatch):
    from app.config import settings
    from app.services import keystore
    raw = b"test-webhook-secret-0123456789ab"
    monkeypatch.setattr(settings, "portone_webhook_secret",
                        "whsec_" + base64.b64encode(raw).decode())
    keystore.invalidate()
    return raw


def _sign(raw: bytes, wid: str, ts: str, body: bytes) -> dict:
    msg = f"{wid}.{ts}.{body.decode()}".encode()
    digest = base64.b64encode(hmac.new(raw, msg, hashlib.sha256).digest()).decode()
    return {"webhook-id": wid, "webhook-timestamp": ts, "webhook-signature": f"v1,{digest}"}


def _bad_events():
    with get_sessionmaker()() as db:
        return db.scalars(select(FunnelEventRow)
                          .where(FunnelEventRow.event == "webhook_bad_signature")
                          .order_by(FunnelEventRow.id)).all()


def _clear_events():
    with get_sessionmaker()() as db, db.begin():
        db.execute(delete(FunnelEventRow))


# 금액 불일치 → 사건 1건, 사유 amount
def test_amount_mismatch_records_event(client, monkeypatch):
    key, pay_id, _total = _order(client)
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(1))  # 다른 금액
    assert payments.complete(pay_id) == "failed"
    [e] = _mismatch_events("amount")
    assert e.props.get("site") == key


def test_currency_mismatch_records_event(client, monkeypatch):
    key, pay_id, total = _order(client)
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(total, currency="USD"))
    assert payments.complete(pay_id) == "failed"
    [e] = _mismatch_events("currency")
    assert e.props.get("site") == key


def test_failed_status_is_not_recorded(client, monkeypatch):
    _, pay_id, _total = _order(client)
    monkeypatch.setattr(payments, "_TRANSPORT", _failed_transport())
    assert payments.complete(pay_id) == "failed"
    assert _mismatch_events() == []


# 서명 실패 종류마다 사건 1건 + 맞는 사유
def test_webhook_missing_headers(client, monkeypatch):
    _webhook_setup(monkeypatch)
    _clear_events()
    body = json.dumps({"data": {"paymentId": "ord_x"}}).encode()
    with pytest.raises(ValueError):
        payments.verify_webhook({}, body)
    [e] = _bad_events()
    assert e.props.get("reason") == "missing"


def test_webhook_stale_timestamp(client, monkeypatch):
    raw = _webhook_setup(monkeypatch)
    body = json.dumps({"data": {"paymentId": "ord_x"}}).encode()
    _clear_events()
    with pytest.raises(ValueError):  # 5분 지난 시각
        payments.verify_webhook(_sign(raw, "msg_1", str(int(time.time()) - 600), body), body)
    with pytest.raises(ValueError):  # 숫자가 아님
        payments.verify_webhook({"webhook-id": "msg_1", "webhook-timestamp": "엊그제",
                                 "webhook-signature": "v1,x"}, body)
    assert [e.props.get("reason") for e in _bad_events()] == ["stale", "stale"]


def test_webhook_no_secret(client, monkeypatch):
    from app.config import settings
    from app.services import keystore
    raw = b"test-webhook-secret-0123456789ab"
    monkeypatch.setattr(settings, "portone_webhook_secret", None)
    keystore.invalidate()
    _clear_events()
    body = json.dumps({"data": {"paymentId": "ord_x"}}).encode()
    wid, ts = "msg_1", str(int(time.time()))
    with pytest.raises(ValueError):
        payments.verify_webhook(_sign(raw, wid, ts, body), body)
    [e] = _bad_events()
    assert e.props.get("reason") == "no_secret"


def test_webhook_mismatch_kinds(client, monkeypatch):
    from app.config import settings
    from app.services import keystore
    raw = _webhook_setup(monkeypatch)
    body = json.dumps({"data": {"paymentId": "ord_x"}}).encode()
    wid, ts = "msg_1", str(int(time.time()))
    good = _sign(raw, wid, ts, body)
    _clear_events()
    bad = dict(good, **{"webhook-signature": "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="})
    with pytest.raises(ValueError):  # 서명 다름
        payments.verify_webhook(bad, body)
    not_json = "json 아님".encode("utf-8")
    with pytest.raises(ValueError):  # 서명은 맞는데 JSON 아님
        payments.verify_webhook(_sign(raw, wid, ts, not_json), not_json)
    with pytest.raises(ValueError):  # 글자로 못 읽음
        payments.verify_webhook(good, None)
    monkeypatch.setattr(settings, "portone_webhook_secret", "깨진키!!")
    keystore.invalidate()
    with pytest.raises(ValueError):  # 비밀값이 base64가 아님
        payments.verify_webhook(good, body)
    assert [e.props.get("reason") for e in _bad_events()] == ["mismatch"] * 4


# 기록이 실패해도 검증 결과는 같다
def test_record_failure_keeps_verify_result(client, monkeypatch):
    raw = _webhook_setup(monkeypatch)
    monkeypatch.setattr(funnel, "record", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    body = json.dumps({"data": {"paymentId": "ord_x"}}).encode()
    wid, ts = "msg_1", str(int(time.time()))
    assert payments.verify_webhook(_sign(raw, wid, ts, body), body)["data"]["paymentId"] == "ord_x"
    bad = dict(_sign(raw, wid, ts, body),
               **{"webhook-signature": "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="})
    with pytest.raises(ValueError):
        payments.verify_webhook(bad, body)


def test_record_failure_keeps_complete_result(client, monkeypatch):
    _, pay_id, _total = _order(client)
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(1))
    monkeypatch.setattr(funnel, "record", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert payments.complete(pay_id) == "failed"


# 스크립트 종료 코드: 사건 없음 0, 하나라도 있으면 1
def test_script_exit_code(client, capsys):
    assert commerce_signals.main([]) == 0
    funnel.record("payment_mismatch", props={"site": "s1", "reason": "amount"})
    assert commerce_signals.main([]) == 1
    out = capsys.readouterr().out
    assert "payment_mismatch" in out and "amount" in out
