"""채팅방 타이머·인원 (D7·D8, ROOM_POLICY §4.2): 시간을 앞당겨 판정한다."""
import datetime

from app import store
from app.config import settings
from app.services import rooms


def _room(client):
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    return rid


def _post(client, rid, text, member="owner"):
    return client.post(f"/room/{rid}/chat", json={"member_id": member, "nickname": member, "message": text})


def _msgs(client, rid, member="owner"):
    return client.get(f"/room/{rid}/messages", headers={"X-Member-Id": member}).json()


def _later(monkeypatch, **delta):
    real = rooms._utcnow()
    monkeypatch.setattr(rooms, "_utcnow", lambda: real + datetime.timedelta(**delta))


def _to_approval(client, rid):
    _post(client, rid, "카페 예약 서비스 만들어줘")
    _post(client, rid, "나머지는 알아서, 시안 먼저 볼게요")
    assert _msgs(client, rid)["state"] == "AWAIT_APPROVAL"


def test_member_cap(client):
    rid = _room(client)
    for i in range(settings.room_max_members - 1):
        assert _post(client, rid, "", f"m{i}").status_code == 200
    assert _post(client, rid, "", "one-too-many").status_code == 403


def test_vote_reset_after_24h(client, monkeypatch):
    rid = _room(client)
    _post(client, rid, "", "guest")
    _to_approval(client, rid)
    _post(client, rid, "승인")  # 1/2 → 결론 없음
    assert _msgs(client, rid)["votes"]
    _later(monkeypatch, hours=25)
    m = _msgs(client, rid)
    assert m["votes"] == {} and m["messages"][-1]["text"] == rooms.MSG_VOTE_RESET
    # 다시 읽어도 같은 글을 또 남기지 않는다
    assert _msgs(client, rid)["messages"][-1]["seq"] == m["messages"][-1]["seq"]


def test_quote_expires_after_7_days(client, monkeypatch):
    rid = _room(client)
    _to_approval(client, rid)
    _post(client, rid, "승인")
    assert _msgs(client, rid)["state"] == "QUOTED"
    _later(monkeypatch, days=8)
    m = _msgs(client, rid)
    assert m["state"] == "GATHERING" and m["messages"][-1]["text"] == rooms.MSG_QUOTE_EXPIRED


def test_closed_after_30_days_owner_reopens(client, monkeypatch):
    rid = _room(client)
    _post(client, rid, "", "guest")
    _post(client, rid, "안녕하세요")
    _later(monkeypatch, days=31)
    m = _msgs(client, rid)
    assert m["closed"] is True and m["messages"][-1]["text"] == rooms.MSG_CLOSED
    assert _post(client, rid, "저도 있어요", "guest").status_code == 423
    assert _post(client, rid, "다시 시작할게요").status_code == 200
    texts = [x["text"] for x in _msgs(client, rid, "owner")["messages"]]
    assert rooms.MSG_REOPENED in texts


def test_vote_reset_follows_setting(client, monkeypatch):
    # S-9: 타이머 값이 설정값에서 오므로 코드를 고치지 않고 바꿀 수 있다.
    monkeypatch.setattr(settings, "room_vote_reset_hours", 1)
    rid = _room(client)
    _post(client, rid, "", "guest")
    _to_approval(client, rid)
    _post(client, rid, "승인")  # 1/2 → 결론 없음
    assert _msgs(client, rid)["votes"]
    _later(monkeypatch, hours=2)
    m = _msgs(client, rid)
    assert m["votes"] == {} and m["messages"][-1]["text"] == rooms.MSG_VOTE_RESET


def test_member_cap_follows_setting(client, monkeypatch):
    # S-9: 인원 상한이 설정값에서 오므로 코드를 고치지 않고 바꿀 수 있다.
    monkeypatch.setattr(settings, "room_max_members", 2)
    rid = _room(client)
    assert _post(client, rid, "", "guest").status_code == 200
    assert _post(client, rid, "", "one-too-many").status_code == 403


def test_active_room_untouched(client):
    rid = _room(client)
    _to_approval(client, rid)
    m = _msgs(client, rid)
    assert m["closed"] is False and m["state"] == "AWAIT_APPROVAL"
