"""손님·결제 연결 (STAMP_WAVE4_CONTRACT §5 테스트 8·9·10). 실제 포트원·문자는 부르지 않는다."""
import datetime
import re

import httpx
import pytest
from sqlalchemy import delete, select, update

from app import store
from app.api import inquiries as inquiries_api
from app.config import settings
from app.db.models import (
    CouponRow,
    CustomerRow,
    OrderRow,
    PaymentRow,
    PhoneVerificationRow,
    SessionRow,
    ShopSettingsRow,
)
from app.db.session import get_sessionmaker
from app.services import design, keystore, orders, payments, publish_check, stamps
from app.services import sms as sms_svc
from app.services.customers import touch

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


def _site(client, order_on=True):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
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
    return key


def _card(key):
    with get_sessionmaker()() as db:
        return db.scalar(select(SessionRow.prd).where(SessionRow.requirement_id == key))


def _paid_transport(total):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={"id": "cancel_1"})
        return httpx.Response(200, json={"status": "PAID", "amount": {"total": total}, "currency": "KRW"})
    return httpx.MockTransport(handler)


def _order_ids(pay_id):
    with get_sessionmaker()() as db:
        pay = db.scalar(select(PaymentRow).where(PaymentRow.provider_payment_id == pay_id))
        return pay.order_id, pay.amount, pay.site_key


def _balance(key, cid):
    with get_sessionmaker()() as db:
        return stamps.balance(db, key, cid)


def _customer_id(key, phone):
    with get_sessionmaker()() as db:
        return db.scalar(select(CustomerRow.id).where(
            CustomerRow.site_key == key, CustomerRow.phone == phone.replace("-", "")))


# §5 테스트 8: 결제 확정 → 도장 +1
def test_complete_earns_one_stamp(client, monkeypatch, _ready):
    from app.services import notify
    key = _site(client)
    stamps.set_rule("tester", key, active=True, goal=10, per="order")
    phone = "010-2000-0001"
    pay_id = orders.create(key, [("아메리카노", 2)], "김손님", phone)
    with get_sessionmaker()() as db:
        total = db.scalar(select(PaymentRow.amount).where(PaymentRow.provider_payment_id == pay_id))
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(total))
    calls = []
    monkeypatch.setattr(notify, "owner_kakao", lambda room_id, text: calls.append(text))
    assert payments.complete(pay_id) == "paid"
    assert _balance(key, _customer_id(key, phone)) == 1
    assert len(calls) == 1 and "쿠폰 사용" not in calls[0]
    r = client.get(f"/pay/{pay_id}/done")
    assert "도장 1/10" in r.text


# §5 테스트 8: 쿠폰 할인 주문 확정 → 쿠폰 used + 알림에 쿠폰 사용 + 도장 +1
def test_discount_order_settles_coupon_and_earns(client, monkeypatch, _ready):
    from app.services import notify
    key = _site(client)
    stamps.set_rule("tester", key, active=True, goal=10, per="order")
    phone = "010-2000-0002"
    pay_id = orders.create(key, [("아메리카노", 1)], "김손님", phone)
    oid, _, _ = _order_ids(pay_id)
    cid = _customer_id(key, phone)
    with get_sessionmaker()() as db, db.begin():
        coid = stamps.issue(db, key, cid, source="owner", kind="amount", value=1000,
                            title="천원 할인")
        stamps.hold(db, oid, coid)
    with get_sessionmaker()() as db:
        assert db.scalar(select(PaymentRow.amount).where(PaymentRow.provider_payment_id == pay_id)) == 3500
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(3500))
    calls = []
    monkeypatch.setattr(notify, "owner_kakao", lambda room_id, text: calls.append(text))
    assert payments.complete(pay_id) == "paid"
    assert len(calls) == 1 and "쿠폰 사용" in calls[0]
    with get_sessionmaker()() as db:
        coupon = db.get(CouponRow, coid)
        assert coupon.status == "used" and coupon.used_order_id == oid
    assert _balance(key, cid) == 1


def test_complete_free_paths(client, monkeypatch, _ready):
    """complete_free: 모름·금액 남음은 ValueError, paid 뒤에는 already. 0원 성공 경로는 아래 테스트."""
    key = _site(client)
    stamps.set_rule("tester", key, active=True, goal=10, per="order")
    with pytest.raises(ValueError):
        payments.complete_free("ord_nope")
    phone = "010-2000-0006"
    pay_id = orders.create(key, [("아메리카노", 1)], "김손님", phone)
    with pytest.raises(ValueError, match="결제할 금액이 남아 있어요"):
        payments.complete_free(pay_id)
    with get_sessionmaker()() as db:
        total = db.scalar(select(PaymentRow.amount).where(PaymentRow.provider_payment_id == pay_id))
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(total))
    assert payments.complete(pay_id) == "paid"
    assert payments.complete_free(pay_id) == "already"


def test_full_discount_coupon_order_completes_without_portone(client, monkeypatch, _ready):
    """§5 테스트 8: 쿠폰으로 합계 0원 → '쿠폰으로 주문하기' → 포트원을 부르지 않고 paid, 쿠폰 used, 도장 +1.
    (0018에서 payments.amount >= 0, method에 coupon을 허용한 뒤 가능)"""
    key = _site(client)
    stamps.set_rule("tester", key, active=True, goal=10, per="order")
    phone = "010-2000-0007"
    pay_id = orders.create(key, [("아메리카노", 1)], "김손님", phone)
    cid = _customer_id(key, phone)
    with get_sessionmaker()() as db, db.begin():
        coid = stamps.issue(db, key, cid, source="owner", kind="free", value=0, title="음료 1잔 무료")

    def no_portone(request):
        raise AssertionError("0원 주문은 포트원을 부르지 않는다")
    monkeypatch.setattr(payments, "_TRANSPORT", httpx.MockTransport(no_portone))
    r = client.post(f"/pay/{pay_id}/coupon", data={"coupon_id": str(coid)}, headers=ORIGIN,
                    follow_redirects=False)
    assert r.status_code == 303
    page = client.get(f"/pay/{pay_id}")
    assert "쿠폰으로 주문하기" in page.text and "PortOne.requestPayment" not in page.text
    r = client.post(f"/pay/{pay_id}/free", headers=ORIGIN, follow_redirects=False)
    assert r.status_code == 303
    with get_sessionmaker()() as db:
        pay = db.scalar(select(PaymentRow).where(PaymentRow.provider_payment_id == pay_id))
        assert (pay.status, pay.amount, pay.provider, pay.method) == ("paid", 0, "manual", "coupon")
        assert db.get(CouponRow, coid).status == "used"
    assert _balance(key, cid) == 1


# §5 테스트 8: 전액 환불 → 도장 회수
def test_full_refund_revokes_stamp(client, monkeypatch, _ready):
    key = _site(client)
    stamps.set_rule("tester", key, active=True, goal=10, per="order")
    phone = "010-2000-0003"
    pay_id = orders.create(key, [("아메리카노", 1)], "김손님", phone)
    with get_sessionmaker()() as db:
        total = db.scalar(select(PaymentRow.amount).where(PaymentRow.provider_payment_id == pay_id))
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(total))
    assert payments.complete(pay_id) == "paid"
    oid, _, _ = _order_ids(pay_id)
    assert _balance(key, _customer_id(key, phone)) == 1
    out = payments.refund(key, oid, None, "변심", "owner1")
    assert out["remaining"] == 0
    assert _balance(key, _customer_id(key, phone)) == 0


# §5 테스트 8: /pay 쿠폰 고르기 → 할인·합계 표시 + 확정 뒤 done 도장줄
def test_pay_page_coupon_hold_and_done_line(client, monkeypatch, _ready):
    key = _site(client)
    stamps.set_rule("tester", key, active=True, goal=10, per="order")
    phone = "010-2000-0004"
    pay_id = orders.create(key, [("아메리카노", 1)], "김손님", phone)
    cid = _customer_id(key, phone)
    with get_sessionmaker()() as db, db.begin():
        coid = stamps.issue(db, key, cid, source="owner", kind="amount", value=1000,
                            title="천원 할인")
    with get_sessionmaker()() as db:
        code = db.scalar(select(CouponRow.code).where(CouponRow.id == coid))
    r = client.get(f"/pay/{pay_id}")
    assert r.status_code == 200 and "천원 할인" in r.text and "쓰지 않기" in r.text
    assert "결제할 금액" in r.text and code not in r.text  # 번호 전체는 내 스탬프에만
    hold = client.post(f"/pay/{pay_id}/coupon", data={"coupon_id": str(coid)},
                       headers=ORIGIN, follow_redirects=False)
    assert hold.status_code == 303 and hold.headers["location"] == f"/pay/{pay_id}"
    r = client.get(f"/pay/{pay_id}")
    assert "쿠폰 할인 1,000원" in r.text and "결제할 금액 3,500원" in r.text
    assert "3,500원 결제하기" in r.text
    with get_sessionmaker()() as db:
        total = db.scalar(select(PaymentRow.amount).where(PaymentRow.provider_payment_id == pay_id))
    monkeypatch.setattr(payments, "_TRANSPORT", _paid_transport(total))
    done = client.get(f"/pay/{pay_id}/done")
    assert "주문이 들어갔어요" in done.text and "도장 1/10" in done.text
    # 남의 쿠폰은 고를 수 없음 → 같은 화면에 문구
    pay_id2 = orders.create(key, [("카페라떼", 1)], "이손님", "010-2000-0005")
    bad = client.post(f"/pay/{pay_id2}/coupon", data={"coupon_id": str(coid)}, headers=ORIGIN)
    assert bad.status_code == 200 and "쓸 수 있는 쿠폰이 아니에요" in bad.text


def _code_of(text):
    return re.search(r"인증번호 (\d{6})", text).group(1)


def _cookie_value(set_cookie, name):
    first = (set_cookie or "").split(";")[0]
    k, _, v = first.partition("=")
    assert k.strip() == name
    return v.strip()


# §5 테스트 9: /my — 쿠키 없으면 전화 입력, 인증 뒤 도장판·바코드
def test_my_page_verify_then_board_and_barcode(client, _sms, _ready):
    key = _site(client)
    stamps.set_rule("tester", key, active=True, goal=10, per="order")
    phone = "010-2000-0011"
    pay_id = orders.create(key, [("아메리카노", 1)], "김손님", phone)
    cid = _customer_id(key, phone)
    with get_sessionmaker()() as db, db.begin():
        stamps.issue(db, key, cid, source="owner", kind="free", value=0, title="음료 1잔 무료")
    with get_sessionmaker()() as db, db.begin():
        stamps.manual(db, key, phone, 1, "owner1")
    with get_sessionmaker()() as db:
        code = db.scalar(select(CouponRow.code).where(
            CouponRow.site_key == key).order_by(CouponRow.id.desc()))
    assert len(code) == 12

    r = client.get(f"/api/orders/{key}/my")
    assert r.status_code == 200 and "번호로 확인하기" in r.text
    assert 'name="phone"' in r.text and "<script" not in r.text

    start = client.post(f"/api/orders/{key}/my", data={"phone": phone}, follow_redirects=False)
    assert start.status_code == 303
    loc = start.headers["location"]
    assert loc.startswith(f"/api/orders/{key}/verify/")
    done = client.post(loc, data={"code": _code_of(_sms[-1][1])}, follow_redirects=False)
    assert done.status_code == 303 and done.headers["location"] == f"/api/orders/{key}/my"
    cookie = _cookie_value(done.headers.get("set-cookie"), f"pv_{key}")

    page = client.get(f"/api/orders/{key}/my", cookies={f"pv_{key}": cookie})
    assert page.status_code == 200
    assert "도장 1/10" in page.text
    assert "음료 1잔 무료" in page.text and "<svg" in page.text and "<script" not in page.text
    assert f"{code[0:4]} {code[4:8]} {code[8:12]}" in page.text
    assert "화면을 밝게 하고 보여 주세요" in page.text
    csp = page.headers.get("content-security-policy", "")
    assert "default-src 'none'" in csp and "img-src data:" in csp
    assert page.headers.get("referrer-policy") == "no-referrer"
    assert page.headers.get("cache-control") == "no-store"
    assert page.headers.get("x-content-type-options") == "nosniff"
    assert pay_id  # 주문 연결 확인용


def test_my_page_other_shop_cookie_and_rule_off(client, _sms, _ready):
    key = _site(client)
    other = _site(client)
    stamps.set_rule("tester", key, active=True, goal=10, per="order")
    phone = "010-2000-0012"
    orders.create(key, [("아메리카노", 1)], "김손님", phone)
    start = client.post(f"/api/orders/{key}/my", data={"phone": phone}, follow_redirects=False)
    assert start.status_code == 303
    loc = start.headers["location"]
    done = client.post(loc, data={"code": _code_of(_sms[-1][1])}, follow_redirects=False)
    cookie = _cookie_value(done.headers.get("set-cookie"), f"pv_{key}")
    # 다른 가게 주소에 이 쿠키를 보내도 번호 입력 화면 (서명이 가게별로 다름)
    page = client.get(f"/api/orders/{other}/my", cookies={f"pv_{key}": cookie})
    assert "번호로 확인하기" in page.text
    # 규칙을 끄면 안내만
    stamps.set_rule("tester", key, active=False)
    off = client.get(f"/api/orders/{key}/my", cookies={f"pv_{key}": cookie})
    assert "이 가게는 스탬프를 쓰지 않아요" in off.text


# §5 테스트 10: 규칙 켠 가게 공개본 내비·앱형 탭에 스탬프 링크
def test_publish_has_stamp_link_and_off_removes(client, _ready):
    key = _site(client, order_on=True)
    stamps.set_rule("tester", key, active=True, goal=10, per="order")
    design.publish_choice(key, _card(key), "v1")
    page = (settings.generated_dir / key / "published" / "index.html").read_text(encoding="utf-8")
    assert "스탬프" in page and f"/api/orders/{key}/my" in page
    publish_check.assert_publishable(page)
    design.publish_choice(key, _card(key), "v3")
    app_page = (settings.generated_dir / key / "published" / "index.html").read_text(encoding="utf-8")
    assert "스탬프" in app_page and f"/api/orders/{key}/my" in app_page
    publish_check.assert_publishable(app_page)
    stamps.set_rule("tester", key, active=False)
    design.publish_choice(key, _card(key), "v1")
    plain = (settings.generated_dir / key / "published" / "index.html").read_text(encoding="utf-8")
    assert f"/api/orders/{key}/my" not in plain
    publish_check.assert_publishable(plain)


def test_purge_orphans_keeps_order_only_customer(client):
    key = _site(client)
    phone = "010-2000-0099"
    orders.create(key, [("아메리카노", 1)], "김손님", phone)
    with get_sessionmaker()() as db, db.begin():
        touch(db, key, "010-2000-0098", None)
    old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=40)
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(CustomerRow).where(CustomerRow.site_key == key,
                                             CustomerRow.phone.in_(["01020000099", "01020000098"]))
                   .values(last_seen=old))
    from app.services import customers
    customers.purge_orphans()
    with get_sessionmaker()() as db:
        assert db.scalar(select(CustomerRow.id).where(
            CustomerRow.site_key == key, CustomerRow.phone == "01020000099")) is not None
        assert db.scalar(select(CustomerRow.id).where(
            CustomerRow.site_key == key, CustomerRow.phone == "01020000098")) is None
