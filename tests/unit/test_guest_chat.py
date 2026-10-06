"""손님 ↔ 사장님 채팅 (GUEST_CHAT_CONTRACT §5의 1~5)."""
import datetime
import secrets

import pytest
from sqlalchemy import select, update

from app import store
from app.api import chat_agent as chat_api
from app.db.models import GuestChatMessageRow, GuestChatThreadRow, UserRoomRow, UserRow
from app.db.session import get_sessionmaker
from app.services import auth as auth_svc
from app.services import guest_chat, notify, shops

ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    chat_api._hits.clear()
    sent = []
    monkeypatch.setattr(notify, "owner_kakao", lambda room_id, text: sent.append(text))
    return sent


def _published_site(client, name="모퉁이 커피"):
    """공개된 가게(shops 행) + 로그인한 주인. 예약 봇은 없다."""
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    shops.ensure(key, name, room_id)
    uid = f"u-{secrets.token_hex(4)}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=uid, nickname="사장님"))
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRoomRow(user_id=uid, room_id=room_id, member_id="owner"))
    return room_id, key, uid


def _login(client, uid):
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(uid))


class Guest:
    """손님 브라우저 하나 = 채팅 쿠키 하나 (서버 쿠키는 Secure라 직접 들고 보낸다)."""

    def __init__(self, client, key):
        self.client, self.key, self.token = client, key, None

    def _headers(self):
        h = dict(ORIGIN)
        if self.token:
            h["Cookie"] = f"{chat_api.cookie_name(self.key)}={self.token}"
        return h

    def say(self, **body):
        r = self.client.post(f"/api/chat/{self.key}", json=body, headers=self._headers())
        assert r.status_code == 200, r.text
        self.token = r.cookies.get(chat_api.cookie_name(self.key)) or self.token
        return r.json()

    def poll(self, after=0):
        r = self.client.get(f"/api/chat/{self.key}/messages", params={"after": after}, headers=self._headers())
        assert r.status_code == 200, r.text
        return r.json()


def _thread(key):
    with get_sessionmaker()() as db:
        return db.scalar(select(GuestChatThreadRow).where(GuestChatThreadRow.shop_id == key))


def test_1_unknown_question_goes_to_owner_once(client, _reset):
    room_id, key, _ = _published_site(client)
    g = Guest(client, key)
    first = g.say(text="주차 돼요?")
    assert "사장님께 여쭤볼게요" in first["reply"] and first.get("mode") == "owner"
    assert {"label": "사장님께 직접 물어보기", "action": "owner"} in first["buttons"]
    assert not any(b["action"] == "book" for b in first["buttons"])  # 예약 봇이 없으면 예약 단추 없음
    assert _thread(key).status == "owner"
    msgs = client.get(f"/room/{room_id}/messages", headers={"X-Member-Id": "owner"}).json()["messages"]
    assert any(m["kind"] == "inquiry" and "주차" in m["text"] for m in msgs)  # 사장님 방에는 원문
    assert len(_reset) == 1 and "주차" not in _reset[0]  # 카톡에는 원문 없이
    second = g.say(text="자리 넓어요?")
    assert "사장님께 전했어요" in second["reply"]
    third = g.say(text="창가 자리요")
    assert third["reply"] == ""  # 연달아 보내면 답 없음
    assert len(_reset) == 1  # 10분 안에는 다시 알리지 않는다
    texts = [m["text"] for m in g.poll()["messages"] if m["sender"] == "guest"]
    assert texts == ["주차 돼요?", "자리 넓어요?", "창가 자리요"]


def test_2_owner_action_skips_ai(client):
    _, key, _ = _published_site(client)
    g = Guest(client, key)
    r = g.say(action="owner")
    assert "사장님이 확인하면" in r["reply"] and r.get("mode") == "owner"
    r = g.say(text="전화번호 알려 주세요")  # AI라면 가게 정보로 답했을 질문
    assert "사장님께 전했어요" in r["reply"]
    assert [m["sender"] for m in g.poll()["messages"]] == ["guest"]  # AI가 답하지 않았다


def test_2_booking_question_without_bot_says_call(client):
    _, key, _ = _published_site(client)
    r = Guest(client, key).say(text="내일 예약돼요?")
    assert "채팅 예약은 아직 받지 않아요" in r["reply"]


def test_3_owner_list_view_reply_block(client):
    _, key, uid = _published_site(client)
    g = Guest(client, key)
    g.say(text="반려견 동반 돼요?")
    _login(client, uid)
    chats = client.get(f"/api/owner/shops/{key}/chats").json()["chats"]
    assert chats[0]["status"] == "owner" and chats[0]["owner_unread"] == 1
    tid = chats[0]["id"]
    view = client.get(f"/api/owner/shops/{key}/chats/{tid}").json()
    assert view["messages"][0]["text"] == "반려견 동반 돼요?"
    assert client.get(f"/api/owner/shops/{key}/chats").json()["chats"][0]["owner_unread"] == 0
    assert client.post(f"/api/owner/shops/{key}/chats/{tid}", json={"text": "네 소형견 가능해요"}).status_code == 403  # 출처 확인
    sent = client.post(f"/api/owner/shops/{key}/chats/{tid}", json={"text": "네 소형견 가능해요"}, headers=ORIGIN)
    assert sent.status_code == 200 and sent.json()["sender"] == "owner"
    last = g.poll()["messages"][-1]
    assert last["sender"] == "owner" and last["text"] == "네 소형견 가능해요"
    assert client.post(f"/api/owner/shops/{key}/chats/{tid}/block", headers=ORIGIN).json()["status"] == "blocked"
    n = len(g.poll()["messages"])
    r = g.say(text="감사합니다")
    assert "보낼 수 없어요" in r["reply"] and len(g.poll()["messages"]) == n


def test_3_other_shop_owner_cannot_see(client):
    _, key, _ = _published_site(client)
    Guest(client, key).say(text="주차 돼요?")
    _, other_key, other_uid = _published_site(client, "다른 가게")
    _login(client, other_uid)
    tid = _thread(key).id
    assert client.get(f"/api/owner/shops/{key}/chats").status_code == 404
    assert client.get(f"/api/owner/shops/{other_key}/chats/{tid}").status_code == 404
    assert client.get(f"/api/owner/shops/{key}/chats", cookies={}).status_code in (401, 404)


def test_4_poll_needs_own_cookie(client):
    _, key, _ = _published_site(client)
    g = Guest(client, key)
    g.say(text="주차 돼요?")
    assert Guest(client, key).poll() == {"messages": [], "status": "ai"}  # 쿠키 없음
    stranger = Guest(client, key)
    stranger.token = "someone-else"
    assert stranger.poll()["messages"] == []


def test_5_purge_and_turn_off(client):
    _, key, uid = _published_site(client)
    Guest(client, key).say(text="주차 돼요?")
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(GuestChatThreadRow).values(
            last_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=31)))
    assert guest_chat.purge() >= 1
    with get_sessionmaker()() as db:
        assert db.scalar(select(GuestChatMessageRow.id).limit(1)) is None or _thread(key) is None
    _login(client, uid)
    r = client.post(f"/api/owner/shops/{key}/chat-settings", json={"guest_chat_on": False}, headers=ORIGIN)
    assert r.status_code == 200 and r.json() == {"guest_chat_on": False}
    # 상태 줄용 값까지 같이 돌려준다 (PRICING_AND_CHAT_1006 C-3): 받기·공개·손님 링크
    state = client.get(f"/api/owner/shops/{key}/chat-settings").json()
    assert state["guest_chat_on"] is False and state["published"] is True
    assert state["link"] == "" and state["preview_url"] == f"/chat/{key}"  # 꺼지면 링크를 만들지 않는다
    # 요금제 포함량과 이번 달 AI 답 사용량도 같이 (D61 plans.py, C-4)
    assert state["plan"] == "free" and state["plan_name"] == "무료"
    assert state["ai_total"] == 300 and 0 <= state["ai_left"] <= 300  # 세는 것은 test_usage_quota에서 본다
    assert "채팅 예약을 받지 않아요" in Guest(client, key).say(text="주차 돼요?")["reply"]


def test_unpublished_site_keeps_old_answer(client):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    assert "채팅 예약을 받지 않아요" in Guest(client, key).say(text="주차 돼요?")["reply"]
    assert _thread(key) is None


def test_publish_creates_shop_row_so_chat_opens(client, monkeypatch):
    """공개하자마자 가게 행이 생겨 손님 채팅이 열린다 (없는 함수를 부르던 공개 경로 고침)."""
    from app.config import settings
    from app.db.models import ShopRow
    monkeypatch.setattr(settings, "publish_login_required", False)
    from app.api import inquiries as inquiries_api
    with inquiries_api._lock:
        inquiries_api._hits.clear()
    body = client.post("/api/start", json={"template": "cafe"}).json()
    rid, headers = body["room_id"], {"X-Member-Id": body["member_id"]}
    client.put(f"/api/rooms/{rid}/card", json={"fields": {"shop_name": "모퉁이 커피"}}, headers=headers)
    r = client.post(f"/api/rooms/{rid}/publish", json={"force": True}, headers=headers)
    assert r.status_code == 200 and r.json().get("ok"), r.text
    key = store.read_session(store.read_room(rid)["session_id"])["requirement_id"]
    with get_sessionmaker()() as db:
        row = db.get(ShopRow, key)
    assert row is not None and row.name == "모퉁이 커피"
    assert guest_chat.enabled(key) is True
    assert "여쭤볼게요" in Guest(client, key).say(text="강아지 데려가도 돼요?")["reply"]
