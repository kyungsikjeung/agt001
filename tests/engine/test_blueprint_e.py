"""공방(E) 청사진 계약 테스트 (BUILD_W1_W2 §6 K1). DB 없이 돌아간다."""
from app.services import archetype
from app.services import card_data
from app.services import design_variants as DV
from app.services import palette as PAL
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services import site_data as SD
from app.services import site_render as SR

# §1.4 바인딩 목록 (test_archetype.py와 같은 집합).
BINDS = {"hero", "catalog", "staff", "booking", "location", "contact",
         "space_photos", "style_photos", "menu_photos", "order_soon", "none",
         "classes", "timetable", "rooms", "dates", "concerns", "signature"}


def _card():
    card = E.new_card("workshop")
    E._put(card, "shop_name", "흙내음 도예 공방", S.FILLED, 1)
    E._put(card, "business_type", "도예 공방", S.FILLED, 1)
    E._put(card, "offerings", ["원데이 도예 토 14시 6명", "4주 정규반 화목 19시 8명"], S.FILLED, 1)
    card["price_pairs"] = {"원데이 도예": "5만원", "4주 정규반": "20만원"}
    card["turn"] = 1
    return card


def test_workshop_maps_to_archetype_e():
    assert archetype.of(_card())[0] == "E"


def test_blueprint_e_loads_and_follows_contract():
    bp = archetype.blueprint(_card())
    assert bp is not None and bp["archetype"] == "E" and bp["mode"] == ""
    assert bp["primary"] == {"label": "수업 신청", "target": "booking"}
    assert bp["secondary"] == {"label": "수업 보기", "target": "classes"}
    strategies = bp["strategies"]
    assert len(strategies) == 3
    assert [s["tone"] for s in strategies] == ["calm", "rich", "rich"]
    # 정석(v1)은 짙은 띠 없음, 분위기·대비용은 최대 1개.
    inverses = [sum(1 for s in st["sections"] if s.get("tone") == "inverse")
                for st in strategies]
    assert inverses[0] == 0
    assert all(n <= 1 for n in inverses)
    variants = set(SR.list_variants())
    for st in strategies:
        assert f"hero--{st['hero']}" in variants, st["id"]
        ids = {s["id"] for s in st["sections"]}
        assert bp["primary"]["target"] in ids, st["id"]
        assert bp["secondary"]["target"] in ids, st["id"]
        assert sum(1 for s in st["sections"] if s.get("nav")) <= 4, st["id"]
        # 수업 신청·수업 안내는 첫 3개 안에 있어야 손님이 바로 행동한다.
        first3 = [s["id"] for s in st["sections"][:3]]
        assert "booking" in first3 or "classes" in first3, (st["id"], first3)
        for s in st["sections"]:
            assert f"{s['type']}--{s['variant']}" in variants, (st["id"], s["id"])
            assert s["bind"] in BINDS, (st["id"], s["id"])
    # hero 다음 섹션이 3안 모두 다름 (종류+변형으로 본다).
    seconds = [(st["sections"][0]["type"], st["sections"][0]["variant"]) for st in strategies]
    assert len(set(seconds)) == 3, seconds
    # 사진첩 제목은 "사진첩"이 아니다 (draft_fit generic_heading).
    for st in strategies:
        for s in st["sections"]:
            if s["type"] == "gallery":
                assert s.get("label") in ("작품", "공방"), (st["id"], s.get("label"))


def test_workshop_classes_parsed_like_academy():
    classes = card_data.build(_card())["classes"]
    assert classes[0] == {"name": "원데이 도예", "target": "", "days": "토",
                          "time": "14:00", "capacity": "6명", "fee": "5만원", "source": "owner"}
    assert classes[1] == {"name": "4주 정규반", "target": "", "days": "화·목",
                          "time": "19:00", "capacity": "8명", "fee": "20만원", "source": "owner"}


def test_design_variants_gives_three():
    assert len(DV.variants(_card())) == 3


def _rendered(strategy_index):
    card = _card()
    bp = archetype.blueprint(card)
    spec = SD.skeleton(bp, strategy_index)
    spec["tokens"]["palette"] = PAL.pick("E", 1)
    resolved = SD.resolve(spec, card, archetype="E")
    html = SR.render_site(resolved, site_key="e", title=DV.title_for(card), kind=DV.kind_for(card))
    return resolved, html


def test_classes_render_as_s_class_cards_and_primary_cta():
    for pos in range(3):
        resolved, html = _rendered(pos)
        assert html.count('<li class="s-class">') == 2, pos
        assert "원데이 도예" in html and "4주 정규반" in html, pos
        assert "신청" in resolved["navbar"]["cta"]["label"], pos
