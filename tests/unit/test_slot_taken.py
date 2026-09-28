"""마감 검사 slot_taken (CUSTOMER_PLAN §1.3, DB 사용)."""
import datetime

from app import store
from app.db.models import BookingRow
from app.db.session import get_sessionmaker
from app.services import availability as A
from app.services import bookings


def _site(client):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat",
                json={"member_id": "owner", "nickname": "사장님", "message": "동네 미용실이에요. 컷트해요"})
    session = store.read_session(store.read_room(room_id)["session_id"])
    return room_id, session["requirement_id"]


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


def _keep(room_id, card):
    """_card_for_site가 읽는 세션 카드로 저장한다."""
    with store.session_tx(store.read_room(room_id)["session_id"]) as s:
        s["prd"] = card


def _day(offset=1):
    return bookings._today() + datetime.timedelta(days=offset)


def _add(key, visit, time="", service=None, status="confirmed"):
    with get_sessionmaker()() as db, db.begin():
        db.add(BookingRow(site_key=key, visit_date=visit, visit_time=time, service=service, party=1,
                          phone="010-1234-5678", status=status))


def _taken(key, visit, time="", service=None):
    with get_sessionmaker()() as db:
        return A.slot_taken(db, key, visit, time, service)


def test_time_based_full_and_other_time_open(client):
    room_id, key = _site(client)
    _keep(room_id, _card("10~19시"))
    day = _day()
    _add(key, day, "14:00", "컷트")
    assert _taken(key, day, "14:00", "컷트") is True
    assert _taken(key, day, "15:00", "컷트") is False


def test_requested_only_is_not_taken(client):
    room_id, key = _site(client)
    _keep(room_id, _card("10~19시"))
    day = _day()
    _add(key, day, "14:00", "컷트", status="requested")
    assert _taken(key, day, "14:00", "컷트") is False


def test_capacity_two_needs_two_confirmed(client):
    room_id, key = _site(client)
    _keep(room_id, _card("10~19시", staff=["원장 김미용", "디자이너 박하나"]))
    day = _day()
    _add(key, day, "14:00", "컷트")
    assert _taken(key, day, "14:00", "컷트") is False
    _add(key, day, "14:00", "염색")
    assert _taken(key, day, "14:00", "컷트") is True
    assert _taken(key, day, "15:00", "컷트") is False


def test_pension_two_rooms_cover(client):
    room_id, key = _site(client)
    _keep(room_id, _card("매일 10~21시", data={"staff": [], "rooms": [{"name": "101호"}, {"name": "102호"}]}))
    day, nxt, over = _day(1), _day(2), _day(3)
    _add(key, day, "", "101호 · 2박")
    assert _taken(key, day, "", "101호 · 1박") is False
    assert _taken(key, nxt, "", "102호 · 1박") is False
    _add(key, nxt, "", "102호 · 2박")
    assert _taken(key, nxt, "", "102호 · 1박") is True
    assert _taken(key, day, "", "101호 · 1박") is False
    assert _taken(key, over, "", "102호 · 1박") is False


def test_declined_never_counts(client):
    room_id, key = _site(client)
    _keep(room_id, _card("10~19시", staff=["원장 김미용", "디자이너 박하나"]))
    day = _day()
    _add(key, day, "14:00", "컷트", status="declined")
    assert _taken(key, day, "14:00", "컷트") is False
    _add(key, day, "14:00", "컷트")
    assert _taken(key, day, "14:00", "컷트") is False


def test_declined_stay_never_counts(client):
    room_id, key = _site(client)
    _keep(room_id, _card("매일 10~21시", data={"staff": [], "rooms": [{"name": "온돌방"}]}))
    day, nxt = _day(1), _day(2)
    _add(key, day, "", "온돌방 · 2박", status="declined")
    assert _taken(key, day, "", "온돌방 · 1박") is False
    assert _taken(key, nxt, "", "온돌방 · 1박") is False


def test_unknown_site_behaves_as_capacity_one(client):
    key = "없는가게"
    day = _day()
    assert _taken(key, day, "14:00", "컷트") is False
    _add(key, day, "14:00", "컷트")
    assert _taken(key, day, "14:00", "컷트") is True
    assert _taken(key, day, "15:00", "컷트") is False
