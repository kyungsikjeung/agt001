"""생성 사이트 예약 신청 (플랫폼 공용 ②, BOOKING_PLAN.md): 저장·채팅방 알림·방장 확정·거절·검증·삭제."""
import datetime

import pytest

from app import store
from app.api import inquiries as inquiries_api
from app.db.models import BookingRow
from app.db.session import get_sessionmaker
from app.services import bookings


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    inquiries_api._hits.clear()


def _site(client):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    session = store.read_session(store.read_room(room_id)["session_id"])
    return room_id, session["requirement_id"]


def _day(offset=3):
    return (bookings._today() + datetime.timedelta(days=offset)).isoformat()


def _send(client, key, **over):
    form = {"date": _day(), "time": "14:30", "service": "컷트", "party": "2", "name": "김손님",
            "phone": "010-1234-5678", "memo": "창가 자리", "agree": "yes", "website": ""}
    form.update(over)
    return client.post(f"/api/bookings/{key}", data=form, follow_redirects=False)


def _booking_id(client, room_id):
    msgs = client.get(f"/room/{room_id}/messages", headers={"X-Member-Id": "owner"}).json()["messages"]
    return next(m for m in reversed(msgs) if m["kind"] == "booking")["booking"]["id"]


def test_submit_saves_and_notifies_room_with_booking_id(client):
    room_id, key = _site(client)
    r = _send(client, key)
    assert r.status_code == 303 and r.headers["location"] == f"/api/bookings/{key}/done"
    done = client.get(r.headers["location"])
    assert done.status_code == 200 and "확정된 예약은 아니에요" in done.text
    msgs = client.get(f"/room/{room_id}/messages", headers={"X-Member-Id": "owner"}).json()["messages"]
    msg = next(m for m in msgs if m["kind"] == "booking")
    assert "010-1234-5678" in msg["text"] and "컷트" in msg["text"] and "2명" in msg["text"]
    assert msg["booking"]["status"] == "requested" and isinstance(msg["booking"]["id"], int)
    assert "meta" not in msg


def test_owner_confirms_once(client):
    room_id, key = _site(client)
    _send(client, key)
    bid = _booking_id(client, room_id)
    url = f"/room/{room_id}/bookings/{bid}/decision"
    r = client.post(url, json={"decision": "confirm"}, headers={"X-Member-Id": "owner"})
    assert r.status_code == 200 and r.json() == {"id": bid, "status": "confirmed"}
    assert client.post(url, json={"decision": "decline"}, headers={"X-Member-Id": "owner"}).status_code == 409
    listed = client.get(f"/room/{room_id}/bookings", headers={"X-Member-Id": "owner"}).json()["bookings"]
    assert {"id": bid, "status": "confirmed"} in listed
    assert store.read_messages(room_id, 0)[-1]["kind"] == "booking_result"


def test_non_owner_cannot_decide_or_list(client):
    room_id, key = _site(client)
    client.post(f"/room/{room_id}/chat", json={"member_id": "guest", "nickname": "손님", "message": "안녕하세요"})
    _send(client, key)
    bid = _booking_id(client, room_id)
    assert client.post(f"/room/{room_id}/bookings/{bid}/decision", json={"decision": "confirm"},
                       headers={"X-Member-Id": "guest"}).status_code == 403
    assert client.get(f"/room/{room_id}/bookings", headers={"X-Member-Id": "guest"}).status_code == 403


def test_other_rooms_booking_is_not_found(client):
    room_a, key_a = _site(client)
    room_b, _ = _site(client)
    _send(client, key_a)
    bid = _booking_id(client, room_a)
    # 다른 방의 방장은 남의 가게 예약을 바꿀 수 없다
    r = client.post(f"/room/{room_b}/bookings/{bid}/decision", json={"decision": "confirm"},
                    headers={"X-Member-Id": "owner"})
    assert r.status_code == 404


def test_bad_decision_400(client):
    room_id, key = _site(client)
    _send(client, key)
    bid = _booking_id(client, room_id)
    assert client.post(f"/room/{room_id}/bookings/{bid}/decision", json={"decision": "maybe"},
                       headers={"X-Member-Id": "owner"}).status_code == 400


def test_honeypot_looks_ok_but_not_saved(client):
    room_id, key = _site(client)
    before = len(store.read_messages(room_id, 0))
    assert _send(client, key, website="http://spam").status_code == 303
    assert len(store.read_messages(room_id, 0)) == before


@pytest.mark.parametrize("over", [
    {"date": ""}, {"date": "2020-01-01"}, {"date": _day(61)}, {"time": "25:00"}, {"party": "0"},
    {"party": "21"}, {"party": "두명"}, {"phone": ""}, {"phone": "abc"}, {"agree": ""},
])
def test_invalid_input_400(client, over):
    _, key = _site(client)
    r = _send(client, key, **over)
    assert r.status_code == 400 and "<script" not in r.text


def test_time_is_optional(client):
    room_id, key = _site(client)
    assert _send(client, key, time="").status_code == 303


def test_unknown_site_400(client):
    assert _send(client, "nope-site").status_code == 400


def test_rate_limit_shared_with_inquiries(client):
    _, key = _site(client)
    codes = [_send(client, key).status_code for _ in range(inquiries_api.RATE_LIMIT + 1)]
    assert codes[0] == 303 and codes[-1] == 429


def test_purge_expired(client):
    _, key = _site(client)
    today = bookings._today()
    with get_sessionmaker()() as db, db.begin():
        db.add(BookingRow(site_key=key, visit_date=today - datetime.timedelta(days=31), visit_time="", party=1, phone="010"))
        db.add(BookingRow(site_key=key, visit_date=today - datetime.timedelta(days=29), visit_time="", party=1, phone="010"))
    assert bookings.purge_expired(today) == 1


@pytest.mark.parametrize("hours,first,last", [
    ("매일 10~20시", "10:00", "19:00"), ("월~토 11~21시, 일요일 휴무", "11:00", "20:00"),
    ("오후 2시~8시", None, None), ("", None, None), ("24시간", None, None),
])
def test_time_options_only_when_clear(hours, first, last):
    from app.services.design_variants import _time_options
    opts = _time_options(hours)
    assert (opts[0], opts[-1]) == (first, last) if first else opts == []


def _card(industry, **slots):
    from app.services import prd_engine as E
    from app.services import prd_schema as S
    card = E.new_card(industry)
    for k, v in slots.items():
        E._put(card, k, v, S.FILLED)
    return card


@pytest.mark.parametrize("industry,slots,expected", [
    ("salon", {"offerings": ["컷트", "염색"], "hours": "매일 10~20시"}, True),
    ("salon", {"booking_url": "https://booking.naver.com/x"}, False),
    ("salon", {"exclude": ["예약"]}, False),
    ("cafe", {}, False),
    ("cafe", {"contact_method": "사이트에서 예약 신청"}, True),
])
def test_booking_section_rules(industry, slots, expected):
    from app.services import design_variants as D
    spec = D.base_spec(_card(industry, **slots))
    sec = next((s for s in spec["sections"] if s["type"] == "booking"), None)
    assert (sec is not None) == expected
    if sec and industry == "salon" and "offerings" in slots:
        assert sec["content"]["services"] == ["컷트", "염색"] and sec["content"]["time_options"][0] == "10:00"
        hero = next(s for s in spec["sections"] if s["type"] == "hero")
        assert hero["content"]["cta"]["href"] == "#booking-title-booking"
