"""채팅방 기능 (contracts/ROOM_FEATURES_API.md §1~§3·§7): 방장 넘기기·나가기·초대 링크·사전 경고."""
import datetime

import pytest

from app.config import settings
from app.services import rooms


def _room(client):
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    return rid


def _join(client, rid, member, invite=None):
    body = {"member_id": member, "nickname": member, "message": ""}
    if invite:
        body["invite"] = invite
    return client.post(f"/room/{rid}/chat", json=body)


def _msgs(client, rid, member="owner"):
    return client.get(f"/room/{rid}/messages", headers={"X-Member-Id": member}).json()


def _h(member):
    return {"X-Member-Id": member}


def test_members_show_owner_and_me(client):
    rid = _room(client)
    _join(client, rid, "guest")
    m = _msgs(client, rid, "guest")
    assert [x["is_owner"] for x in m["members"]] == [True, False]
    assert m["me"]["is_owner"] is False and _msgs(client, rid)["me"]["is_owner"] is True


def test_transfer_owner(client):
    rid = _room(client)
    _join(client, rid, "guest")
    guest_handle = _msgs(client, rid, "guest")["me"]["member_handle"]
    assert client.post(f"/room/{rid}/owner", json={"to": guest_handle}, headers=_h("guest")).status_code == 403
    r = client.post(f"/room/{rid}/owner", json={"to": guest_handle}, headers=_h("owner"))
    assert r.status_code == 200 and r.json()["owner"] == guest_handle
    m = _msgs(client, rid, "guest")
    assert m["me"]["is_owner"] is True and "방장이 됐어요" in m["messages"][-1]["text"]


def test_owner_leaves_next_member_becomes_owner(client):
    rid = _room(client)
    _join(client, rid, "guest")
    assert client.post(f"/room/{rid}/leave", headers=_h("owner")).status_code == 204
    m = _msgs(client, rid, "guest")
    assert len(m["members"]) == 1 and m["me"]["is_owner"] is True
    assert "이제 guest님이 방장이에요" in m["messages"][-1]["text"]
    assert client.get(f"/room/{rid}/messages", headers=_h("owner")).status_code == 404


@pytest.fixture
def invites_on(monkeypatch):
    monkeypatch.setattr(settings, "room_invite_required", True)


def test_invite_required_for_new_rooms(client, invites_on):
    rid = _room(client)  # 첫 사람(방장)은 초대 없이
    assert _join(client, rid, "stranger").json()["detail"] == "invite required"
    assert _join(client, rid, "stranger", invite="wrong").json()["detail"] == "invite invalid"
    assert client.post(f"/room/{rid}/invites", json={"days": 7}, headers=_h("stranger")).status_code == 404
    r = client.post(f"/room/{rid}/invites", json={"days": 7}, headers=_h("owner"))
    assert r.status_code == 201
    token = r.json()["url"].split("invite=")[1]
    assert _join(client, rid, "friend", invite=token).status_code == 200
    assert _join(client, rid, "friend").status_code == 200  # 이미 참여자면 초대 필요 없음
    lst = client.get(f"/room/{rid}/invites", headers=_h("owner")).json()["invites"]
    assert lst[0]["uses"] == 1 and "token" not in str(lst)  # 원문은 목록에 없다
    assert client.delete(f"/room/{rid}/invites/{lst[0]['invite_id']}", headers=_h("owner")).status_code == 204
    assert _join(client, rid, "late", invite=token).json()["detail"] == "invite invalid"


def test_expired_invite(client, invites_on, monkeypatch):
    from app import store
    rid = _room(client)
    token = client.post(f"/room/{rid}/invites", json={"days": 1}, headers=_h("owner")).json()["url"].split("invite=")[1]
    from app.db.models import RoomInviteRow
    from app.db.session import get_sessionmaker
    from sqlalchemy import update
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(RoomInviteRow).values(expires_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)))
    assert _join(client, rid, "friend", invite=token).json()["detail"] == "invite invalid"


def test_old_rooms_stay_open(client):
    # 설정이 꺼진 상태(테스트 기본)로 만든 방은 주소로 들어온다
    rid = _room(client)
    assert _join(client, rid, "anyone").status_code == 200 and _msgs(client, rid)["invite_required"] is False


def _later(monkeypatch, **delta):
    real = rooms._utcnow()
    monkeypatch.setattr(rooms, "_utcnow", lambda: real + datetime.timedelta(**delta))


def test_warning_before_vote_reset_once(client, monkeypatch):
    rid = _room(client)
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": "카페 예약 서비스 만들어줘"})
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": "나머지는 알아서, 시안 먼저 볼게요"})
    assert _msgs(client, rid)["state"] == "AWAIT_APPROVAL"
    _later(monkeypatch, hours=21)
    m = _msgs(client, rid)
    assert m["messages"][-1]["kind"] == "warning" and m["messages"][-1]["text"] == rooms.MSG_WARN_VOTE
    seq = m["messages"][-1]["seq"]
    assert _msgs(client, rid)["messages"][-1]["seq"] == seq  # 한 번만
    _later(monkeypatch, hours=25)
    assert _msgs(client, rid)["messages"][-1]["text"] == rooms.MSG_VOTE_RESET


def test_warning_before_close(client, monkeypatch):
    rid = _room(client)
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": "안녕하세요"})
    _later(monkeypatch, days=28)
    texts = [x["text"] for x in _msgs(client, rid)["messages"]]
    assert rooms.MSG_WARN_CLOSE in texts and rooms.MSG_CLOSED not in texts
