"""베타 흐름: 견적 없이 승인→시안, 공개 답에 고치기 링크, 로그인 카드 열람 (DB 사용)."""
import uuid

from app import store
from app.config import settings
from app.db.models import UserRoomRow, UserRow
from app.db.session import get_sessionmaker
from app.services import auth

OWNER = "owner"


def _beta(monkeypatch):
    monkeypatch.setattr(settings, "quote_enabled", False)
    monkeypatch.setattr(settings, "publish_login_required", False)


def _post(client, room_id, member_id, message):
    r = client.post(f"/room/{room_id}/chat",
                    json={"member_id": member_id, "nickname": "사장님", "message": message})
    assert r.status_code == 200, r.text
    return r.json()


def _ai_replies(client, room_id):
    r = client.get(f"/room/{room_id}/messages", headers={"X-Member-Id": OWNER})
    assert r.status_code == 200, r.text
    msgs = [m for m in r.json()["messages"] if m.get("kind") == "ai_reply"]
    assert msgs, r.json()["messages"]
    return [m["text"] for m in msgs]


def _to_approval(client):
    room_id = client.post("/room").json()["room_id"]
    _post(client, room_id, OWNER, "")
    _post(client, room_id, OWNER, "카페 예약 서비스 만들어줘")
    _post(client, room_id, OWNER, "나머지는 알아서, 시안 먼저 볼게요")
    session_id = store.read_room(room_id)["session_id"]
    assert (store.read_session(session_id) or {})["state"] == "AWAIT_APPROVAL"
    return room_id


def _state(room_id):
    session_id = store.read_room(room_id)["session_id"]
    return (store.read_session(session_id) or {})["state"]


def test_approve_goes_straight_to_design(client, monkeypatch):
    _beta(monkeypatch)
    room_id = _to_approval(client)
    _post(client, room_id, OWNER, "승인")
    assert _state(room_id) in ("GENERATING", "DONE")
    design_replies = [t for t in _ai_replies(client, room_id) if "/design/" in t]
    assert design_replies, "승인 뒤 시안 답이 없다"
    assert "시안" in design_replies[0]
    assert "견적" not in design_replies[0]


def test_summary_ask_mentions_design_not_quote(client, monkeypatch):
    _beta(monkeypatch)
    room_id = _to_approval(client)
    reply = _ai_replies(client, room_id)[-1]
    assert "시안을 만들어 볼까요" in reply
    assert "견적" not in reply


def test_publish_reply_has_editor_link(client, monkeypatch):
    _beta(monkeypatch)
    room_id = _to_approval(client)
    _post(client, room_id, OWNER, "승인")
    client.get(f"/room/{room_id}/messages", headers={"X-Member-Id": OWNER})  # 폴링 → DONE
    _post(client, room_id, OWNER, "2안으로 할게요")
    _post(client, room_id, OWNER, "그대로 공개")
    reply = _ai_replies(client, room_id)[-1]
    assert reply.startswith("사이트를 열었어요")
    assert f"/editor?room={room_id}" in reply


def test_card_api_with_login_no_member_header(client, monkeypatch):
    _beta(monkeypatch)
    room_id = client.post("/room").json()["room_id"]
    _post(client, room_id, OWNER, "")
    user_id = f"u-{uuid.uuid4().hex[:8]}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=user_id, nickname="사장님"))
        db.flush()
        db.add(UserRoomRow(user_id=user_id, room_id=room_id, member_id=OWNER))
    client.cookies.set(auth.SESSION_COOKIE, auth.create_session(user_id))
    r = client.get(f"/api/rooms/{room_id}/card")
    assert r.status_code == 200, r.text
    assert r.json()["can_edit"] is True
