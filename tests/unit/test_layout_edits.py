"""구역 편집 코어 (EDIT_WAVE2_CONTRACT §6 테스트 1-4)."""
import copy

from app.services import archetype as AT
from app.services import design_variants as DV
from app.services import layout_edits as LE
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services import site_data as SD


def _cafe_card():
    """test_design_variants와 같은 현실 카드."""
    card = E.new_card("cafe")
    E._put(card, "business_type", "카페", S.FILLED, 1)
    E._put(card, "shop_name", "연남 느린오후", S.FILLED, 1)
    E._put(card, "offerings", ["아메리카노", "카페라떼"], S.FILLED, 1)
    E._put(card, "phone", "02-123-4567", S.FILLED, 1)
    E._put(card, "hours", "매일 10~21시", S.FILLED, 1)
    E._put(card, "location", "서울 마포구 연남로 12", S.FILLED, 1)
    card["turn"] = 1
    return card


def _academy_card():
    card = E.new_card("academy")
    E._put(card, "business_type", "영어 학원", S.FILLED, 1)
    E._put(card, "shop_name", "믿음영어", S.FILLED, 1)
    E._put(card, "offerings", ["초등 파닉스반", "중등 내신반"], S.FILLED, 1)
    E._put(card, "staff", ["김믿음 원장(초등)"], S.FILLED, 1)
    E._put(card, "phone", "02-777-8888", S.FILLED, 1)
    E._put(card, "location", "서울 노원구 상계로 77", S.FILLED, 1)
    card["turn"] = 1
    return card


def _blueprint(card, pos=0):
    bp = AT.blueprint(card)
    assert bp is not None
    return bp


def test_normalize_drops_unknown_locks_and_caps_added():
    """테스트 1: 모르는 id 버림, hero·inquiry 숨기기/옮기기 불가, added 최대 3, 효과 없으면 None."""
    card = _cafe_card()
    bp = _blueprint(card)  # A-dinein, v1 기본 [hero,menu,space,around,inquiry]
    base = ["hero", "menu", "space", "around", "inquiry"]

    # 효과 없으면 None
    assert LE.normalize(None, bp, 0) is None
    assert LE.normalize({}, bp, 0) is None
    assert LE.normalize({"order": list(base), "hidden": [], "added": []}, bp, 0) is None

    # 모르는 id는 조용히 버림 (효과가 남는 순서로)
    cleaned = LE.normalize({"order": ["around", "nope", "menu"], "hidden": ["nope"], "added": ["nope"]}, bp, 0)
    assert cleaned is not None
    assert "nope" not in cleaned["order"] and "nope" not in cleaned["hidden"] and "nope" not in cleaned["added"]
    assert cleaned["order"][1:3] == ["around", "menu"]
    # 모르는 id만 있으면 효과 없음 → None
    assert LE.normalize({"order": ["nope"], "hidden": ["nope"], "added": ["nope"]}, bp, 0) is None

    # hero·inquiry 숨기기 불가
    cleaned = LE.normalize({"hidden": ["hero", "inquiry", "menu"]}, bp, 0)
    assert cleaned is not None
    assert cleaned["hidden"] == ["menu"]

    # hero·inquiry 옮기기 불가: hero 0번, inquiry 원래 자리 유지
    cleaned = LE.normalize({"order": ["inquiry", "around", "menu", "space", "hero"]}, bp, 0)
    assert cleaned["order"][0] == "hero"
    assert cleaned["order"].index("inquiry") == base.index("inquiry")
    assert cleaned["order"][1:4] == ["around", "menu", "space"]

    # added 최대 3 (합성 청사진으로 5개 후보)
    fake = {"strategies": [
        {"id": "v1", "sections": [{"id": "a"}, {"id": "b"}]},
        {"id": "v2", "sections": [{"id": "c"}, {"id": "d"}, {"id": "e"}]},
        {"id": "v3", "sections": [{"id": "f"}, {"id": "g"}]},
    ]}
    cleaned = LE.normalize({"added": ["c", "d", "e", "f", "g", "nope", "a", "c"]}, fake, 0)
    assert cleaned is not None
    assert cleaned["added"] == ["c", "d", "e"]
    assert len(cleaned["added"]) == LE.MAX_ADDED == 3


def test_apply_keeps_hero_first_drops_hidden_and_shapes_added():
    """테스트 2: hero 0번 유지, 숨긴 구역 없음, 추가 구역이 skeleton 모양."""
    card = _cafe_card()
    bp = _blueprint(card)
    skel = SD.skeleton(bp, 0)
    assert skel["sections"][0]["id"] == "hero"

    edits = LE.normalize({"order": ["around", "menu", "space", "inquiry"],
                          "hidden": ["space"], "added": ["sign"]}, bp, 0)
    assert edits is not None
    got = LE.apply(skel, bp, 0, edits)
    ids = [s["id"] for s in got["sections"]]
    assert ids[0] == "hero"  # hero 0번 유지
    assert "space" not in ids  # 숨긴 구역 없음
    assert "sign" in ids  # 추가 구역 들어감
    assert ids.index("around") < ids.index("menu")  # 순서 반영
    assert ids == ["hero", "around", "menu", "sign", "inquiry"]  # 더한 구역은 inquiry 바로 앞
    # 추가 구역이 skeleton 모양
    sign = next(s for s in got["sections"] if s["id"] == "sign")
    assert sign["content"] == {}
    for key in ("id", "type", "variant", "bind"):
        assert sign[key]
    # 원본 skeleton은 그대로
    assert [s["id"] for s in skel["sections"]][0] == "hero" and "sign" not in [s["id"] for s in skel["sections"]]


def test_variants_reflect_edits_and_hide_nav_tab_links():
    """테스트 3: 편집 → DV.variants 구역 순서 반영, 숨긴 구역으로 가는 내비·탭 링크 0개."""
    from app.services import site_render as SR

    card = _cafe_card()
    bp = _blueprint(card)
    edits = LE.normalize({"order": ["around", "menu", "space", "inquiry"],
                          "hidden": ["space"], "added": ["sign"]}, bp, 0)
    card["layout_edits"] = {"v1": edits}
    vs = DV.variants(card)
    assert [v["id"] for v in vs] == ["v1", "v2", "v3"]
    v1 = next(v for v in vs if v["id"] == "v1")
    ids = [s["id"] for s in v1["spec"]["sections"]]
    assert ids[0] == "hero" and "space" not in ids and "sign" in ids
    assert ids.index("around") < ids.index("menu")
    # 내비 링크가 숨긴 구역으로 가지 않음
    nav_hrefs = [l.get("href", "") for l in (v1["spec"].get("navbar") or {}).get("links", [])]
    assert not any(h.endswith("-space") for h in nav_hrefs)

    # 앱 탭(v3 앱형): menu 숨기면 탭에도 없음
    card3 = _cafe_card()
    bp3 = AT.blueprint(card3)
    pos3 = 2
    base3 = ["hero"] + [n["id"] for n in bp3["strategies"][pos3]["sections"]]
    assert "menu" in base3
    edits3 = LE.normalize({"hidden": ["menu"]}, bp3, pos3)
    card3["layout_edits"] = {"v3": edits3}
    vs3 = DV.variants(card3)
    app = next(v for v in vs3 if v["id"] == "v3")
    assert app["spec"].get("layout") == "app"
    nav3 = [l.get("href", "") for l in (app["spec"].get("navbar") or {}).get("links", [])]
    assert not any(h.endswith("-menu") for h in nav3)
    body_ids = {f"{s.get('type')}-title-{s.get('id')}" for s in app["spec"]["sections"]}
    tabs = SR._app_tabs(app["spec"].get("navbar") or {}, app["spec"].get("actionbar") or {}, body_ids)
    assert not any(t.get("href", "").endswith("-menu") for t in tabs)
    html = SR.render_site(app["spec"], site_key="k")
    assert "title-menu" not in html


def test_old_edits_on_new_blueprint_do_not_raise():
    """테스트 4: 청사진이 바뀐 카드(업종 변경)에 옛 편집이 있어도 예외 없음."""
    cafe = _cafe_card()
    old = {"order": ["sign", "menu", "around", "inquiry"], "hidden": ["space"], "added": ["space"]}
    academy = _academy_card()
    academy["layout_edits"] = {"v1": copy.deepcopy(old), "v2": copy.deepcopy(old), "v3": copy.deepcopy(old)}
    bp = AT.blueprint(academy)
    assert bp is not None
    # 순수 함수들이 옛 id를 조용히 버림
    for pos in range(3):
        assert LE.normalize(old, bp, pos) is None or isinstance(LE.normalize(old, bp, pos), dict)
        skel = SD.skeleton(bp, pos)
        LE.apply(skel, bp, pos, old)
        LE.sections(bp, pos, old)
        LE.addable(bp, pos, old)
    vs = DV.variants(academy)
    assert len(vs) == 3


def test_added_goes_right_before_inquiry():
    """더한 구역은 inquiry 바로 앞에 (A-dinein v1 + sign)."""
    card = _cafe_card()
    bp = _blueprint(card)
    cleaned = LE.normalize({"added": ["sign"]}, bp, 0)
    assert cleaned is not None
    assert cleaned["order"].index("sign") + 1 == cleaned["order"].index("inquiry")
    secs = LE.sections(bp, 0, {"added": ["sign"]})
    ids = [s["id"] for s in secs]
    assert ids.index("sign") + 1 == ids.index("inquiry")
