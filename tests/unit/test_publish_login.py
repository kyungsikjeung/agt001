"""처음 공개는 방장 로그인 필수 (OWNER_SETTINGS_PLAN §1.1, DB 사용)."""
import uuid

from app import store
from app.config import settings
from app.db.models import UserRoomRow, UserRow
from app.db.session import get_sessionmaker
from app.services import rooms

OWNER = "owner"


def _post(client, room_id, member_id, message):
    r = client.post(f"/room/{room_id}/chat",
                    json={"member_id": member_id, "nickname": "사장님", "message": message})
    assert r.status_code == 200, r.text
    return r.json()


def _last_reply(client, room_id):
    r = client.get(f"/room/{room_id}/messages", headers={"X-Member-Id": OWNER})
    assert r.status_code == 200, r.text
    msgs = [m for m in r.json()["messages"] if m.get("kind") == "ai_reply"]
    assert msgs, r.json()["messages"]
    return msgs[-1]["text"]


def _drive_to_pickable(client):
    """방을 만들고 시안 고르기까지 몰아간다. 방장은 member_id 'owner'."""
    room_id = client.post("/room").json()["room_id"]
    _post(client, room_id, OWNER, "")
    _post(client, room_id, OWNER, "카페 예약 서비스 만들어줘")
    _post(client, room_id, OWNER, "나머지는 알아서, 시안 먼저 볼게요")
    _post(client, room_id, OWNER, "승인")  # 1명이라 전원 동의로 QUOTED
    _post(client, room_id, OWNER, "진행")  # GENERATING
    client.get(f"/room/{room_id}/messages", headers={"X-Member-Id": OWNER})  # 폴링 → DONE
    _post(client, room_id, OWNER, "2안으로 할게요")
    return room_id


def _published(room_id):
    session_id = store.read_room(room_id)["session_id"]
    return (store.read_session(session_id) or {}).get("prd", {}).get("published")


def _claim(user_id, room_id, member_id):
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=user_id, nickname="사장님"))
        db.flush()
        db.add(UserRoomRow(user_id=user_id, room_id=room_id, member_id=member_id))


def test_first_publish_needs_owner_login(client, monkeypatch):
    monkeypatch.setattr(settings, "publish_login_required", True)
    room_id = _drive_to_pickable(client)
    assert not rooms.owner_claimed(room_id)

    _post(client, room_id, OWNER, "그대로 공개")
    reply = _last_reply(client, room_id)
    assert "로그인" in reply
    assert f"/auth/kakao/start?next=%2Froom.html%3Froom%3D{room_id}" in reply
    assert f"/auth/google/start?next=%2Froom.html%3Froom%3D{room_id}" in reply
    assert _published(room_id) is None


def test_claimed_owner_can_publish(client, monkeypatch):
    monkeypatch.setattr(settings, "publish_login_required", True)
    room_id = _drive_to_pickable(client)
    _claim(f"u-{uuid.uuid4().hex[:8]}", room_id, OWNER)
    assert rooms.owner_claimed(room_id)

    _post(client, room_id, OWNER, "그대로 공개")
    assert "사이트를 열었어요" in _last_reply(client, room_id)
    assert _published(room_id) == "v2"


def test_non_owner_claim_does_not_count(client, monkeypatch):
    monkeypatch.setattr(settings, "publish_login_required", True)
    room_id = _drive_to_pickable(client)
    _claim(f"u-{uuid.uuid4().hex[:8]}", room_id, "someone-else")
    assert not rooms.owner_claimed(room_id)

    _post(client, room_id, OWNER, "그대로 공개")
    assert "로그인" in _last_reply(client, room_id)
    assert _published(room_id) is None


def test_flag_off_publishes_without_login(client, monkeypatch):
    monkeypatch.setattr(settings, "publish_login_required", False)
    room_id = _drive_to_pickable(client)

    _post(client, room_id, OWNER, "그대로 공개")
    assert "사이트를 열었어요" in _last_reply(client, room_id)
    assert _published(room_id) == "v2"
