"""고칠 곳 칩 목록 (FIX_TAGS_CONTRACT §2·§6 1~4)."""
from app import store
from app.services import prd_engine as E
from app.services import prd_schema as S


def _room(client):
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": "카페예요"})
    client.post(f"/room/{rid}/chat", json={"member_id": "guest", "nickname": "손님", "message": ""})
    return rid


def _sid(rid):
    return store.read_room(rid)["session_id"]


def _get(client, rid, member="owner"):
    return client.get(f"/api/rooms/{rid}/fix-targets", headers={"X-Member-Id": member})


def test_1_filled_only_order_industry_label(client):
    """1번: 채워진 칸만·정해진 순서·업종 이름표. 사진은 늘, 공지는 켜졌을 때만."""
    rid = _room(client)
    with store.session_tx(_sid(rid)) as s:
        card = E.new_card("academy")
        card["turn"] = 1
        E._put(card, "business_type", "학원", S.FILLED, 1)
        E._put(card, "shop_name", "슬기영어", S.FILLED, 1)
        E._put(card, "offerings", ["초등반", "중등반"], S.FILLED, 1)
        E._put(card, "hours", "평일 15~21시", S.FILLED, 1)
        E._put(card, "location", "목동", S.FILLED, 1)
        E._put(card, "phone", None, S.PLACEHOLDER, 1)
        E._put(card, "contact_method", "전화", S.FILLED, 1)
        card["notice"] = {"text": "3월 휴강 안내", "popup": False}
        s["prd"] = card
    r = _get(client, rid)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    targets = r.json()["targets"]
    assert [t["key"] for t in targets] == [
        "shop_name", "items", "hours", "location", "contact_method", "notice", "photo"]
    items = next(t for t in targets if t["key"] == "items")
    assert items["label"] == S.label_for(E.industry_of(card), "offerings")
    assert all(set(t) == {"key", "label", "current", "parts"} for t in targets)
    # 공지를 끄면 공지 칩이 빠지고 사진 칩은 남는다
    with store.session_tx(_sid(rid)) as s:
        s["prd"].pop("notice", None)
    keys = [t["key"] for t in _get(client, rid).json()["targets"]]
    assert "notice" not in keys and "photo" in keys


def test_2_item_parts_and_current_cut(client):
    """2번: 항목 이름·가격 label, 가격 없으면 이름만, 30개 상한, 현재값 40자."""
    rid = _room(client)
    long_hours = "매일 10시~21시, 주말은 11시~20시, 공휴일도 쉬지 않고 열어요, 문의는 전화로"
    with store.session_tx(_sid(rid)) as s:
        card = E.new_card("cafe")
        card["turn"] = 1
        E._put(card, "business_type", "카페", S.FILLED, 1)
        E._put(card, "shop_name", "모퉁이 커피", S.FILLED, 1)
        E._put(card, "offerings", ["아메리카노", "라떼"], S.FILLED, 1)
        E._put(card, "hours", long_hours, S.FILLED, 1)
        card["price_pairs"] = {"아메리카노": "4,500원"}
        s["prd"] = card
    targets = _get(client, rid).json()["targets"]
    items = next(t for t in targets if t["key"] == "items")
    assert items["parts"] == [
        {"key": "아메리카노", "label": "아메리카노 4,500원"},
        {"key": "라떼", "label": "라떼"}]
    hours = next(t for t in targets if t["key"] == "hours")
    assert hours["current"] == long_hours[:40] and len(hours["current"]) <= 40
    # 30개 상한
    with store.session_tx(_sid(rid)) as s:
        E._put(s["prd"], "offerings", [f"메뉴{i}" for i in range(35)], S.FILLED, 1)
    items = next(t for t in _get(client, rid).json()["targets"] if t["key"] == "items")
    assert len(items["parts"]) == 30


def test_3_auth_empty_cache(client):
    """3번: 낯선 사람은 404(기존 _member_room 방식), 카드 없으면 빈 목록, 캐시 없음."""
    rid = _room(client)
    assert _get(client, rid, "stranger").status_code == 404
    assert _get(client, rid, "guest").status_code == 200
    with store.session_tx(_sid(rid)) as s:
        s["prd"] = None
    r = _get(client, rid)
    assert r.json() == {"targets": []}
    assert r.headers["cache-control"] == "no-store"


def test_4_correction_via_chat(client, monkeypatch):
    """4번: 요약 상태(AWAIT_APPROVAL)에서 합친 말을 채팅으로 보내면 카드가 바뀐다."""
    import json as _json

    from app import llm

    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat",
                json={"member_id": "owner", "nickname": "사장님", "message": "카페 예약 서비스 만들어줘"})
    client.post(f"/room/{rid}/chat",
                json={"member_id": "owner", "nickname": "사장님", "message": "나머지는 알아서, 시안 먼저 볼게요"})
    assert client.get(f"/room/{rid}/messages", headers={"X-Member-Id": "owner"}).json()["state"] == "AWAIT_APPROVAL"
    with store.session_tx(_sid(rid)) as s:
        card = s["prd"]
        E._put(card, "shop_name", "모퉁이 커피", S.FILLED, card.get("turn", 0))
        E._put(card, "offerings", ["아메리카노", "라떼"], S.FILLED, card.get("turn", 0))
        E._put(card, "hours", "매일 9시~18시", S.FILLED, card.get("turn", 0))
        card["price_pairs"] = {"아메리카노": "4,500원"}
    label = next(t for t in _get(client, rid).json()["targets"] if t["key"] == "hours")["label"]
    assert label == "영업시간"

    real = llm.chat_json

    def fake(system, user, **kw):
        if "매일 10시~21시" in user:
            return _json.dumps({"updates": [{"slot": "hours", "value": "매일 10시~21시"}]}, ensure_ascii=False)
        if "아메리카노" in user and "5,000원" in user:
            return _json.dumps({"updates": [{"slot": "offerings", "value": "아메리카노"},
                                             {"slot": "price", "value": "5,000원"}]}, ensure_ascii=False)
        return real(system, user, **kw)

    monkeypatch.setattr(llm, "chat_json", fake)

    def _last_ai():
        msgs = client.get(f"/room/{rid}/messages", headers={"X-Member-Id": "owner"}).json()["messages"]
        return msgs[-1]["text"]

    client.post(f"/room/{rid}/chat",
                json={"member_id": "owner", "nickname": "사장님", "message": f"{label} 매일 10시~21시"})
    assert "고쳤어요" in _last_ai()
    assert store.read_session(_sid(rid))["prd"]["slots"]["hours"]["value"] == "매일 10시~21시"
    client.post(f"/room/{rid}/chat",
                json={"member_id": "owner", "nickname": "사장님", "message": "아메리카노 5,000원으로"})
    assert "고쳤어요" in _last_ai()
    assert store.read_session(_sid(rid))["prd"]["price_pairs"]["아메리카노"] == "5,000원"
