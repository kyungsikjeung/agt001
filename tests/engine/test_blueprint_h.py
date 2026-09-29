"""웹서비스(H) 청사진 (BUILD_W1_W2 §6 K5). DB 없이 돌아간다.

예약 관리 웹서비스 카드가 원형 H로 판정되고, 청사진 3안이
도입 문의 양식·첫 화면 문의 버튼까지 그려지는지 본다.
"""
import html as H
import re

from app.services import archetype
from app.services import design_variants as DV
from app.services import palette as PAL
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services import site_data
from app.services import site_render as SR

# site_data.resolve이 아는 바인딩 (§1.4).
BINDS = {"hero", "catalog", "staff", "booking", "location", "contact",
         "space_photos", "style_photos", "menu_photos", "order_soon", "none",
         "classes", "timetable", "rooms", "dates", "concerns", "signature"}


def _card():
    """작은 가게 예약 관리 웹서비스 카드."""
    card = E.new_card("webservice")
    E._put(card, "business_type", "예약 관리 웹서비스", S.FILLED, 1)
    E._put(card, "shop_name", "예약잇기", S.FILLED, 1)
    E._put(card, "offerings", ["문자 알림", "노쇼 관리"], S.FILLED, 1)
    price = "문자 알림 월 1만원, 노쇼 관리 월 2만원"
    E._put(card, "price", price, S.FILLED, 1)
    E._record_price_pairs(card, [{"slot": "price", "value": price}], price)
    E._put(card, "phone", "070-8888-9999", S.FILLED, 1)
    E._put(card, "hours", "평일 9~18시 고객센터", S.FILLED, 1)
    E._put(card, "detail", "작은 가게의 예약을 대신 받아주는 서비스예요.", S.FILLED, 1)
    card["turn"] = 1
    return card


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", fragment)))


def _hero_text(doc: str) -> str:
    found = re.findall(r'<section\b[^>]*s-hero[^>]*>.*?</section>', doc, re.S)
    assert found, "첫 화면이 없음"
    return _text(found[0])


def test_webservice_maps_to_h():
    assert archetype.of(_card())[0] == "H"


def test_blueprint_h_loads_with_three_strategies():
    bp = archetype.blueprint(_card())
    assert bp is not None and bp["archetype"] == "H"
    assert bp == archetype.load("H")
    assert len(bp["strategies"]) == 3
    assert [st["tone"] for st in bp["strategies"]] == ["calm", "rich", "rich"]


def test_blueprint_h_follows_contract():
    """K5 계약: 첫 부품 3안 다름·문의 양식 또는 기능 안내가 앞 3칸 안·짙은 띠는 분위기안에만 1개."""
    bp = archetype.load("H")
    assert bp["primary"] == {"label": "도입 문의", "target": "inquiry"}
    assert bp["secondary"] == {"label": "기능 보기", "target": "features"}
    assert bp["actionbar_secondary"] in ("none", "phone")
    variants = set(SR.list_variants())
    firsts = []
    for st in bp["strategies"]:
        sections = st["sections"]
        firsts.append((sections[0]["type"], sections[0]["variant"]))
        # 문의 양식 또는 기능 안내가 앞 3칸 안에 있다.
        head = sections[:3]
        has_inquiry = any(s["id"] == "inquiry" and s["type"] == "contact"
                          and s["variant"] == "form" for s in head)
        has_offerings = any(s["type"] == "offerings" for s in head)
        assert has_inquiry or has_offerings, st["id"]
        # 주요·보조 행동이 그 안의 칸을 가리킨다 (보조는 기능 안내 칸).
        ids = {s["id"] for s in sections}
        assert bp["primary"]["target"] in ids, st["id"]
        assert bp["secondary"]["target"] in ids, st["id"]
        by_id = {s["id"]: s for s in sections}
        assert by_id["inquiry"]["type"] == "contact" and by_id["inquiry"]["variant"] == "form", st["id"]
        assert by_id["features"]["type"] == "offerings", st["id"]
        # 내비 링크는 최대 4개.
        assert sum(1 for s in sections if s.get("nav")) <= 4, st["id"]
        # 짙은 띠는 안마다 최대 1개, 차분한 안에는 없음.
        inverses = sum(1 for s in sections if s.get("tone") == "inverse")
        assert inverses <= 1, st["id"]
        if st["tone"] == "calm":
            assert inverses == 0, st["id"]
        for s in sections:
            assert f"{s['type']}--{s['variant']}" in variants, (st["id"], s["id"])
            assert s["bind"] in BINDS, (st["id"], s["id"])
        # 지도는 있을 때만 (주소 없는 웹서비스가 많아 선택 사항).
        for s in sections:
            if s["type"] == "around":
                assert s.get("optional") is True, (st["id"], s["id"])
        # 사진첩 제목은 "사진첩"이 아니다 (draft_fit generic_heading).
        for s in sections:
            assert s.get("label") != "사진첩", (st["id"], s["id"])
    assert len(set(firsts)) == 3, firsts
    # v1 정석은 기능·요금 분류형이 맨 앞, v2 분위기는 고민 공감이 맨 앞, v3 대비는 요금표가 맨 앞.
    by_id = {st["id"]: st for st in bp["strategies"]}
    assert (by_id["v1"]["sections"][0]["type"], by_id["v1"]["sections"][0]["variant"]) == ("offerings", "categories")
    assert by_id["v1"]["sections"][0]["label"] == "기능·요금"
    assert (by_id["v2"]["sections"][0]["type"], by_id["v2"]["sections"][0]["variant"]) == ("concerns", "bubbles")
    assert (by_id["v3"]["sections"][0]["type"], by_id["v3"]["sections"][0]["variant"]) == ("offerings", "list-price")
    # v2에 사진첩이 있으면 흐르는 띠다.
    for s in by_id["v2"]["sections"]:
        if s["type"] == "gallery":
            assert s["variant"] == "marquee", s["id"]


def test_variants_come_from_blueprint():
    """엔진 3안이 청사진 전략 그대로다."""
    card = _card()
    bp = archetype.load("H")
    items = DV.variants(card)
    assert len(items) == 3
    assert [v["name"] for v in items] == [st["name"] for st in bp["strategies"]][:2] + ["앱형"]  # D56: 3안은 앱형


def test_every_variant_renders_inquiry_form_and_hero_cta():
    """3안 모두 문의 양식과 첫 화면 문의 버튼이 있다."""
    card = _card()
    bp = archetype.load("H")
    for index, st in enumerate(bp["strategies"]):
        spec = site_data.resolve(site_data.skeleton(bp, index), card, archetype="H")
        spec["tokens"]["palette"] = PAL.pick("H", 1)  # 엔진이 palette.pick(① 정석)으로 채우는 값
        doc = SR.render_site(spec, site_key="test-h", title=DV.title_for(card),
                             kind=DV.kind_for(card))
        assert 'id="contact-title-inquiry"' in doc, st["id"]
        assert "문의 보내기" in doc, st["id"]
        assert "문의" in _hero_text(doc), st["id"]
        assert not re.search(r"<h2\b[^>]*>\s*사진첩\s*</h2>", doc), st["id"]
