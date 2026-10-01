"""손님 채팅 즉시 반영 (GUEST_CHAT_CONTRACT §7, SSE). 연결은 짧게(0.4초) 열고 닫는다."""
import json
import secrets

import pytest

from app import store
from app.api import chat_agent as chat_api
from app.db.models import UserRoomRow, UserRow
from app.db.session import get_sessionmaker
from app.services import auth as auth_svc
from app.services import guest_chat, notify, shops, sse

ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    chat_api._hits.clear()
    monkeypatch.setattr(notify, "owner_kakao", lambda room_id, text: None)
    monkeypatch.setattr(sse, "MAX_SEC", 0.4)
    monkeypatch.setattr(sse, "POLL_SEC", 0.02)


def _site(client, name="모퉁이 커피"):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    shops.ensure(key, name, room_id)
    uid = f"u-{secrets.token_hex(4)}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=uid, nickname="사장님"))
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRoomRow(user_id=uid, room_id=room_id, member_id="owner"))
    return key, uid


def _guest_says(client, key, text, token=None):
    headers = dict(ORIGIN)
    if token:
        headers["Cookie"] = f"{chat_api.cookie_name(key)}={token}"
    r = client.post(f"/api/chat/{key}", json={"text": text}, headers=headers)
    assert r.status_code == 200, r.text
    return r.cookies.get(chat_api.cookie_name(key)) or token


def _events(client, url, headers=None):
    """SSE를 끝까지 읽어 [(이름, id, 데이터)]로. 첫 줄은 retry여야 한다."""
    out, name, eid, first = [], None, None, None
    with client.stream("GET", url, headers=headers or {}) as r:
        assert r.status_code == 200, r.read()
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if first is None:
                first = line
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("id: "):
                eid = int(line[4:])
            elif line.startswith("data: "):
                out.append((name, eid, json.loads(line[6:])))
                name, eid = None, None
    assert first == f"retry: {sse.RETRY_MS}"
    return out


def _owner_thread(client, key, uid):
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(uid))
    tid = client.get(f"/api/owner/shops/{key}/chats").json()["chats"][0]["id"]
    return tid


def test_guest_stream_sends_owner_reply_and_resumes(client):
    key, uid = _site(client)
    token = _guest_says(client, key, "반려견 동반 돼요?")  # 모르는 질문 → 사장님께
    tid = _owner_thread(client, key, uid)
    reply = client.post(f"/api/owner/shops/{key}/chats/{tid}", json={"text": "네 소형견 가능해요"}, headers=ORIGIN).json()
    client.cookies.clear()
    cookie = {"Cookie": f"{chat_api.cookie_name(key)}={token}"}
    events = _events(client, f"/api/chat/{key}/stream?after=0", cookie)
    owner = [d for n, _, d in events if n == "message" and d["sender"] == "owner"]
    assert owner and owner[-1]["text"] == "네 소형견 가능해요"
    assert ("status", None, {"status": "owner"}) in events
    # 다시 붙을 때(Last-Event-ID) 본 글은 다시 오지 않는다
    again = _events(client, f"/api/chat/{key}/stream", {**cookie, "Last-Event-ID": str(reply["id"])})
    assert [e for e in again if e[0] == "message"] == []


def test_guest_stream_ends_when_blocked_and_needs_own_cookie(client):
    key, uid = _site(client)
    token = _guest_says(client, key, "주차 돼요?")
    tid = _owner_thread(client, key, uid)
    client.post(f"/api/owner/shops/{key}/chats/{tid}/block", headers=ORIGIN)
    client.cookies.clear()
    events = _events(client, f"/api/chat/{key}/stream", {"Cookie": f"{chat_api.cookie_name(key)}={token}"})
    assert events[-1] == ("status", None, {"status": "blocked"})
    stranger = _events(client, f"/api/chat/{key}/stream", {"Cookie": f"{chat_api.cookie_name(key)}=someone-else"})
    assert stranger == [("status", None, {"status": "ai"})]  # 남의 대화는 안 보인다


def test_owner_stream_auth_and_changes(client):
    key, uid = _site(client)
    assert client.get(f"/api/owner/shops/{key}/chat-stream").status_code == 401
    _, other_uid = _site(client, "다른 가게")
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(other_uid))
    assert client.get(f"/api/owner/shops/{key}/chat-stream").status_code == 404
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(uid))
    first = _events(client, f"/api/owner/shops/{key}/chat-stream")
    assert [n for n, _, _ in first] == ["changed"]  # 처음 한 번, 바뀐 게 없으면 더 없음
    before = guest_chat.shop_signature(key)
    _guest_says(client, key, "포장 돼요?")
    assert guest_chat.shop_signature(key) != before
    second = _events(client, f"/api/owner/shops/{key}/chat-stream")
    assert second[0][2]["sig"] == guest_chat.shop_signature(key) != first[0][2]["sig"]
