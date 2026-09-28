"""손님 명단 바탕 (CUSTOMER_PLAN §1.1·§1.2): 번호 정규화·손님 저장·방문 기록·빈 손님 지우기."""
import datetime

import pytest
from sqlalchemy import update

from app import store
from app.db.models import BookingRow, CustomerRow, InquiryRow
from app.db.session import get_sessionmaker
from app.services import customers


def _site(client):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    session = store.read_session(store.read_room(room_id)["session_id"])
    return room_id, session["requirement_id"]


def _touch(site_key, phone_raw, name=None):
    with get_sessionmaker()() as db, db.begin():
        return customers.touch(db, site_key, phone_raw, name)


@pytest.mark.parametrize("raw,expected", [
    ("010-1234-5678", "01012345678"),
    ("+82 10 1234 5678", "01012345678"),
    ("02-123-4567", "021234567"),
    ("abc", None),
    ("123", None),
    ("owner@example.com", None),
])
def test_normalize_phone(raw, expected):
    assert customers.normalize_phone(raw) == expected


def test_touch_reuses_same_id(client):
    _, key = _site(client)
    first = _touch(key, "010-1234-5678", "김손님")
    assert first is not None
    assert _touch(key, "01012345678", "김손님") == first


def test_touch_ids_differ_across_sites(client):
    _, key_a = _site(client)
    _, key_b = _site(client)
    assert key_a != key_b
    assert _touch(key_a, "010-1234-5678") != _touch(key_b, "010-1234-5678")


def test_touch_bad_phone_returns_none(client):
    _, key = _site(client)
    assert _touch(key, "abc") is None


def test_touch_none_name_keeps_old_name(client):
    _, key = _site(client)
    cid = _touch(key, "010-1111-2222", "김손님")
    assert _touch(key, "010-1111-2222", None) == cid
    with get_sessionmaker()() as db:
        assert db.get(CustomerRow, cid).name == "김손님"
    assert _touch(key, "010-1111-2222", "이손님") == cid
    with get_sessionmaker()() as db:
        assert db.get(CustomerRow, cid).name == "이손님"


def test_history_counts_linked_rows(client):
    _, key = _site(client)
    cid = _touch(key, "010-3333-4444")
    visit = datetime.date.today() + datetime.timedelta(days=1)
    with get_sessionmaker()() as db, db.begin():
        db.add(BookingRow(site_key=key, customer_id=cid, visit_date=visit, visit_time="10:00",
                          party=2, phone="01033334444"))
        db.add(BookingRow(site_key=key, customer_id=cid, visit_date=visit, visit_time="11:00",
                          party=1, phone="01033334444"))
        db.add(BookingRow(site_key=key, visit_date=visit, visit_time="12:00", party=1, phone="01099998888"))
        db.add(InquiryRow(site_key=key, customer_id=cid, contact="01033334444", message="문의해요"))
    with get_sessionmaker()() as db:
        assert customers.history(db, cid) == {"bookings": 2, "inquiries": 1}


@pytest.mark.parametrize("hist,expected", [
    ({"bookings": 0, "inquiries": 0}, "처음 오신 손님이에요."),
    ({"bookings": 2, "inquiries": 3}, "이 번호로 예약 2번·문의 3번 있었어요."),
    ({"bookings": 2, "inquiries": 0}, "이 번호로 예약 2번 있었어요."),
    ({"bookings": 0, "inquiries": 1}, "이 번호로 문의 1번 있었어요."),
])
def test_visit_line(hist, expected):
    assert customers.visit_line(hist) == expected


def test_purge_orphans_only_old_orphans(client):
    _, key = _site(client)
    old_orphan = _touch(key, "010-0000-0001")
    recent = _touch(key, "010-0000-0002")
    linked = _touch(key, "010-0000-0003")
    old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=31)
    with get_sessionmaker()() as db, db.begin():
        db.add(InquiryRow(site_key=key, customer_id=linked, contact="01000000003", message="문의해요"))
        for cid in (old_orphan, linked):
            db.execute(update(CustomerRow).where(CustomerRow.id == cid).values(last_seen=old))
    assert customers.purge_orphans() >= 1
    with get_sessionmaker()() as db:
        assert db.get(CustomerRow, old_orphan) is None
        assert db.get(CustomerRow, recent) is not None
        assert db.get(CustomerRow, linked) is not None
