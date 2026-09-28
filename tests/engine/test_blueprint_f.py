"""개인 전문가(F) 청사진 (BUILD_W1_W2 §6 K2). DB 없이 돌아간다.

출장 사진작가 카드가 원형 F로 판정되고, 청사진 3안이
견적 문의 양식·첫 화면 문의 버튼까지 그려지는지 본다.
"""
import html as H
import re

from app.services import archetype
from app.services import design_variants as DV
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services import site_data
from app.services import site_render as SR

# site_data.resolve이 아는 바인딩 (§1.4).
BINDS = {"hero", "catalog", "staff", "booking", "location", "contact",
         "space_photos", "style_photos", "menu_photos", "order_soon", "none",
         "classes", "timetable", "rooms", "dates", "concerns", "signature"}


def _card():
    """출장 사진작가 카드 (1:1 레슨이 아니라 F로 판정되는 말만 쓴다)."""
    card = E.new_card("individual")
    E._put(card, "business_type", "출장 사진", S.FILLED, 1)
    E._put(card, "shop_name", "빛기록", S.FILLED, 1)
    E._put(card, "offerings", ["프로필 촬영 1시간", "가족 촬영 2시간"], S.FILLED, 1)
    price = "프로필 촬영 1시간 15만원, 가족 촬영 2시간 25만원"
    E._put(card, "price", price, S.FILLED, 1)
    E._record_price_pairs(card, [{"slot": "price", "value": price}], price)
    card["turn"] = 1
    return card


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", fragment)))


def _hero_text(doc: str) -> str:
    found = re.findall(r'<section\b[^>]*s-hero[^>]*>.*?</section>', doc, re.S)
    assert found, "첫 화면이 없음"
    return _text(found[0])


def test_individual_photographer_maps_to_f():
    assert archetype.of(_card())[0] == "F"


def test_blueprint_f_loads_with_three_strategies():
    bp = archetype.blueprint(_card())
    assert bp is not None and bp["archetype"] == "F"
    assert bp == archetype.load("F")
    assert len(bp["strategies"]) == 3
    assert [st["tone"] for st in bp["strategies"]] == ["calm", "rich", "rich"]


def test_blueprint_f_follows_contract():
    """K2 계약: 첫 부품 3안 다름·문의 양식이 앞 4칸 안·짙은 띠는 분위기안에만 1개."""
    bp = archetype.load("F")
    assert bp["primary"] == {"label": "견적 문의", "target": "inquiry"}
    assert bp["secondary"] == {"label": "작업 보기", "target": "works"}
    variants = set(SR.list_variants())
    firsts = []
    for st in bp["strategies"]:
        sections = st["sections"]
        firsts.append((sections[0]["type"], sections[0]["variant"]))
        # 문의 양식이 앞 4칸 안에 있다.
        pos = [i for i, s in enumerate(sections)
               if s["id"] == "inquiry" and s["type"] == "contact" and s["variant"] == "form"]
        assert len(pos) == 1 and pos[0] < 4, st["id"]
        # 주요·보조 행동이 그 안의 칸을 가리킨다.
        ids = {s["id"] for s in sections}
        assert bp["primary"]["target"] in ids, st["id"]
        assert bp["secondary"]["target"] in ids, st["id"]
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
        gallery = [s for s in sections if s["type"] == "gallery"]
        assert gallery and all(s["label"] == "작업" for s in gallery), st["id"]
    assert len(set(firsts)) == 3, firsts


def test_every_variant_renders_inquiry_form_and_hero_cta():
    """3안 모두 문의 양식과 첫 화면 문의 버튼이 있다."""
    card = _card()
    bp = archetype.load("F")
    for index, st in enumerate(bp["strategies"]):
        spec = site_data.resolve(site_data.skeleton(bp, index), card, archetype="F")
        spec["tokens"]["palette"] = "sage"  # 엔진이 palette.pick(① 정석)으로 채우는 값
        doc = SR.render_site(spec, site_key="test-f", title=DV.title_for(card),
                             kind=DV.kind_for(card))
        assert 'id="contact-title-inquiry"' in doc, st["id"]
        assert "문의 보내기" in doc, st["id"]
        assert "문의" in _hero_text(doc), st["id"]
        assert not re.search(r"<h2\b[^>]*>\s*사진첩\s*</h2>", doc), st["id"]
