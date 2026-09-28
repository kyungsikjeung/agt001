"""예약 엔진 (BOOKING_BOT_IMPL_PLAN BOOK-1~BOOK-8, SPEC-3). 실제 PostgreSQL(배제 제약·잠금)."""
import copy
import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import store
from app.db.models import BookingEventRow, BookingRow
from app.db.session import get_sessionmaker
from app.services import booking_engine as E
from app.services import shops
from app.services.slots import KST

SALON = {
    "mode": "slot", "step_min": 30,
    "weekly_hours": {d: [["10:00", "20:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")},
    "services": [{"name": "컷", "duration_min": 60, "buffer_min": 15},
                 {"name": "펌", "duration_min": 150, "buffer_min": 15}],
    "resources": [{"key": "r1", "kind": "staff", "name": "원장"}],
    "policy": {"lead_min": 60, "max_days": 30, "change_deadline_hours": 24, "cancel_deadline_hours": 3},
}
DINER = {
    "mode": "table", "step_min": 30,
    "weekly_hours": {d: [["17:00", "22:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")},
    "meal_minutes": {"1-4": 90, "5+": 120}, "pace": {"teams": 2, "people": 8},
    "policy": {"lead_min": 60, "party_max": 8},
}
NOW = datetime.datetime.now(KST).replace(hour=9, minute=0, second=0, microsecond=0)
DAY = NOW.date() + datetime.timedelta(days=3)


def _site(client, spec=SALON):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    with get_sessionmaker()() as db, db.begin():
        shop_id = shops.ensure(db, key)
    E.save_draft(shop_id, copy.deepcopy(spec), None)
    E.activate(shop_id, None)
    return room_id, key, shop_id


def _times(key, **kw):
    return [f["time"] for f in E.available(key, DAY, now=NOW, **kw)]


def _room_texts(client, room_id):
    msgs = client.get(f"/room/{room_id}/messages", headers={"X-Member-Id": "owner"}).json()["messages"]
    return [m["text"] for m in msgs if m["kind"].startswith("booking")]


def test_hold_then_confirm_blocks_duration_and_notifies(client):
    room_id, key, _ = _site(client)
    bid = E.hold(key, DAY, "14:00", service="펌", token_hash="t1", now=NOW)
    assert "14:00" not in _times(key, service="컷")
    out = E.confirm_hold(key, bid, "t1", name="김손님", phone="010-1234-5678", now=NOW)
    assert out["status"] == "requested" and out["service"] == "펌 · 원장"
    times = _times(key, service="컷")
    assert "12:30" in times and "13:00" not in times and "16:30" not in times and "17:00" in times
    assert any("새 예약 신청" in t and "010-1234-5678" in t for t in _room_texts(client, room_id))


def test_second_hold_same_time_rejected(client):
    _, key, _ = _site(client)
    E.hold(key, DAY, "14:00", service="컷", token_hash="a", now=NOW)
    with pytest.raises(E.SlotTaken):
        E.hold(key, DAY, "14:30", service="컷", token_hash="b", now=NOW)


def test_exclusion_constraint_blocks_direct_overlap(client):
    _, key, shop_id = _site(client)
    start = datetime.datetime.combine(DAY, datetime.time(15, 0), tzinfo=KST)
    base = dict(site_key=key, shop_id=shop_id, visit_date=DAY, visit_time="15:00", party=1, phone="010",
                status="confirmed", resource_key="r1")
    with get_sessionmaker()() as db, db.begin():
        db.add(BookingRow(start_at=start, end_at=start + datetime.timedelta(hours=1), **base))
    with pytest.raises(IntegrityError):
        with get_sessionmaker()() as db, db.begin():
            db.add(BookingRow(start_at=start + datetime.timedelta(minutes=30),
                              end_at=start + datetime.timedelta(minutes=90), **base))


def test_hold_expires(client):
    _, key, _ = _site(client)
    bid = E.hold(key, DAY, "14:00", service="컷", token_hash="a", now=NOW)
    later = NOW + datetime.timedelta(minutes=11)
    E.hold(key, DAY, "14:00", service="컷", token_hash="b", now=later)
    with pytest.raises(E.HoldExpired):
        E.confirm_hold(key, bid, "a", name=None, phone="010-1111-2222", now=later)


def test_confirm_needs_same_token_and_valid_phone(client):
    _, key, _ = _site(client)
    bid = E.hold(key, DAY, "11:00", service="컷", token_hash="a", now=NOW)
    with pytest.raises(E.NotFound):
        E.confirm_hold(key, bid, "other", name=None, phone="010-1111-2222", now=NOW)
    with pytest.raises(E.EngineError):
        E.confirm_hold(key, bid, "a", name=None, phone="12", now=NOW)


def test_change_moves_and_failure_keeps_old(client):
    _, key, _ = _site(client)
    bid = E.book_now(key, DAY, "14:00", service="컷", phone="010-1234-5678", token_hash="t", now=NOW)["id"]
    other = E.book_now(key, DAY, "17:00", service="컷", phone="010-9999-0000", token_hash="u", now=NOW)["id"]
    # 겹치는 가까운 시각(14:30)으로도 옮길 수 있다(옛 자리를 먼저 푼다)
    moved = E.change(key, bid, "t", DAY, "14:30", now=NOW)
    assert moved["time"] == "14:30" and moved["id"] != bid
    with pytest.raises(E.SlotTaken):
        E.change(key, moved["id"], "t", DAY, "17:00", now=NOW)
    mine = E.my_bookings(key, "t", now=NOW)
    assert [b["id"] for b in mine] == [moved["id"]]
    assert other not in [b["id"] for b in mine]
    with pytest.raises(E.NotFound):
        E.change(key, other, "t", DAY, "18:00", now=NOW)


def test_deadlines(client):
    _, key, _ = _site(client)
    bid = E.book_now(key, DAY, "14:00", service="컷", phone="010-1234-5678", token_hash="t", now=NOW)["id"]
    close = datetime.datetime.combine(DAY, datetime.time(12, 0), tzinfo=KST)
    with pytest.raises(E.DeadlinePassed):
        E.change(key, bid, "t", DAY, "16:00", now=close)
    with pytest.raises(E.DeadlinePassed):
        E.cancel(key, bid, token_hash="t", now=close)
    assert E.cancel(key, bid, token_hash="t", now=NOW)["status"] == "cancelled"
    assert "14:00" in _times(key, service="컷")


def test_owner_actions_and_events(client):
    _, key, shop_id = _site(client)
    bid = E.book_now(key, DAY, "14:00", service="컷", phone="010-1234-5678", now=NOW)["id"]
    assert E.owner_action(shop_id, bid, "confirm", "u1")["status"] == "confirmed"
    with pytest.raises(E.NotAllowed):
        E.owner_action(shop_id, bid, "decline", "u1")
    with pytest.raises(E.NotAllowed):
        E.owner_action(shop_id, bid, "no_show", "u1", now=NOW)
    after = datetime.datetime.combine(DAY, datetime.time(16, 0), tzinfo=KST)
    assert E.owner_action(shop_id, bid, "no_show", "u1", now=after)["status"] == "no_show"
    phone = E.book_now(key, DAY, "10:00", service="컷", phone="010-2222-3333", source="phone", actor="owner", now=NOW)
    assert phone["status"] == "confirmed"
    with get_sessionmaker()() as db:
        actions = db.scalars(select(BookingEventRow.action).where(BookingEventRow.booking_id == bid)
                             .order_by(BookingEventRow.id)).all()
    assert actions == ["requested", "confirmed", "no_show"]
    listed = E.list_for_owner(shop_id, DAY, DAY)
    assert {b["id"] for b in listed} == {bid, phone["id"]}


def test_auto_confirm(client):
    spec = copy.deepcopy(SALON)
    spec["policy"]["auto_confirm"] = True
    _, key, _ = _site(client, spec)
    bid = E.hold(key, DAY, "11:00", service="컷", token_hash="a", now=NOW)
    assert E.confirm_hold(key, bid, "a", name="이", phone="010-1111-2222", now=NOW)["status"] == "confirmed"


def test_stale_request_releases_after_hold_hours(client):
    _, key, _ = _site(client)
    E.book_now(key, DAY, "14:00", service="컷", phone="010-1234-5678", now=NOW)
    assert "14:00" not in _times(key, service="컷")
    later = datetime.datetime.now(KST) + datetime.timedelta(hours=25)  # 신청 뒤 hold_hours(24) 지남, 방문일 전
    assert "14:00" in [f["time"] for f in E.available(key, DAY, service="컷", now=later)]


def test_closure_blocks_and_reports_conflicts(client):
    _, key, shop_id = _site(client)
    E.book_now(key, DAY, "15:00", service="컷", phone="010-1234-5678", now=NOW)
    a = datetime.datetime.combine(DAY, datetime.time(14, 0), tzinfo=KST)
    got = E.add_closure(shop_id, a, a + datetime.timedelta(hours=3), reason="개인 사정")
    assert [c["time"] for c in got["conflicts"]] == ["15:00"]
    times = _times(key, service="컷")
    assert "13:00" in times and "13:30" not in times and "16:30" not in times and "17:00" in times
    assert E.delete_closure(shop_id, got["id"]) and not E.delete_closure(shop_id, got["id"])


def test_activate_validates_and_reverts(client):
    _, key, shop_id = _site(client)
    first = E.get_spec(shop_id)["id"]
    bad = copy.deepcopy(SALON)
    bad["resources"] = []
    E.save_draft(shop_id, bad, None)
    with pytest.raises(E.EngineError):
        E.activate(shop_id, None)
    better = copy.deepcopy(SALON)
    better["step_min"] = 60
    E.save_draft(shop_id, better, None)
    E.activate(shop_id, None)
    assert E.get_spec(shop_id)["spec"]["step_min"] == 60
    E.activate(shop_id, None, spec_id=first)
    assert E.get_spec(shop_id)["spec"]["step_min"] == 30


def test_no_spec_shop_is_rejected(client):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    assert E.active_spec(key) is None
    with pytest.raises(E.NotFound):
        E.available(key, DAY)


def test_table_pacing(client):
    _, key, _ = _site(client, DINER)
    E.book_now(key, DAY, "18:00", party=4, phone="010-1111-1111", now=NOW)
    E.book_now(key, DAY, "18:00", party=3, phone="010-2222-2222", now=NOW)
    with pytest.raises(E.SlotTaken):   # 2팀 한도
        E.book_now(key, DAY, "18:00", party=1, phone="010-3333-3333", now=NOW)
    assert "18:00" not in _times(key, party=2) and "18:30" in _times(key, party=2)


def test_concurrent_same_slot_only_one_wins(client):
    import threading
    _, key, _ = _site(client)
    results = []

    def go(i):
        try:
            E.book_now(key, DAY, "15:00", service="컷", phone=f"010-1234-00{i:02d}", now=NOW, notify=False)
            results.append("ok")
        except E.SlotTaken:
            results.append("taken")

    threads = [threading.Thread(target=go, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["ok"] + ["taken"] * 5


def test_site_form_goes_through_engine_when_spec_active(client):
    from app.services import bookings
    room_id, key, _ = _site(client)
    kw = dict(date=DAY.isoformat(), party="1", name="폼손님", phone="010-5555-6666", memo=None, agree="yes", website=None)
    assert bookings.submit(key, time="14:00", service="펌 · 원장", **kw)
    with get_sessionmaker()() as db:
        row = db.scalar(select(BookingRow).where(BookingRow.site_key == key))
    assert row.source == "web" and row.resource_key == "r1" and row.end_at - row.start_at == datetime.timedelta(minutes=165)
    with pytest.raises(bookings.BookingError):
        bookings.submit(key, time="15:00", service="컷", **kw)   # 펌이 16:45까지
    with pytest.raises(bookings.BookingError):
        bookings.submit(key, time="18:00", service="없는시술", **kw)
