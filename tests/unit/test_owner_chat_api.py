"""사장님 API·손님 채팅 (BOOKING_BOT_IMPL_PLAN W5, 완료 기준 §4)."""
import datetime
import secrets

import pytest

from app import store
from app.api import chat_agent as chat_api
from app.db.models import UserRoomRow, UserRow
from app.db.session import get_sessionmaker
from app.services import auth as auth_svc
from app.services import booking_engine, chat_agent
from app.services.slots import KST

ORIGIN = {"Origin": "http://testserver"}
SALON_TALK = ["매일 10시~8시", "30분", "컷, 펌", "1시간", "두 시간 반", "원장, 실장", "1시간 전", "제가 확인할게요",
              "15분", "없어요", "없어요", "없어요", "없어요", "따로 없어요", "없어요", "3시간 전"]


@pytest.fixture(autouse=True)
def _reset_limits():
    chat_api._hits.clear()


def _owned_site(client):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    uid = f"u-{secrets.token_hex(4)}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=uid, nickname="사장님"))
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRoomRow(user_id=uid, room_id=room_id, member_id="owner"))
    return room_id, key, uid


def _login(client, uid):
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(uid))


def _bot(client, key, **body):
    r = client.post(f"/api/owner/shops/{key}/bot", json=body, headers=ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()


def _make_bot(client, key):
    _bot(client, key, mode="slot")
    out = None
    for text in SALON_TALK:
        out = _bot(client, key, text=text)
    assert out["ready"] is True, out["reply"]
    return _bot(client, key, action="activate")


_TOKENS: dict = {}


def _chat(client, key, **body):
    """이 브라우저 = 채팅 토큰 하나. 서버 쿠키는 Secure라 http 테스트에서 직접 들고 보낸다."""
    name = chat_api.cookie_name(key)
    headers = dict(ORIGIN)
    if key in _TOKENS:
        headers["Cookie"] = f"{name}={_TOKENS[key]}"
    r = client.post(f"/api/chat/{key}", json=body, headers=headers)
    assert r.status_code == 200, r.text
    _TOKENS[key] = r.cookies.get(name) or _TOKENS.get(key)
    return r.json()


def _press(reply, prefix):
    return next(b["action"] for b in reply["buttons"] if b["action"].startswith(prefix))


def _later_date(reply, days=2):
    """변경 마감(24시간)에 걸리지 않게 이틀 뒤 이후 날짜 버튼."""
    edge = datetime.datetime.now(KST).date() + datetime.timedelta(days=days)
    return next(b["action"] for b in reply["buttons"]
                if b["action"].startswith("date:") and datetime.date.fromisoformat(b["action"][5:]) >= edge)


# ── 권한 ──

def test_owner_api_requires_login_and_membership(client):
    _, key, uid = _owned_site(client)
    assert client.get("/api/owner/shops").status_code == 401
    _login(client, uid)
    shops = client.get("/api/owner/shops").json()["shops"]
    assert [s["site_key"] for s in shops] == [key] and shops[0]["bot_active"] is False
    other = f"u-{secrets.token_hex(4)}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=other, nickname="남"))
    _login(client, other)
    assert client.get(f"/api/owner/shops/{key}/bookings").status_code == 404
    assert client.post(f"/api/owner/shops/{key}/bot", json={"mode": "slot"}, headers=ORIGIN).status_code == 404


def test_owner_writes_need_origin(client):
    _, key, uid = _owned_site(client)
    _login(client, uid)
    assert client.post(f"/api/owner/shops/{key}/bot", json={"mode": "slot"}).status_code == 403


# ── 완료 기준 시나리오 ──

def test_end_to_end_botmaker_chat_owner_change_cancel(client):
    room_id, key, uid = _owned_site(client)
    _login(client, uid)
    activated = _make_bot(client, key)
    assert activated["activated"]["version"] == 1
    assert client.get("/api/owner/shops").json()["shops"][0]["bot_active"] is True

    # 손님: 채팅으로 예약
    hello = _chat(client, key)
    assert [b["action"] for b in hello["buttons"]][:2] == ["book", "mine"]
    r = _chat(client, key, text="펌 예약하고 싶어요")
    assert "선생님" in r["reply"]
    r = _chat(client, key, action="staff:")                      # 상관없음
    r = _chat(client, key, action=_later_date(r))
    times = [b["label"] for b in r["buttons"] if b["action"].startswith("time:")]
    offered = set(times)
    r = _chat(client, key, action=_press(r, "time:"))
    assert "10분 동안 잡아" in r["reply"]
    r = _chat(client, key, text="김민지 010-1234-5678")
    assert "010-****-5678" in r["reply"]
    r = _chat(client, key, action="confirm:")
    booking = r["booking"]
    assert booking["status"] == "requested" and booking["time"] in offered and booking["service"].startswith("펌 · ")

    # 사장님: 다른 기기(계정)로 확정
    listed = client.get(f"/api/owner/shops/{key}/bookings", params={"frm": booking["date"], "to": booking["date"]}).json()
    assert [b["id"] for b in listed["bookings"]] == [booking["id"]]
    ok = client.post(f"/api/owner/shops/{key}/bookings/{booking['id']}/confirm", headers=ORIGIN).json()
    assert ok["booking"]["status"] == "confirmed"

    # 손님: 내 예약 → 변경
    r = _chat(client, key, action="mine")
    assert "확정" in r["reply"]
    r = _chat(client, key, action=f"change:{booking['id']}")
    r = _chat(client, key, action=_later_date(r))
    new_time = next(b for b in r["buttons"] if b["action"].startswith("time:") and b["label"] != booking["time"])
    r = _chat(client, key, action=new_time["action"])
    assert "바꿔서 다시 신청" in r["reply"]
    mine = booking_engine.my_bookings(key, chat_agent.token_hash(_TOKENS[key]))
    assert len(mine) == 1 and mine[0]["time"] == new_time["label"] and mine[0]["id"] != booking["id"]

    # 손님: 취소
    r = _chat(client, key, action=f"cancel:{mine[0]['id']}")
    r = _chat(client, key, action=f"cancel_ok:{mine[0]['id']}")
    assert "취소했어요" in r["reply"]
    assert booking_engine.my_bookings(key, chat_agent.token_hash(_TOKENS[key])) == []

    msgs = client.get(f"/room/{room_id}/messages", headers={"X-Member-Id": "owner"}).json()["messages"]
    texts = [m["text"] for m in msgs if m["kind"].startswith("booking")]
    assert any("새 예약 신청" in t for t in texts) and any("바꾸셨어요" in t for t in texts) \
        and any("취소했어요" in t for t in texts)


def test_other_browser_cannot_see_or_cancel(client):
    _, key, uid = _owned_site(client)
    _login(client, uid)
    _make_bot(client, key)
    day = datetime.datetime.now(KST).date() + datetime.timedelta(days=2)
    b = booking_engine.book_now(key, day, "14:00", service="컷", phone="010-1111-2222", token_hash="someone-else")
    r = _chat(client, key, action="mine")
    assert "이 기기로 한 예약이 없어요" in r["reply"]
    r = _chat(client, key, action=f"cancel_ok:{b['id']}")
    assert "찾을 수 없어요" in r["reply"]


def test_chat_without_bot_says_call(client):
    _, key, _ = _owned_site(client)
    r = _chat(client, key, text="예약돼요?")
    assert "채팅 예약을 받지 않아요" in r["reply"]


def test_unknown_question_goes_to_owner(client):
    room_id, key, uid = _owned_site(client)
    _login(client, uid)
    _make_bot(client, key)
    r = _chat(client, key, text="강아지 데려가도 돼요?")
    assert "사장님께 여쭤볼게요" in r["reply"]
    msgs = client.get(f"/room/{room_id}/messages", headers={"X-Member-Id": "owner"}).json()["messages"]
    assert any(m["kind"] == "inquiry" and "강아지" in m["text"] for m in msgs)


def test_owner_phone_booking_and_closure(client):
    _, key, uid = _owned_site(client)
    _login(client, uid)
    _make_bot(client, key)
    day = (datetime.datetime.now(KST).date() + datetime.timedelta(days=2)).isoformat()
    r = client.post(f"/api/owner/shops/{key}/bookings", headers=ORIGIN,
                    json={"date": day, "time": "11:00", "service": "컷", "staff": "원장", "phone": "010-3333-4444"})
    assert r.status_code == 200 and r.json()["booking"]["status"] == "confirmed"
    again = client.post(f"/api/owner/shops/{key}/bookings", headers=ORIGIN,
                        json={"date": day, "time": "11:30", "service": "컷", "staff": "원장", "phone": "010-5555-6666"})
    assert again.status_code == 409
    c = client.post(f"/api/owner/shops/{key}/closures", headers=ORIGIN,
                    json={"start_at": f"{day}T10:00:00", "end_at": f"{day}T13:00:00", "reason": "병원"}).json()
    assert [x["time"] for x in c["conflicts"]] == ["11:00"]
    assert len(client.get(f"/api/owner/shops/{key}/closures").json()["closures"]) == 1
    assert client.delete(f"/api/owner/shops/{key}/closures/{c['id']}", headers=ORIGIN).status_code == 200


def test_rate_limit(client):
    _, key, _ = _owned_site(client)
    for _ in range(chat_api.RATE_LIMIT):
        client.post(f"/api/chat/{key}", json={}, headers=ORIGIN)
    assert client.post(f"/api/chat/{key}", json={}, headers=ORIGIN).status_code == 429


def test_parsers():
    today = datetime.date(2026, 9, 29)  # 화
    assert chat_agent.parse_date("내일", today) == datetime.date(2026, 9, 30)
    assert chat_agent.parse_date("10/3", today) == datetime.date(2026, 10, 3)
    assert chat_agent.parse_date("토요일", today) == datetime.date(2026, 10, 3)
    assert chat_agent.parse_time("오후 3시 반") == "15:30" and chat_agent.parse_time("3시") == "15:00"
    assert chat_agent.parse_time("11시") == "11:00"
    assert chat_agent.parse_party("4명이요") == 4 and chat_agent.parse_party("둘이서") == 2
    assert chat_agent.intent_of("예약 취소할게요") == "cancel" and chat_agent.intent_of("주차 돼요?") == "ask"
    assert chat_agent.intent_of("내일 3시 돼요?") == "book"


def test_published_booking_section_links_to_chat(client, monkeypatch):
    from app.config import settings
    from app.services import availability, site_render
    _, key, uid = _owned_site(client)
    spec = {"sections": [{"type": "booking", "variant": "form", "content": {}}]}
    assert "chat_url" not in availability.apply(spec, {}, key)["sections"][0]["content"]   # 봇 꺼짐
    _login(client, uid)
    _make_bot(client, key)
    monkeypatch.setattr(settings, "public_base_url", "https://app.example.com")
    content = availability.apply(spec, {}, key)["sections"][0]["content"]
    assert content["chat_url"] == f"https://app.example.com/chat/{key}"
    assert site_render._chat_url(content, key) == content["chat_url"]
    assert site_render._chat_url({"chat_url": "https://evil.example/x"}, key) == ""
    monkeypatch.setattr(settings, "public_base_url", None)
    monkeypatch.setattr(settings, "preview_host", "preview.example.com")
    assert "chat_url" not in availability.apply(spec, {}, key)["sections"][0]["content"]


def test_pages_served(client):
    assert "예약 관리" in client.get("/owner").text
    assert "채팅 예약" in client.get("/chat/abc123").text


def test_thread_purge(client):
    from app.services import chat_agent as ca
    _, key, uid = _owned_site(client)
    _login(client, uid)
    _make_bot(client, key)
    _chat(client, key)
    assert ca.purge(datetime.datetime.now(KST) + datetime.timedelta(days=8)) == 1
