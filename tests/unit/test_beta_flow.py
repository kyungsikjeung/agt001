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


def _messages_payload(client, room_id):
    r = client.get(f"/room/{room_id}/messages", headers={"X-Member-Id": OWNER})
    assert r.status_code == 200, r.text
    return r.json()


def _to_fill_first(client):
    """질문 예산을 다 써서(건너뛰기 아님) 요약에 온 것처럼, 빈칸이 남은 채 동의 대기로 만든다."""
    room_id = client.post("/room").json()["room_id"]
    _post(client, room_id, OWNER, "")
    _post(client, room_id, OWNER, "한식 식당 해요. 가게 이름은 내맘")
    _post(client, room_id, OWNER, "나머지는 알아서, 시안 먼저 볼게요")
    assert _state(room_id) == "AWAIT_APPROVAL"
    with store.room_tx(room_id) as (_room, session):
        card = session["prd"]
        assert card["fill_later"] is True  # "시안 먼저"는 빈칸을 다시 묻지 않는다
        card["fill_later"] = False
        card["fill_first"] = True
    return room_id


def test_missing_facts_asked_before_approval(client, monkeypatch):
    _beta(monkeypatch)
    room_id = _to_fill_first(client)
    assert _messages_payload(client, room_id)["fill_first"] is True
    # 빈칸이 있는데 동의하면 시안을 만들지 않고 다시 묻는다. 동의표도 세지 않는다.
    _post(client, room_id, OWNER, "승인")
    assert _state(room_id) == "AWAIT_APPROVAL"
    assert "아직 비어 있는 곳이 있어요" in _ai_replies(client, room_id)[-1]
    assert store.read_room(room_id)["votes"] == {}
    # 나중에 채우겠다고 하면 동의 질문이 나온다.
    _post(client, room_id, OWNER, "나중에")
    assert "시안을 만들어 볼까요" in _ai_replies(client, room_id)[-1]
    assert _messages_payload(client, room_id)["fill_first"] is False
    _post(client, room_id, OWNER, "승인")
    assert _state(room_id) in ("GENERATING", "DONE")


def test_fill_missing_then_approval(client, monkeypatch):
    _beta(monkeypatch)
    room_id = _to_fill_first(client)
    from app import llm
    import json as _json
    real = llm.chat_json

    def fake(system, user, **kw):
        if "010-1234-5678" in user:
            return _json.dumps({"updates": [{"slot": "phone", "value": "010-1234-5678"},
                                            {"slot": "location", "value": "서울 종로구"}]},
                               ensure_ascii=False)
        return real(system, user, **kw)

    monkeypatch.setattr(llm, "chat_json", fake)
    _post(client, room_id, OWNER, "전화번호는 010-1234-5678, 위치는 서울 종로구예요")
    reply = _ai_replies(client, room_id)[-1]
    assert "고쳤어요: 전화번호, 위치" in reply
    card = store.read_session(store.read_room(room_id)["session_id"])["prd"]
    left = [k for k, v in card["slots"].items() if v.get("status") == "placeholder"]
    if left:
        asked = reply.split("시안 전에 비어 있는 곳을 알려 주세요:")[1].split("\n")[0]
        assert "전화번호" not in asked and "위치" not in asked
    else:
        assert "시안을 만들어 볼까요" in reply
        assert _messages_payload(client, room_id)["fill_first"] is False


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


def test_card_put_with_login_needs_our_origin(client, monkeypatch):
    """F8: 로그인 쿠키로 고치는 요청은 우리 출처만 받는다 (보안 S-3)."""
    _beta(monkeypatch)
    room_id = client.post("/room").json()["room_id"]
    _post(client, room_id, OWNER, "")
    user_id = f"u-{uuid.uuid4().hex[:8]}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=user_id, nickname="사장님"))
        db.flush()
        db.add(UserRoomRow(user_id=user_id, room_id=room_id, member_id=OWNER))
    client.cookies.set(auth.SESSION_COOKIE, auth.create_session(user_id))
    body = {"fields": {"shop_name": "모퉁이커피"}}
    ours = (settings.public_base_url or "http://testserver").rstrip("/")
    assert client.put(f"/api/rooms/{room_id}/card", json=body).status_code == 403
    assert client.put(f"/api/rooms/{room_id}/card", json=body,
                      headers={"Origin": "https://evil.example"}).status_code == 403
    r = client.put(f"/api/rooms/{room_id}/card", json=body, headers={"Origin": ours})
    assert r.status_code == 200, r.text
    # 방 멤버 머리글로 오는 요청(쿠키 아님)은 지금처럼 출처 검사 없이 통과
    r = client.put(f"/api/rooms/{room_id}/card", json=body, headers={"X-Member-Id": OWNER})
    assert r.status_code == 200, r.text
