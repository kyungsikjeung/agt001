"""프로젝트 삭제 (대표 10/5, 유예 30일): 지우면 서비스가 닫히고 돈이 멈추는가, 30일 뒤 기록이 사라지는가.

돈이 걸린 경로라 한 번에 끝까지 본다: 결제받던 가게를 지우고 → 사이트·주문·결제가 막히는지 →
구독(우리 요금)이 해지되고 포트원 예약 결제가 취소되는지 → 유예 중에는 되살아나는지 →
30일 뒤 **그 가게만** 사라지는지(옆 가게는 그대로).
"""
import datetime
import re
import secrets

import httpx
import pytest
from sqlalchemy import delete, select, update

from app import store
from app.config import settings
from app.db.models import (
    CustomerRow,
    OrderRow,
    PaymentRow,
    PhoneVerificationRow,
    RoomRow,
    SessionRow,
    ShopRow,
    ShopSettingsRow,
    SubscriptionRow,
    UserRoomRow,
    UserRow,
)
from app.db.session import get_sessionmaker
from app.services import design, keystore, payments, project_delete, takedown
from app.services import sms as sms_svc

MENU = ["아메리카노"]
PRICES = {"아메리카노": "4,500원"}
ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """IP당 신청 횟수 제한은 모듈 상태라 앞 테스트의 주문이 남아 있다 (test_commerce_flow와 같은 처리)."""
    from app.api import inquiries as inquiries_api
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


CANCELED_SCHEDULES: list = []


def _portone(request: httpx.Request) -> httpx.Response:
    """포트원 가짜: 조회는 DB 금액 그대로 PAID, 예약 취소는 성공으로 기록."""
    if request.url.path == "/payment-schedules" and request.method == "DELETE":
        CANCELED_SCHEDULES.append(request.read().decode())
        return httpx.Response(200, json={"revokedScheduleIds": ["sch_1"]})
    pid = request.url.path.rsplit("/", 1)[-1]
    with get_sessionmaker()() as db:
        total = db.scalar(select(PaymentRow.amount).where(PaymentRow.provider_payment_id == pid))
    return httpx.Response(200, json={"status": "PAID", "amount": {"total": total}, "currency": "KRW"})


@pytest.fixture(autouse=True)
def _reset_schedules():
    CANCELED_SCHEDULES.clear()


@pytest.fixture(autouse=True)
def _pay_ready(monkeypatch):
    monkeypatch.setattr(settings, "portone_store_id", "store-test")
    monkeypatch.setattr(settings, "portone_channel_key", "channel-test")
    monkeypatch.setattr(settings, "portone_api_secret", "secret-test")
    monkeypatch.setattr(payments, "_TRANSPORT", httpx.MockTransport(_portone))
    keystore.invalidate()


def _site(client, phone: str):
    """주문 받는 카페 하나를 공개까지 만든다. (room_id, site_key)."""
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    prd = {"slots": {"shop_name": {"value": "우리 가게", "status": "filled"},
                     "business_type": {"value": "카페", "status": "filled"},
                     "contact_method": {"value": "픽업 주문", "status": "filled"},
                     "phone": {"value": phone, "status": "filled"},
                     "hours": {"value": "매일 09~22시", "status": "filled"},
                     "location": {"value": "경기 수원시 행궁동 근처", "status": "filled"},
                     "offerings": {"value": list(MENU), "status": "filled"}},
           "price_pairs": dict(PRICES), "industry": "cafe", "published": "v1"}
    uid = f"u-{secrets.token_hex(4)}"
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(SessionRow).where(SessionRow.requirement_id == key).values(prd=prd))
        db.add(ShopSettingsRow(site_key=key, phone_verify=False, order_on=True))
        db.add(UserRow(id=uid, nickname="사장님"))
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRoomRow(user_id=uid, room_id=room_id, member_id="owner"))
    design.publish_choice(key, prd, "v1")
    return room_id, key


def _order(client, key, phone, sms):
    """주문 → 문자 인증 → 결제 링크(아직 결제 안 함). pay_id를 돌려준다."""
    form = {"item_0": MENU[0], "qty_0": "1", "name": "김손님", "phone": phone, "website": ""}
    r = client.post(f"/api/orders/{key}", data=form, follow_redirects=False)
    assert r.status_code == 303, r.text
    code = re.search(r"인증번호 (\d{6})", sms[-1][1]).group(1)
    done = client.post(r.headers["location"], data={"code": code}, follow_redirects=False)
    assert done.status_code == 303 and done.headers["location"].startswith("/pay/ord_")
    return done.headers["location"].rsplit("/", 1)[-1]


def _order_and_pay(client, key, phone, sms):
    """주문 → 문자 인증 → 결제 완료. 결제 번호를 돌려준다."""
    pay_id = _order(client, key, phone, sms)
    assert "주문이 들어갔어요" in client.get(f"/pay/{pay_id}/done").text
    with get_sessionmaker()() as db:
        assert db.scalar(select(PaymentRow.status).where(PaymentRow.provider_payment_id == pay_id)) == "paid"
    return pay_id


def _order_refused(client, key, phone):
    """새 주문이 막혔는가. 막히면 303이 아니라 안내 화면이 돌아온다."""
    form = {"item_0": MENU[0], "qty_0": "1", "name": "김손님", "phone": phone, "website": ""}
    r = client.post(f"/api/orders/{key}", data=form, follow_redirects=False)
    return r.status_code != 303 and "주문" in r.text


def _rows(key, room_id):
    """그 가게·방에 남은 행 수 (가게, 주문, 결제, 손님, 방)."""
    with get_sessionmaker()() as db:
        return (
            len(db.scalars(select(ShopRow.site_key).where(ShopRow.site_key == key)).all()),
            len(db.scalars(select(OrderRow.id).where(OrderRow.site_key == key)).all()),
            len(db.scalars(select(PaymentRow.id).where(PaymentRow.site_key == key)).all()),
            len(db.scalars(select(CustomerRow.id).where(CustomerRow.site_key == key)).all()),
            1 if db.get(RoomRow, room_id) else 0,
        )


def _subscribe(key, schedule_id="sch_1"):
    """이 가게가 우리 요금제를 쓰고 있다 — 빌링키 + 다음 달 예약 결제가 걸린 상태."""
    with get_sessionmaker()() as db, db.begin():
        db.add(SubscriptionRow(site_key=key, plan="starter", status="active",
                               billing_key_enc="enc:billing-key", card_last4="1234",
                               next_schedule_id=schedule_id))


def _subscription(key):
    with get_sessionmaker()() as db:
        row = db.get(SubscriptionRow, key)
        return row and (row.status, row.billing_key_enc, row.next_schedule_id, row.cancel_at_period_end)


def test_delete_paid_project(client, _sms):
    """돈을 받던 가게를 지우면: 사이트·주문·결제 닫힘 + 구독 해지 → 30일 뒤 그 가게만 영구 삭제."""
    room_id, key = _site(client, "010-1234-5678")
    other_room, other_key = _site(client, "010-9999-0000")  # 옆 가게 (건드리면 안 된다)
    _order_and_pay(client, key, "010-2000-0001", _sms)  # 이미 받은 돈
    open_pay = _order(client, key, "010-2000-0009", _sms)  # 지우기 직전에 나간 결제 링크
    _order_and_pay(client, other_key, "010-3000-0001", _sms)
    _subscribe(key)  # 가게 행(shops)은 첫 주문 때 생긴다
    _subscribe(other_key, "sch_other")
    assert client.get(f"/site/{key}/").status_code == 200
    assert _rows(key, room_id) == (1, 2, 2, 2, 1)

    # 1. 지우기 — 방장만 (다른 참여자는 403, 남은 사람은 404)
    assert client.post(f"/api/projects/{room_id}/delete", headers={"X-Member-Id": "nobody"}).status_code == 404
    r = client.post(f"/api/projects/{room_id}/delete", headers={"X-Member-Id": "owner"})
    assert r.status_code == 200, r.text
    deleted_at = datetime.datetime.fromisoformat(r.json()["deleted_at"])
    assert r.json()["grace_days"] == project_delete.GRACE_DAYS

    # 2. 서비스가 닫혔다: 공개 사이트·새 주문·이미 받은 결제 링크 모두
    assert takedown.is_down(key)
    assert client.get(f"/site/{key}/").status_code == 410
    assert _order_refused(client, key, "010-2000-0002")
    page = client.get(f"/pay/{open_pay}")
    assert "주문을 받지 않아요" in page.text and "결제하기" not in page.text, \
        "지우기 직전에 나간 결제 링크로도 더 이상 결제할 수 없어야 한다"
    assert "주문을 받지 않아요" in client.post(f"/pay/{open_pay}/free", headers=ORIGIN).text
    assert "주문을 받지 않아요" in client.get(f"/api/orders/{key}/my").text  # 내 주문 내역도 닫힌다

    # 3. 구독(우리 요금)도 같은 자리에서 해지 — 포트원 예약 결제 취소 + 빌링키 버리기
    assert CANCELED_SCHEDULES and "sch_1" in CANCELED_SCHEDULES[0], \
        "포트원 예약 결제를 취소하지 않으면 지운 뒤에도 카드가 계속 긁힌다"
    assert "sch_other" not in "".join(CANCELED_SCHEDULES)  # 옆 가게 구독은 건드리지 않는다
    assert _subscription(key) == ("canceled", None, None, True)
    assert _subscription(other_key) == ("active", "enc:billing-key", "sch_other", False)

    # 4. 유예 기간(30일) 안에는 아무것도 지워지지 않는다
    assert project_delete.purge_deleted(now=deleted_at + datetime.timedelta(days=29, hours=23)) == 0
    assert _rows(key, room_id) == (1, 2, 2, 2, 1)

    # 5. 되살리면 서비스는 돌아온다. 구독은 돌아오지 않는다(카드 정보를 버렸으니 다시 신청해야 한다)
    assert client.post(f"/api/projects/{room_id}/restore", headers={"X-Member-Id": "owner"}).status_code == 200
    assert not takedown.is_down(key)
    assert client.get(f"/site/{key}/").status_code == 200
    assert not _order_refused(client, key, "010-2000-0003")
    assert _subscription(key) == ("canceled", None, None, True)

    # 6. 다시 지우고 30일이 지나면 그 가게 기록만 영구 삭제 (옆 가게는 그대로)
    again = client.post(f"/api/projects/{room_id}/delete", headers={"X-Member-Id": "owner"})
    assert again.status_code == 200, again.text
    assert project_delete.purge_deleted(now=deleted_at + datetime.timedelta(days=31)) == 1
    assert _rows(key, room_id) == (0, 0, 0, 0, 0)
    assert not (settings.generated_dir / key).exists()
    assert _rows(other_key, other_room) == (1, 1, 1, 1, 1)
    assert client.get(f"/site/{other_key}/").status_code == 200
    with get_sessionmaker()() as db:
        assert db.scalar(select(SessionRow.id).where(SessionRow.requirement_id == key)) is None
