"""직접 편집 API (계약 §5): 참여자는 읽기, 방장만 고치기, 빈 값은 입력 필요, 공개본에 바로 반영."""
import re

from app import store


def _room(client):
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": "카페예요"})
    client.post(f"/room/{rid}/chat", json={"member_id": "guest", "nickname": "손님", "message": ""})
    return rid


def _cafe_room(client):
    """시안까지 있는 카페 방 (청사진 A-dinein, v1 기본 [hero,menu,space,around,inquiry])."""
    from app.services import prd_engine as E
    from app.services import prd_schema as S
    rid = _room(client)
    room = store.read_room(rid)
    with store.session_tx(room["session_id"]) as s:
        card = s.get("prd") or E.new_card("cafe")
        E._put(card, "business_type", "카페", S.FILLED, 1)
        E._put(card, "shop_name", "연남 느린오후", S.FILLED, 1)
        E._put(card, "offerings", ["아메리카노", "카페라떼"], S.FILLED, 1)
        E._put(card, "phone", "02-123-4567", S.FILLED, 1)
        E._put(card, "hours", "매일 10~21시", S.FILLED, 1)
        E._put(card, "location", "서울 마포구 연남로 12", S.FILLED, 1)
        card["turn"] = 1
        s["prd"] = card
        s["design_url"] = "/design/x"
    return rid


def _section_ids(html_text: str) -> list:
    return re.findall(r'data-section-id="([^"]+)"', html_text)


def test_read_and_owner_only_edit(client):
    rid = _room(client)
    v = client.get(f"/api/rooms/{rid}/card", headers={"X-Member-Id": "guest"}).json()
    assert v["can_edit"] is False and {f["key"] for f in v["fields"]} >= {"shop_name", "phone"}
    assert client.put(f"/api/rooms/{rid}/card", json={"fields": {"shop_name": "x"}}, headers={"X-Member-Id": "guest"}).status_code == 403
    r = client.put(f"/api/rooms/{rid}/card", json={"fields": {"shop_name": "모퉁이커피", "phone": "공일공 1234 5678", "offerings": "라떼, 모카"}},
                   headers={"X-Member-Id": "owner"})
    assert r.status_code == 200
    f = {x["key"]: x for x in r.json()["fields"]}
    assert f["shop_name"]["value"] == "모퉁이커피" and f["shop_name"]["status"] == "filled"
    assert f["phone"]["value"] == "010-1234-5678" and f["offerings"]["value"] == "라떼, 모카"
    r = client.put(f"/api/rooms/{rid}/card", json={"fields": {"shop_name": ""}}, headers={"X-Member-Id": "owner"})
    assert {x["key"]: x for x in r.json()["fields"]}["shop_name"]["status"] == "placeholder"
    assert client.get(f"/api/rooms/{rid}/card", headers={"X-Member-Id": "stranger"}).status_code == 404


def test_edit_before_publish_rerenders_drafts(client, monkeypatch):
    """공개 전 직접 고치기도 시안 3안을 다시 그린다 (EDIT_PUBLISH_PLAN §4-5)."""
    from app.services import photos
    calls = []
    monkeypatch.setattr(photos, "_refresh_designs_async", lambda rid, req, announced="": calls.append((rid, announced)))
    rid = _room(client)
    client.put(f"/api/rooms/{rid}/card", json={"fields": {"shop_name": "모퉁이커피"}}, headers={"X-Member-Id": "owner"})
    assert calls == []  # 시안이 없으면 다시 그릴 것도 없다
    room = store.read_room(rid)
    with store.session_tx(room["session_id"]) as s:
        s["design_url"] = "/design/x"
    client.put(f"/api/rooms/{rid}/card", json={"fields": {"phone": "010-1234-5678"}}, headers={"X-Member-Id": "owner"})
    assert calls == [(rid, "고친 내용을 시안에 넣었어요.")]


def test_notice_set_and_clear(client):
    """공지 띠·팝업 (D56): 방장이 켜고, 빈 글이면 끈다. 공개본 다시 그리기도 같은 길."""
    rid = _room(client)
    h = {"X-Member-Id": "owner"}
    r = client.put(f"/api/rooms/{rid}/card", json={"notice": {"text": "10월 3일은 쉬어요", "popup": True}}, headers=h)
    assert r.json()["notice"] == {"text": "10월 3일은 쉬어요", "photos": [], "popup": True}
    r = client.put(f"/api/rooms/{rid}/card", json={"notice": {"text": "", "popup": True}}, headers=h)
    assert r.json()["notice"] == {"text": "", "popup": False}


def test_preview_owner_design_and_hidden(client):
    """테스트 6: 방장 200·다른 참여자 403·시안 전 409, 숨긴 구역 hidden:true."""
    rid = _room(client)
    assert client.get(f"/api/rooms/{rid}/card/preview",
                      headers={"X-Member-Id": "owner"}).status_code == 409
    room = store.read_room(rid)
    with store.session_tx(room["session_id"]) as s:
        s["design_url"] = "/design/x"
    assert client.get(f"/api/rooms/{rid}/card/preview",
                      headers={"X-Member-Id": "guest"}).status_code == 403
    rid = _cafe_room(client)
    h = {"X-Member-Id": "owner"}
    r = client.put(f"/api/rooms/{rid}/card",
                   json={"layout": {"variant": "v1", "hidden": ["space"]}}, headers=h)
    assert r.status_code == 200
    assert r.json()["layout"]["v1"]["hidden"] == ["space"]
    r = client.get(f"/api/rooms/{rid}/card/preview?variant=v1", headers=h)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["variant"] == "v1"
    assert "data-edit-mode" in body["html"] and "agt-edit" in body["html"]
    assert body["sections"]
    assert all({"id", "label", "bind", "locked", "hidden"} <= set(s) for s in body["sections"])
    space = next(s for s in body["sections"] if s["id"] == "space")
    assert space["hidden"] is True
    # 편집기가 지금 값에서 시작하게: 이 안의 구역 편집과 항목 가격·설명
    assert body["layout"]["hidden"] == ["space"]
    assert [i["name"] for i in body["items"]] == store.read_session(
        store.read_room(rid)["session_id"])["prd"]["slots"]["offerings"]["value"]
    assert all({"name", "price", "note", "group", "photo"} == set(i) for i in body["items"])  # 그룹 카드 §2-6
    assert next(s for s in body["sections"] if s["id"] == "hero")["locked"] is True
    # variant 생략·이상한 값은 v1 (choice 없음)
    assert client.get(f"/api/rooms/{rid}/card/preview", headers=h).json()["variant"] == "v1"
    assert client.get(f"/api/rooms/{rid}/card/preview?variant=vx", headers=h).json()["variant"] == "v1"


def test_put_items_rename_remove_price(client):
    """테스트 7: 이름 바꾸면 가격·설명·사진 태그 따라감, 마지막 1개 빼기 400, 빈 가격은 키 삭제."""
    rid = _cafe_room(client)
    h = {"X-Member-Id": "owner"}
    room = store.read_room(rid)
    with store.session_tx(room["session_id"]) as s:
        card = s["prd"]
        card["price_pairs"] = {"아메리카노": "4,500원", "카페라떼": "5,000원"}
        card["item_notes"] = {"아메리카노": "샷 추가 500원"}
        card["photos"] = [{"id": "p1", "url": "/uploads/x/1.jpg", "tag": "item:아메리카노"}]
    r = client.put(f"/api/rooms/{rid}/card", json={"items": [
        {"name": "아메리카노", "rename": "아이스 아메리카노", "price": "5,000원"},
        {"name": "없는메뉴", "price": "1원"},
    ]}, headers=h)
    assert r.status_code == 200
    card = store.read_session(room["session_id"])["prd"]
    assert card["slots"]["offerings"]["value"] == ["아이스 아메리카노", "카페라떼"]
    assert card["price_pairs"] == {"아이스 아메리카노": "5,000원", "카페라떼": "5,000원"}
    assert card["item_notes"] == {"아이스 아메리카노": "샷 추가 500원"}
    assert card["photos"][0]["tag"] == "item:아이스 아메리카노"
    # 빈 가격은 키 삭제, 빈 설명은 키 삭제
    r = client.put(f"/api/rooms/{rid}/card", json={"items": [
        {"name": "카페라떼", "price": "", "note": ""},
    ]}, headers=h)
    assert r.status_code == 200
    card = store.read_session(room["session_id"])["prd"]
    assert "카페라떼" not in card["price_pairs"] and "카페라떼" not in card.get("item_notes", {})
    # 빼기·더하기
    r = client.put(f"/api/rooms/{rid}/card", json={"items": [{"name": "카페라떼", "remove": True}]}, headers=h)
    assert r.status_code == 200
    assert store.read_session(room["session_id"])["prd"]["slots"]["offerings"]["value"] == ["아이스 아메리카노"]
    # 마지막 1개는 못 뺀다
    r = client.put(f"/api/rooms/{rid}/card", json={"items": [{"name": "아이스 아메리카노", "remove": True}]},
                   headers=h)
    assert r.status_code == 400
    r = client.put(f"/api/rooms/{rid}/card", json={"items": [{"name": "바닐라라떼", "add": True, "price": "5,500원"}]},
                   headers=h)
    assert r.status_code == 200
    card = store.read_session(room["session_id"])["prd"]
    assert card["slots"]["offerings"]["value"] == ["아이스 아메리카노", "바닐라라떼"]
    assert card["price_pairs"]["바닐라라떼"] == "5,500원"
    # 같은 이름 더하기·variant 이상한 layout은 무시/400
    r = client.put(f"/api/rooms/{rid}/card", json={"items": [{"name": "바닐라라떼", "add": True}]}, headers=h)
    assert r.status_code == 200
    assert store.read_session(room["session_id"])["prd"]["slots"]["offerings"]["value"] == ["아이스 아메리카노", "바닐라라떼"]
    assert client.put(f"/api/rooms/{rid}/card",
                      json={"layout": {"variant": "vx", "hidden": ["space"]}}, headers=h).status_code == 400


def test_put_layout_repaints_published_without_edit_flag(client):
    """테스트 8: layout 저장 → 공개본 구역 순서가 바뀜(공개 뒤에도 남음), 공개본에 data-edit-mode 없음."""
    from app.config import settings
    rid = _cafe_room(client)
    h = {"X-Member-Id": "owner"}
    room = store.read_room(rid)
    session = store.read_session(room["session_id"])
    with store.session_tx(room["session_id"]) as s:
        s["prd"]["published"] = "v1"
    from app.services import design
    design.publish_choice(session["requirement_id"], store.read_session(room["session_id"])["prd"], "v1")
    key = store.read_session(room["session_id"])["requirement_id"]
    before = (settings.generated_dir / key / "published" / "index.html").read_text(encoding="utf-8")
    assert _section_ids(before).index("menu") < _section_ids(before).index("around")
    r = client.put(f"/api/rooms/{rid}/card", json={"layout": {
        "variant": "v1", "order": ["around", "menu", "space", "inquiry"], "hidden": ["space"]}}, headers=h)
    assert r.status_code == 200
    assert r.json()["layout"]["v1"]["hidden"] == ["space"]
    after = (settings.generated_dir / key / "published" / "index.html").read_text(encoding="utf-8")
    ids = _section_ids(after)
    assert ids.index("around") < ids.index("menu")
    assert "space" not in ids
    assert after.count("data-edit-mode") == 0 and after.count("agt-edit") == 0
    # 새로고침(다시 공개) 뒤에도 남음
    design.publish_choice(key, store.read_session(room["session_id"])["prd"], "v1")
    again = (settings.generated_dir / key / "published" / "index.html").read_text(encoding="utf-8")
    assert _section_ids(again).index("around") < _section_ids(again).index("menu")
    assert "space" not in _section_ids(again)
    # reset이면 처음 모양으로
    r = client.put(f"/api/rooms/{rid}/card", json={"layout": {"variant": "v1", "reset": True}}, headers=h)
    assert r.status_code == 200
    assert r.json()["layout"] == {}
