"""관리자 읽기 API (ADMIN_CONTRACT §5 1~4·6). DB를 쓰고 바깥 호출은 없다."""
import pytest
from sqlalchemy import select

from app import store
from app.config import settings
from app.db.models import AdminAuditRow, ChatTurnRow, UserRow
from app.db.session import get_sessionmaker
from app.services import auth as auth_svc
from app.services import prd_engine as E
from app.services import prd_schema as S

ADMIN, OWNER = "u_admin_t", "u_owner_t"
PHONE, TURN_PHONE = "010-1234-5678", "010-9999-8888"


@pytest.fixture
def users(client, monkeypatch):
    with get_sessionmaker()() as db, db.begin():
        db.add_all([UserRow(id=ADMIN, nickname="관리자"), UserRow(id=OWNER, nickname="사장님")])
    monkeypatch.setattr(settings, "admin_user_ids", f" {ADMIN} , someone-else ")


def _login(client, uid):
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(uid))


def _room(client, name, turns=0, english=False):
    """카드에 전화번호가 있는 방. turns만큼 요약 전 대화 턴을 쌓는다(엔진 판단에도 전화번호)."""
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": f"카페예요 {PHONE}"})
    sid = store.read_room(rid)["session_id"]
    with store.session_tx(sid) as s:
        card = s.get("prd") or E.new_card("cafe")
        E._put(card, "shop_name", name, S.FILLED, 1)
        E._put(card, "phone", PHONE, S.FILLED, 1)
        s["prd"] = card
    with get_sessionmaker()() as db, db.begin():
        for i in range(turns):
            db.add(ChatTurnRow(session_id=sid, room_id=rid, author="owner", user_text=f"말 {i} {TURN_PHONE}",
                               ai_text="Please tell me more" if english and i == 0 else "네, 알려 주세요.",
                               state_before="GATHERING", state_after="GATHERING",
                               meta={"extracted": [{"slot": "phone", "value": TURN_PHONE}], "next_slot": None}))
    return rid


def test_access_401_404_200(client, users):
    paths = ["/api/admin/rooms", "/api/admin/rooms/nope", "/api/admin/signals", "/api/admin/metrics", "/api/admin/keys"]
    for p in paths:
        assert client.get(p).status_code == 401, p
    _login(client, OWNER)
    for p in paths:
        assert client.get(p).status_code == 404, p  # 관리자 기능이 있다는 것 자체를 숨긴다
    _login(client, ADMIN)
    r = client.get("/api/admin/rooms")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    page = client.get("/admin")
    assert page.status_code == 200 and "관리자" in page.text


def test_rooms_search_page_and_flags(client, users):
    stuck = _room(client, "모퉁이 커피", turns=12, english=True)
    _room(client, "연남 헤어")
    _login(client, ADMIN)
    body = client.get("/api/admin/rooms", params={"q": "모퉁이"}).json()
    assert body["total"] == 1
    item = body["rooms"][0]
    assert item["room_id"] == stuck and item["shop_name"] == "모퉁이 커피"
    assert {"stuck", "english"} <= set(item["flags"]) and item["turns"] >= 12
    assert {"inquiries", "bookings", "owner_logged_in", "published", "site_key"} <= set(item)
    one = client.get("/api/admin/rooms", params={"limit": 1}).json()
    assert len(one["rooms"]) == 1 and one["total"] == 2
    assert client.get("/api/admin/rooms", params={"limit": 1, "offset": 1}).json()["rooms"][0]["room_id"] != one["rooms"][0]["room_id"]


def test_detail_masks_card_chat_turns_and_engine_trace(client, users):
    rid = _room(client, "모퉁이 커피", turns=3)
    _login(client, ADMIN)
    r = client.get(f"/api/admin/rooms/{rid}")
    assert r.status_code == 200
    assert PHONE not in r.text and TURN_PHONE not in r.text  # 카드·채팅·대화·엔진 판단·지표 어디에도 없다
    body = r.json()
    assert body["card"]["phone"]["value"] == "[전화]"
    assert body["turns"] and body["turns"][-1]["meta"]["extracted"][0]["value"] == "[전화]"
    assert any("[전화]" in m["text"] for m in body["messages"])
    assert body["metrics"]["n_turns"] >= 3
    assert client.get("/api/admin/rooms/nope").status_code == 404


def test_views_are_recorded(client, users):
    rid = _room(client, "모퉁이 커피")
    _login(client, ADMIN)
    client.get("/api/admin/rooms")
    client.get(f"/api/admin/rooms/{rid}")
    client.get("/api/admin/keys")
    with get_sessionmaker()() as db:
        rows = db.execute(select(AdminAuditRow.action, AdminAuditRow.target).where(AdminAuditRow.user_id == ADMIN)).all()
    assert {("view:rooms", None), ("view:room", rid), ("view:keys", None)} <= set(rows)


def test_signals_and_metrics(client, users):
    rid = _room(client, "모퉁이 커피", turns=12)
    _room(client, "조용한 가게", turns=1)
    _login(client, ADMIN)
    sessions = client.get("/api/admin/signals").json()["sessions"]
    assert [s["room_id"] for s in sessions] == [rid] and "stuck" in sessions[0]["flags"]
    m = client.get("/api/admin/metrics", params={"days": 7}).json()
    assert {"days", "design", "funnel", "rooms_created", "published", "owners_logged_in"} <= set(m)
    assert m["days"] == 7 and m["rooms_created"] >= 2
