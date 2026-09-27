"""예약 현황 실계산 J7 (DB 사용): 영업시간 읽기·현황 계산·공개본 다시 그리기."""
import copy
import datetime
import json

import pytest

from app import store
from app.api import inquiries as inquiries_api
from app.db.models import BookingRow
from app.db.session import get_sessionmaker
from app.services import availability as A
from app.services import bookings
from app.services import design


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    inquiries_api._hits.clear()


def _site(client):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat",
                json={"member_id": "owner", "nickname": "사장님", "message": "동네 미용실이에요. 컷트해요"})
    session = store.read_session(store.read_room(room_id)["session_id"])
    return room_id, session["requirement_id"]


def _day(offset=1):
    return (bookings._today() + datetime.timedelta(days=offset)).isoformat()


def _send(client, key, **over):
    form = {"date": _day(), "time": "10:00", "service": "컷트", "party": "1", "name": "김손님",
            "phone": "010-1234-5678", "memo": "", "agree": "yes", "website": ""}
    form.update(over)
    return client.post(f"/api/bookings/{key}", data=form, follow_redirects=False)


def _booking_id(client, room_id):
    msgs = client.get(f"/room/{room_id}/messages", headers={"X-Member-Id": "owner"}).json()["messages"]
    return next(m for m in reversed(msgs) if m["kind"] == "booking")["booking"]["id"]


def _decide(client, room_id, bid, decision):
    return client.post(f"/room/{room_id}/bookings/{bid}/decision", json={"decision": decision},
                       headers={"X-Member-Id": "owner"})


def _card(hours, staff=None, data=None):
    from app.services import prd_engine as E
    from app.services import prd_schema as S
    card = E.new_card()
    if hours is not None:
        E._put(card, "hours", hours, S.FILLED)
    if staff is not None:
        E._put(card, "staff", staff, S.FILLED)
    if data is not None:
        card["data"] = data
    return card


def _slot_state(days, date, time):
    day = next(d for d in days if d["date"] == date)
    return next(s for s in day["slots"] if s["time"] == time)["state"]


# ── 영업시간 읽기 ──

@pytest.mark.parametrize("hours,opened,closed,shut", [
    ("10~19시", "10:00", "19:00", []),
    ("매일 10~21시", "10:00", "21:00", []),
    ("평일 11~20시", "11:00", "20:00", ["sat", "sun"]),
    ("10~19시, 월요일 휴무", "10:00", "19:00", ["mon"]),
    ("오후 2시~8시", "14:00", "20:00", []),
    ("10:30~19:30", "10:30", "19:30", []),
])
def test_schedule_reads_six_sentence_shapes(hours, opened, closed, shut):
    sched = A.schedule(_card(hours))
    assert sched["source"] == "owner"
    assert sched["closed"] == shut
    assert sched["weekly"]["tue"] == [[opened, closed]]
    assert sched["slot_min"] == 60 and sched["capacity"] == 1


@pytest.mark.parametrize("hours", ["24시간", "", None])
def test_schedule_falls_back_when_unreadable(hours):
    sched = A.schedule(_card(hours))
    assert sched["source"] == "assumed"
    assert sched["closed"] == [] and sched["weekly"]["mon"] == [["10:00", "18:00"]]


def test_schedule_capacity_from_staff_and_rooms():
    two = A.schedule(_card("10~19시", staff=["원장 김미용", "디자이너 박하나"]))
    assert two["capacity"] == 2
    one = A.schedule(_card("10~19시", staff=["원장 김미용"]))
    assert one["capacity"] == 1
    pension = A.schedule(_card("매일 10~21시", data={"staff": [], "rooms": [{"name": "온돌방"}]}))
    assert pension["capacity"] == 1
    pension2 = A.schedule(_card("매일 10~21시", data={"staff": [], "rooms": [{"name": "온돌"}, {"name": "침대"}]}))
    assert pension2["capacity"] == 2


# ── 현황 계산 ──

def test_days_skips_closed(client):
    _, key = _site(client)
    card = _card("10~19시, 월요일 휴무")
    days = A.days(card, key, today=datetime.date(2026, 9, 27), count=3)  # 일요일
    assert [d["date"] for d in days] == ["2026-09-29", "2026-09-30", "2026-10-01"]
    assert days[0]["slots"][0]["time"] == "10:00" and days[0]["slots"][-1]["time"] == "18:00"


def test_confirmed_fills_single_shop_slot(client):
    room_id, key = _site(client)
    _send(client, key)
    _decide(client, room_id, _booking_id(client, room_id), "confirm")
    assert _slot_state(A.days(_card("10~19시"), key), _day(), "10:00") == "full"


def test_two_person_shop_has_few_left(client):
    room_id, key = _site(client)
    _send(client, key)
    _decide(client, room_id, _booking_id(client, room_id), "confirm")
    card = _card("10~19시", staff=["원장 김미용", "디자이너 박하나"])
    assert _slot_state(A.days(card, key), _day(), "10:00") == "few"


def test_requested_only_is_few_and_declined_is_ignored(client):
    room_id, key = _site(client)
    _send(client, key, time="11:00")
    assert _slot_state(A.days(_card("10~19시"), key), _day(), "11:00") == "few"
    _decide(client, room_id, _booking_id(client, room_id), "decline")
    days = A.days(_card("10~19시"), key)
    assert _slot_state(days, _day(), "11:00") == "open"


def test_nights_blocks_stay_length(client):
    room_id, key = _site(client)
    assert _send(client, key, time="", service="온돌방", nights="2").status_code == 303
    _decide(client, room_id, _booking_id(client, room_id), "confirm")
    card = _card("매일 10~21시", data={"staff": [], "rooms": [{"name": "온돌방"}]})
    states = {d["date"]: d["state"] for d in A.nights(card, key)}
    assert states[_day(1)] == "full" and states[_day(2)] == "full"
    assert states[_day(3)] == "open"


# ── 명세 적용 ──

def _spec():
    return {"sections": [
        {"id": "booking", "type": "booking", "variant": "slots",
         "content": {"label": "예약", "days": [{"date": "2020-01-01"}], "days_example": True}},
        {"id": "stay", "type": "booking", "variant": "dates",
         "content": {"label": "예약", "days": [{"date": "2020-01-01"}], "days_example": True}},
        {"id": "intro", "type": "intro", "variant": "short", "content": {"body": "소개"}},
    ]}


def test_apply_rewrites_days_and_turns_off_example(client):
    _, key = _site(client)
    card = _card("10~19시")
    before = _spec()
    after = A.apply(before, card, key, today=datetime.date(2026, 9, 27))
    assert before["sections"][0]["content"]["days_example"] is True  # 원본 그대로
    slots = next(s for s in after["sections"] if s["variant"] == "slots")
    assert len(slots["content"]["days"]) == 5 and slots["content"]["days_example"] is False
    assert slots["content"]["days"][0]["date"] == "2026-09-28"
    dates = next(s for s in after["sections"] if s["variant"] == "dates")
    assert len(dates["content"]["days"]) == 14 and dates["content"]["days_example"] is False
    intro = next(s for s in after["sections"] if s["type"] == "intro")
    assert intro["content"] == {"body": "소개"}


def test_apply_without_booking_sections_keeps_spec(client):
    _, key = _site(client)
    spec = {"sections": [{"id": "intro", "type": "intro", "variant": "short", "content": {}}]}
    assert A.apply(spec, _card("10~19시"), key) == spec


# ── 공개본 다시 그리기 ──

def _publish_with_slots(client, monkeypatch, room_id, key, card):
    """청사진 경로(J5)가 들어오기 전이라 slots 칸을 덧붙여 공개한다."""
    from app.services import design_variants as DV
    real_pick = DV.pick

    def pick_with_slots(c, vid):
        v = real_pick(c, vid)
        spec = copy.deepcopy(v["spec"])
        spec["sections"].append(
            {"id": "booking", "type": "booking", "variant": "slots",
             "content": {"label": "예약", "note": "확인 뒤 연락드려요.", "staff": [],
                         "services": ["컷트"], "service_label": "시술",
                         "days": [], "days_example": True}})
        return {"id": v["id"], "name": v["name"], "summary": v["summary"], "spec": spec}

    monkeypatch.setattr(DV, "pick", pick_with_slots)
    from app.services import prd_engine as E
    from app.services import prd_schema as S
    with store.session_tx(store.read_room(room_id)["session_id"]) as s:
        E._put(s["prd"], "hours", "10~19시", S.FILLED)
        s["prd"]["published"] = "v1"
    card["published"] = "v1"
    design.publish_choice(key, card, "v1")


def test_decide_repaints_published_site(client, monkeypatch):
    room_id, key = _site(client)
    card = _card("10~19시")
    _publish_with_slots(client, monkeypatch, room_id, key, card)
    from app.config import settings
    html = (settings.generated_dir / key / "published" / "index.html").read_text(encoding="utf-8")
    assert 's-slot--full"' not in html
    meta = json.loads((settings.generated_dir / key / "published" / "meta.json").read_text(encoding="utf-8"))
    assert meta["variant"] == "v1" and meta["kst_date"] == bookings._today().isoformat()
    _send(client, key)
    _decide(client, room_id, _booking_id(client, room_id), "confirm")
    html = (settings.generated_dir / key / "published" / "index.html").read_text(encoding="utf-8")
    assert 's-slot--full"' in html and f"{_day()} 10:00" in html


def test_public_rerenders_when_date_changes(client, monkeypatch):
    room_id, key = _site(client)
    card = _card("10~19시")
    _publish_with_slots(client, monkeypatch, room_id, key, card)
    from app.config import settings
    meta_path = settings.generated_dir / key / "published" / "meta.json"
    meta_path.write_text(json.dumps({"kst_date": "2020-01-01", "variant": "v1"}), encoding="utf-8")
    with get_sessionmaker()() as db, db.begin():
        db.add(BookingRow(site_key=key, visit_date=bookings._today() + datetime.timedelta(days=1),
                          visit_time="11:00", service="컷트", party=1, phone="010-1234-5678",
                          status="confirmed"))
    r = client.get(f"/site/{key}/")
    assert r.status_code == 200
    assert json.loads(meta_path.read_text(encoding="utf-8"))["kst_date"] == bookings._today().isoformat()
    assert 's-slot--full"' in r.text


def test_public_skips_rerender_when_date_matches(client, monkeypatch):
    room_id, key = _site(client)
    card = _card("10~19시")
    _publish_with_slots(client, monkeypatch, room_id, key, card)
    from app.config import settings
    meta_path = settings.generated_dir / key / "published" / "meta.json"
    before = meta_path.read_text(encoding="utf-8")
    assert client.get(f"/site/{key}/").status_code == 200
    assert meta_path.read_text(encoding="utf-8") == before
