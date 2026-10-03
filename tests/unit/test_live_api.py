"""실시간 대화 API (COMPOSE_INTERVIEW_CONTRACT §4): 방장만, 채팅 기록에 남김, 미리보기는 정한 부품만."""
import json

from app import llm, store


def _fake(monkeypatch):
    table = {"카페요": [{"slot": "business_type", "value": "카페"}],
             "바다카페": [{"slot": "shop_name", "value": "바다카페"}]}

    def fake(system, user, **kw):
        if "[사장님 메시지] " not in user:
            return json.dumps({"missing": [], "conflicts": []})
        return json.dumps({"updates": table.get(user.split("[사장님 메시지] ", 1)[-1], [])}, ensure_ascii=False)

    monkeypatch.setattr(llm, "chat_json", fake)


def _room(client):
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    client.post(f"/room/{rid}/chat", json={"member_id": "guest", "nickname": "손님", "message": ""})
    return rid


def test_live_flow_and_preview(client, monkeypatch):
    _fake(monkeypatch)
    rid = _room(client)
    h = {"X-Member-Id": "owner"}
    r = client.post(f"/api/rooms/{rid}/live/turn", json={"text": ""}, headers=h).json()
    assert "어떤 사이트" in r["question_text"] and r["speech"]
    assert client.get(f"/api/rooms/{rid}/live/preview", headers=h).json()["html"] is None
    r = client.post(f"/api/rooms/{rid}/live/turn", json={"text": "카페요"}, headers=h).json()
    assert r["phase"] == "compose" and r["options"][0] == "따뜻하고 아늑하게" and r["has_previews"]
    opts = client.get(f"/api/rooms/{rid}/live/options", headers=h).json()
    assert opts["component"] == "tone" and len(opts["options"]) == 4 and opts["options"][0]["html"]
    r = client.post(f"/api/rooms/{rid}/live/turn", json={"text": "따뜻하게"}, headers=h).json()
    assert "사진 크게" in r["options"] and r["speech_parts"][0].startswith("좋아요")
    r = client.post(f"/api/rooms/{rid}/live/turn", json={"text": "사진 크게"}, headers=h).json()
    assert r["last"] == "hero" and [c["id"] for c in r["components"]] == ["tone", "hero"]
    client.post(f"/api/rooms/{rid}/live/turn", json={"text": "바다카페"}, headers=h)
    p = client.get(f"/api/rooms/{rid}/live/preview", headers=h).json()
    assert "바다카페" in p["html"] and p["last"] == "hero"
    # 다시 열면 같은 질문을 진전 없이 보여 준다
    again = client.post(f"/api/rooms/{rid}/live/turn", json={"text": ""}, headers=h).json()
    assert again["phase"] == "compose" and "메뉴" in again["question_text"]
    texts = [m["text"] for m in store.read_messages(rid, 0)]
    assert "카페요" in texts and any("첫 화면" in t for t in texts)


def test_live_owner_only(client, monkeypatch):
    _fake(monkeypatch)
    rid = _room(client)
    assert client.post(f"/api/rooms/{rid}/live/turn", json={"text": "카페요"},
                       headers={"X-Member-Id": "guest"}).status_code == 403
    assert client.get(f"/api/rooms/{rid}/live/preview", headers={"X-Member-Id": "guest"}).status_code == 403
    assert client.get(f"/api/rooms/{rid}/live/options", headers={"X-Member-Id": "guest"}).status_code == 403
    assert client.post("/api/rooms/nope/live/turn", json={"text": ""},
                       headers={"X-Member-Id": "owner"}).status_code == 404
