"""그룹 + 카드 추가 (GROUP_CARDS_CONTRACT §5). 외부 호출 없음."""
from app import store
from app.services import card_data
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services import site_data
from app.services.site_render import render_site

H = {"X-Member-Id": "owner"}
MENU = ["아메리카노", "카페라떼", "자몽에이드", "치즈케이크"]


def _cafe(client, menu=MENU):
    """시안까지 있는 카페 방. 낱말표로 커피·음료·디저트로 나뉜다."""
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": "카페예요"})
    room = store.read_room(rid)
    with store.session_tx(room["session_id"]) as s:
        card = s.get("prd") or E.new_card("cafe")
        E._put(card, "business_type", "카페", S.FILLED, 1)
        E._put(card, "shop_name", "연남 느린오후", S.FILLED, 1)
        E._put(card, "offerings", list(menu), S.FILLED, 1)
        card["turn"] = 1
        s["prd"] = card
        s["design_url"] = "/design/x"
    return rid


def _card(rid):
    return store.read_session(store.read_room(rid)["session_id"])["prd"]


def _shown(rid):
    """공개 사이트가 보이는 분류: [(분류, [항목…])]."""
    card = _card(rid)
    return [(c["name"], [i["name"] for i in c["items"]]) for c in card_data._catalog(card, "cafe")]


def _put(client, rid, body):
    return client.put(f"/api/rooms/{rid}/card", json=body, headers=H)


def test_preview_starts_as_shown(client):
    rid = _cafe(client)
    shown = _shown(rid)
    assert [g for g, _ in shown] == ["커피", "음료", "디저트"]
    body = client.get(f"/api/rooms/{rid}/card/preview?variant=v1", headers=H).json()
    assert body["groups"] == ["커피", "음료", "디저트"]
    assert {i["name"]: i["group"] for i in body["items"]} == {n: g for g, names in shown for n in names}
    assert {i["photo"] for i in body["items"]} == {"auto"}
    with store.session_tx(store.read_room(rid)["session_id"]) as s:
        s["prd"]["photos"] = [{"id": "p1", "url": "/uploads/x/1.jpg", "tag": "item:아메리카노"}]
        s["prd"]["item_photo_off"] = ["치즈케이크"]
    items = {i["name"]: i["photo"] for i in client.get(f"/api/rooms/{rid}/card/preview", headers=H).json()["items"]}
    assert items["아메리카노"] == "own" and items["치즈케이크"] == "none" and items["카페라떼"] == "auto"


def test_groups_order_rename_delete_clear(client):
    rid = _cafe(client)
    assert _put(client, rid, {"groups": {"order": ["디저트", "커피", "음료"]}}).status_code == 200
    assert _shown(rid) == [("디저트", ["치즈케이크"]), ("커피", ["아메리카노", "카페라떼"]), ("음료", ["자몽에이드"])]
    # 이름 바꾸기: 안의 항목이 따라간다
    r = _put(client, rid, {"groups": {"order": ["디저트", "에스프레소바", "음료"], "rename": {"커피": "에스프레소바"}}})
    assert r.status_code == 200
    assert _shown(rid)[1] == ("에스프레소바", ["아메리카노", "카페라떼"])
    # 지우기: 그 항목은 첫 그룹으로
    assert _put(client, rid, {"groups": {"order": ["디저트", "에스프레소바"]}}).status_code == 200
    assert _shown(rid) == [("디저트", ["자몽에이드", "치즈케이크"]), ("에스프레소바", ["아메리카노", "카페라떼"])]
    # 빈 그룹도 목록에 남는다(공개 사이트엔 안 나옴)
    assert _put(client, rid, {"groups": {"order": ["디저트", "에스프레소바", "시즌"]}}).status_code == 200
    body = client.get(f"/api/rooms/{rid}/card/preview", headers=H).json()
    assert body["groups"] == ["디저트", "에스프레소바", "시즌"] and "시즌" not in [g for g, _ in _shown(rid)]
    # 다 비우기: 낱말표로, 다시 묻지 않는다
    assert _put(client, rid, {"groups": {"order": []}}).status_code == 200
    card = _card(rid)
    assert card["slots"]["menu_categories"]["status"] == S.REJECTED and "item_groups" not in card
    assert [g for g, _ in _shown(rid)] == ["커피", "음료", "디저트"]


def test_groups_validation(client):
    rid = _cafe(client)
    bad = [{"order": ["커피", "커피"]}, {"order": ["가" * 13]}, {"order": [f"g{i}" for i in range(11)]},
           {"order": ["커피·라떼"]}, {"order": [" "]}, {"order": ["커피"], "rename": {"없는그룹": "커피"}},
           {"order": ["커피"], "rename": {"음료": "주스"}}]
    for groups in bad:
        assert _put(client, rid, {"groups": groups}).status_code == 400, groups
    assert "menu_categories" not in _card(rid)["slots"] or _card(rid)["slots"]["menu_categories"]["status"] != S.FILLED


def test_item_group_photo_follow_rename_and_remove(client):
    rid = _cafe(client)
    # 그룹 목록이 없을 때 그룹을 고르면 지금 보이는 분류가 그룹 목록이 된다
    assert _put(client, rid, {"items": [{"name": "아메리카노", "group": "음료"}]}).status_code == 200
    assert _shown(rid) == [("커피", ["카페라떼"]), ("음료", ["아메리카노", "자몽에이드"]), ("디저트", ["치즈케이크"])]
    # 한 요청: 새 그룹 + 그 그룹에 새 항목(사진 없음)
    r = _put(client, rid, {"groups": {"order": ["커피", "음료", "디저트", "시즌"]},
                           "items": [{"name": "호박라떼", "add": True, "group": "시즌", "photo": "none"}]})
    assert r.status_code == 200
    assert _shown(rid)[-1] == ("시즌", ["호박라떼"])
    assert _card(rid)["item_photo_off"] == ["호박라떼"]
    # 이름 바꾸면 그룹·사진 없음이 따라간다
    assert _put(client, rid, {"items": [{"name": "호박라떼", "rename": "단호박라떼"}]}).status_code == 200
    card = _card(rid)
    assert card["item_groups"]["단호박라떼"] == "시즌" and card["item_photo_off"] == ["단호박라떼"]
    # 사진 다시 기본으로, 빼기는 둘 다 지운다
    assert _put(client, rid, {"items": [{"name": "단호박라떼", "photo": "auto"}]}).status_code == 200
    assert "item_photo_off" not in _card(rid)
    assert _put(client, rid, {"items": [{"name": "단호박라떼", "remove": True}]}).status_code == 200
    assert "단호박라떼" not in _card(rid)["item_groups"]
    # 없는 그룹은 400
    assert _put(client, rid, {"items": [{"name": "카페라떼", "group": "없는그룹"}]}).status_code == 400


def test_untouched_card_catalog_unchanged():
    card = E.new_card("cafe")
    E._put(card, "offerings", MENU, S.FILLED, 1)
    E._put(card, "menu_categories", ["음료", "커피"], S.FILLED, 1)
    before = card_data._catalog(card, "cafe")
    card["item_groups"] = {"치즈케이크": "없는그룹"}  # 목록에 없는 그룹은 무시
    assert card_data._catalog(card, "cafe") == before


def _pack():
    return {"prices": {}, "photos": {"category:커피": "/static/examples/cafe/coffee.webp"}, "catalog": []}


def test_photo_off_category_cover():
    data = {"catalog": [{"name": "커피", "items": [{"name": "아메리카노", "price": "4,500원"},
                                                  {"name": "카페라떼", "price": "5,000원"}]}]}
    card = {"item_photo_off": ["아메리카노"]}
    sec = {"variant": "categories"}
    site_data._fill_catalog(sec, data, _pack(), "A", False, card=card)
    assert sec["content"]["categories"][0]["image"] == "/static/examples/cafe/coffee.webp"
    card["item_photo_off"] = ["아메리카노", "카페라떼"]  # 모두 사진 없음이면 대표도 없다
    sec = {"variant": "categories"}
    site_data._fill_catalog(sec, data, _pack(), "A", False, card=card)
    assert "image" not in sec["content"]["categories"][0]
    assert site_data._item_image(card, "아메리카노", _pack(), {"image": "/x.webp"}) == {"image_off": True}


def test_photo_off_card_has_no_empty_box():
    items = [{"name": "아메리카노", "price": "4,500원", "image_off": True}, {"name": "라떼", "price": "5,000원"}]
    spec = {"sections": [{"id": "menu", "type": "offerings", "variant": "cards",
                          "content": {"label": "메뉴", "items": items}}]}
    import copy
    import json
    from pathlib import Path
    base = json.loads((Path(__file__).resolve().parents[2] / "templates" / "samples" / "cafe.json").read_text(encoding="utf-8"))
    full = copy.deepcopy(base)
    full["sections"] = spec["sections"]
    out = render_site(full, kind="cafe")
    assert out.count("[사진 입력]") == 1  # 라떼(아직 없음)만, 사진 없음 카드는 빈 칸도 없다
