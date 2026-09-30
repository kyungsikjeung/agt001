"""비상 스위치 (WAVE5_CONTRACT §2.5). 실제 포트원·문자는 부르지 않는다."""
import base64
import hashlib
import hmac
import importlib.util
import json
import re
import secrets
import time

import httpx
import pytest
from sqlalchemy import delete, func, select, update

from app import store
from app.api import inquiries as inquiries_api
from app.config import settings
from app.db.models import (
    OrderRow,
    PaymentRow,
    PhoneVerificationRow,
    SessionRow,
    ShopSettingsRow,
    UserRoomRow,
    UserRow,
)
from app.db.session import get_sessionmaker
from app.services import auth as auth_svc
from app.services import design, keystore, orders, payments, stamps
from app.services import sms as sms_svc

MENU = ["아메리카노", "카페라떼"]
PRICES = {"아메리카노": "4,500원", "카페라떼": "5,000원"}
ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    inquiries_api._hits.clear()


@pytest.fixture(autouse=True)
def _clean_verify(monkeypatch):
    monkeypatch.setattr(settings, "token_enc_key", "test-device-key")
    with get_sessionmaker()() as db, db.begin():
        db.execute(delete(PhoneVerificationRow))


@pytest.fixture
def _sms(monkeypatch):
    sent = []
    monkeypatch.setattr(sms_svc, "send", lambda to, text, site_key=None: sent.append((to, text)) or True)
    return sent


@pytest.fixture
def _ready(monkeypatch):
    monkeypatch.setattr(settings, "portone_store_id", "store-test")
    monkeypatch.setattr(settings, "portone_channel_key", "channel-test")
    monkeypatch.setattr(settings, "portone_api_secret", "secret-test")
    keystore.invalidate()


def _site(client, order_on=True, rule=True):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    uid = f"u-{secrets.token_hex(4)}"
    prd = {"slots": {"shop_name": {"value": "우리 가게", "status": "filled"},
                     "business_type": {"value": "카페", "status": "filled"},
                     "contact_method": {"value": "픽업 주문", "status": "filled"},
                     "phone": {"value": "010-1234-5678", "status": "filled"},
                     "hours": {"value": "매일 09~22시", "status": "filled"},
                     "location": {"value": "경기 수원시 행궁동 근처", "status": "filled"},
                     "offerings": {"value": list(MENU), "status": "filled"}},
           "price_pairs": dict(PRICES), "industry": "cafe", "published": "v1"}
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(SessionRow).where(SessionRow.requirement_id == key).values(prd=prd))
        db.add(ShopSettingsRow(site_key=key, phone_verify=False, order_on=order_on))
        db.add(UserRow(id=uid, nickname="사장님"))
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRoomRow(user_id=uid, room_id=room_id, member_id="owner"))
    if rule:
        stamps.set_rule("tester", key, active=True, goal=10, per="order")
    return key, uid


def _card(key):
    with get_sessionmaker()() as db:
        return db.scalar(select(SessionRow.prd).where(SessionRow.requirement_id == key))


def _published(key):
    return (settings.generated_dir / key / "published" / "index.html").read_text(encoding="utf-8")


def _counts():
    with get_sessionmaker()() as db:
        return (db.scalar(select(func.count()).select_from(OrderRow)),
                db.scalar(select(func.count()).select_from(PaymentRow)))


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/cancel"):
        return httpx.Response(200, json={"id": "cancel_1"})
    pid = request.url.path.rsplit("/", 1)[-1]
    with get_sessionmaker()() as db:
        total = db.scalar(select(PaymentRow.amount).where(PaymentRow.provider_payment_id == pid))
    return httpx.Response(200, json={"status": "PAID", "amount": {"total": total}, "currency": "KRW"})


def _webhook_secret(monkeypatch):
    raw = b"test-webhook-secret-0123456789ab"
    monkeypatch.setattr(settings, "portone_webhook_secret", "whsec_" + base64.b64encode(raw).decode())
    keystore.invalidate()
    return raw


def _sign(raw: bytes, wid: str, ts: str, body: bytes) -> dict:
    msg = f"{wid}.{ts}.{body.decode()}".encode()
    digest = base64.b64encode(hmac.new(raw, msg, hashlib.sha256).digest()).decode()
    return {"webhook-id": wid, "webhook-timestamp": ts, "webhook-signature": f"v1,{digest}"}


def _form(phone="010-2000-0001"):
    return {"item_0": "아메리카노", "qty_0": "1", "name": "김손님", "phone": phone, "website": ""}


def test_paused_blocks_new_starts(client, monkeypatch, _sms, _ready):
    key, _uid = _site(client)
    monkeypatch.setattr(settings, "commerce_paused", True)
    assert orders.paused() is True
    pay_id = orders.create(key, [("아메리카노", 1)], "김손님", "010-2000-0001")
    before = _counts()

    r = client.post(f"/api/orders/{key}", data=_form())
    assert r.status_code == 200 and "잠시 멈췄어요" in r.text
    assert "tel:" in r.text  # 카드 전화 링크
    assert r.headers.get("cache-control") == "no-store"
    assert not _sms  # 문자 없음

    assert client.get(f"/api/orders/{key}/verify/tok_nope").status_code == 200
    assert "잠시 멈췄어요" in client.get(f"/api/orders/{key}/verify/tok_nope").text
    r = client.post(f"/api/orders/{key}/verify/tok_nope", data={"code": "000000"})
    assert r.status_code == 200 and "잠시 멈췄어요" in r.text
    r = client.post(f"/api/orders/{key}/verify/tok_nope/resend")
    assert r.status_code == 200 and "잠시 멈췄어요" in r.text

    r = client.get(f"/pay/{pay_id}")
    assert r.status_code == 200 and "잠시 멈췄어요" in r.text
    assert "PortOne.requestPayment" not in r.text  # 결제창 버튼 없음
    r = client.post(f"/pay/{pay_id}/coupon", data={"coupon_id": ""}, headers=ORIGIN)
    assert r.status_code == 200 and "잠시 멈췄어요" in r.text
    r = client.post(f"/pay/{pay_id}/free", headers=ORIGIN)
    assert r.status_code == 200 and "잠시 멈췄어요" in r.text

    r = client.get(f"/api/orders/{key}/my")
    assert r.status_code == 200 and "스탬프 화면을 잠시 멈췄어요" in r.text
    r = client.post(f"/api/orders/{key}/my", data={"phone": "010-2000-0001"})
    assert r.status_code == 200 and "스탬프 화면을 잠시 멈췄어요" in r.text
    assert not _sms

    assert _counts() == before  # 주문·결제 행 새로 생기지 않음


def test_paused_keeps_done_webhook_refund(client, monkeypatch, _ready):
    key, uid = _site(client)
    raw = _webhook_secret(monkeypatch)
    monkeypatch.setattr(payments, "_TRANSPORT", httpx.MockTransport(_handler))
    monkeypatch.setattr(settings, "commerce_paused", True)
    pay1 = orders.create(key, [("아메리카노", 1)], "김손님", "010-2000-0011")
    pay2 = orders.create(key, [("카페라떼", 1)], "이손님", "010-2000-0012")

    assert "주문이 들어갔어요" in client.get(f"/pay/{pay1}/done").text
    with get_sessionmaker()() as db:
        assert db.scalar(select(PaymentRow.status).where(
            PaymentRow.provider_payment_id == pay1)) == "paid"

    body = json.dumps({"data": {"paymentId": pay2}}).encode()
    r = client.post("/api/payments/webhook", content=body,
                    headers=_sign(raw, "msg_paused", str(int(time.time())), body))
    assert r.status_code == 200 and r.json() == {"ok": True}
    with get_sessionmaker()() as db:
        assert db.scalar(select(PaymentRow.status).where(
            PaymentRow.provider_payment_id == pay2)) == "paid"

    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(uid))
    with get_sessionmaker()() as db:
        oid1 = db.scalar(select(PaymentRow.order_id).where(PaymentRow.provider_payment_id == pay1))
    r = client.post(f"/api/owner/shops/{key}/orders/{oid1}/refund",
                    json={"amount": None, "reason": "품절"}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["remaining"] == 0 and r.json()["status"] == "canceled"


def test_paused_publish_hides_and_restore_shows(client, monkeypatch, _ready):
    key, _uid = _site(client)
    design.publish_choice(key, _card(key), "v1")
    assert 'action="/api/orders/' in _published(key)

    monkeypatch.setattr(settings, "commerce_paused", True)
    design.publish_choice(key, _card(key), "v1")
    page = _published(key)
    assert "/api/orders/" not in page  # 주문 폼·스탬프 링크 없음

    monkeypatch.setattr(settings, "commerce_paused", False)
    design.publish_choice(key, _card(key), "v1")
    page = _published(key)
    assert 'action="/api/orders/' in page and f"/api/orders/{key}/my" in page


def _republish_main():
    path = settings.project_root / "scripts" / "republish_commerce.py"
    spec = importlib.util.spec_from_file_location("republish_commerce", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main


def test_republish_dry_run_selects_only_commerce(client, monkeypatch, _ready, capsys):
    on_key, _u1 = _site(client, order_on=True, rule=True)
    design.publish_choice(on_key, _card(on_key), "v1")
    off_key, _u2 = _site(client, order_on=False, rule=False)
    design.publish_choice(off_key, _card(off_key), "v1")  # 파일은 있지만 주문·스탬프 꺼짐
    monkeypatch.setattr(settings, "commerce_paused", False)
    main = _republish_main()

    assert main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert on_key in out and off_key not in out

    assert main([]) == 0
    first = capsys.readouterr().out
    assert f"다시 공개 1곳, 실패 0곳" in first
    assert 'action="/api/orders/' in _published(on_key)
    assert main([]) == 0  # 멱등: 두 번 실행해도 같음
    assert capsys.readouterr().out == first
