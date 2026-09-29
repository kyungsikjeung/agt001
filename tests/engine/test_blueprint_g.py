"""모임·공동체(G) 청사진 계약 테스트 (BUILD_W1_W2 §6 K4). DB 없이 돌아간다.

동네 독서 모임 카드가 원형 G로 판정되고, 청사진 3안이
모임 안내·참여 신청·모임 모습까지 그려지는지 본다.
"""
import html as H
import re

from app.services import archetype
from app.services import design_variants as DV
from app.services import palette as PAL
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services import site_data as SD
from app.services import site_render as SR

# §1.4 바인딩 목록 (test_blueprint_e.py와 같은 집합).
BINDS = {"hero", "catalog", "staff", "booking", "location", "contact",
         "space_photos", "style_photos", "menu_photos", "order_soon", "none",
         "classes", "timetable", "rooms", "dates", "concerns", "signature"}


def _card():
    card = E.new_card("group")
    E._put(card, "shop_name", "월빛독서모임", S.FILLED, 1)
    E._put(card, "business_type", "독서 모임", S.FILLED, 1)
    E._put(card, "offerings", ["월요 고전 읽기", "금요 신간 나누기"], S.FILLED, 1)
    price = "월요 고전 읽기 월 2만원, 금요 신간 나누기 월 2만원"
    E._put(card, "price", price, S.FILLED, 1)
    E._record_price_pairs(card, [{"slot": "price", "value": price}], price)
    E._put(card, "staff", ["이책사랑 대표(진행)"], S.FILLED, 1)
    E._put(card, "phone", "010-6666-7777", S.FILLED, 1)
    E._put(card, "hours", "월·금 19~21시", S.FILLED, 1)
    E._put(card, "location", "서울 마포구 동교로 50", S.FILLED, 1)
    E._put(card, "detail", "매주 모여 책을 읽고 나누는 동네 독서 모임이에요.", S.FILLED, 1)
    card["turn"] = 1
    return card


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", fragment)))


def _hero_text(doc: str) -> str:
    found = re.findall(r'<section\b[^>]*s-hero[^>]*>.*?</section>', doc, re.S)
    assert found, "첫 화면이 없음"
    return _text(found[0])


def test_group_maps_to_archetype_g():
    assert archetype.of(_card())[0] == "G"


def test_blueprint_g_loads_with_three_strategies():
    bp = archetype.blueprint(_card())
    assert bp is not None and bp["archetype"] == "G"
    assert bp == archetype.load("G")
    assert len(bp["strategies"]) == 3
    assert [st["tone"] for st in bp["strategies"]] == ["calm", "rich", "rich"]


def test_blueprint_g_follows_contract():
    """K4 계약: 첫 부품 3안 다름·참여 신청이 앞 3칸 안·짙은 띠는 분위기안에만 1개."""
    bp = archetype.load("G")
    assert bp["primary"] == {"label": "참여 신청", "target": "booking"}
    assert bp["secondary"] == {"label": "모임 보기", "target": "meetings"}
    assert bp["actionbar_secondary"] == "phone"
    variants = set(SR.list_variants())
    firsts = []
    for st in bp["strategies"]:
        sections = st["sections"]
        firsts.append((sections[0]["type"], sections[0]["variant"]))
        # 참여 신청이 앞 3칸 안에 있다.
        pos = [i for i, s in enumerate(sections) if s["id"] == "booking"]
        assert len(pos) == 1 and pos[0] < 3, (st["id"], pos)
        assert sections[pos[0]]["type"] == "booking", st["id"]
        assert sections[pos[0]]["variant"] == "slots", st["id"]
        assert sections[pos[0]]["bind"] == "booking", st["id"]
        assert sections[pos[0]].get("label") == "참여 신청", st["id"]
        # 모임 안내는 offerings--categories + catalog 바인딩이다.
        programs = [s for s in sections
                    if s["type"] == "offerings" and s["variant"] == "categories"]
        assert programs and programs[0].get("label") == "모임 안내", st["id"]
        assert all(s.get("bind") == "catalog" for s in programs), st["id"]
        assert bp["secondary"]["target"] in {s["id"] for s in sections}, st["id"]
        # 주요 행동이 그 안의 칸을 가리킨다.
        ids = {s["id"] for s in sections}
        assert bp["primary"]["target"] in ids, st["id"]
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
        # 모임 사진첩 제목은 "모임 모습"이다.
        gallery = [s for s in sections if s["type"] == "gallery"]
        assert gallery and all(s.get("label") == "모임 모습" for s in gallery), st["id"]
        # 둘러보기 지도와 문의 양식이 있다.
        assert any(s["type"] == "around" and s["variant"] == "map"
                   and s.get("bind") == "location" for s in sections), st["id"]
        assert any(s["id"] == "inquiry" and s["type"] == "contact"
                   and s["variant"] == "form" and s.get("bind") == "none"
                   for s in sections), st["id"]
        # 운영진은 staff--solo + staff 바인딩 + 선택 칸이다.
        hosts = [s for s in sections if s.get("bind") == "staff"]
        assert len(hosts) == 1 and hosts[0]["variant"] == "solo", st["id"]
        assert hosts[0].get("optional") is True, st["id"]
    # 첫 부품이 3안 모두 다르고, 분위기안은 흐르는 띠(marquee)다.
    assert len(set(firsts)) == 3, firsts
    assert bp["strategies"][1]["sections"][0]["variant"] == "marquee", firsts


def test_design_variants_come_from_blueprint_not_legacy():
    """3안이 청사진 전략(이름·여정)에서 나온다."""
    card = _card()
    bp = archetype.load("G")
    got = DV.variants(card)
    assert len(got) == 3
    assert [v["name"] for v in got] == [s["name"] for s in bp["strategies"]][:2] + ["앱형"]  # D56: 3안은 앱형
    assert [v["summary"] for v in got][:2] == [s["journey"] for s in bp["strategies"]][:2]


def test_every_variant_renders_booking_and_hero_cta():
    """3안 모두 참여 신청 칸과 첫 화면 참여 버튼이 있다."""
    card = _card()
    bp = archetype.load("G")
    for index, st in enumerate(bp["strategies"]):
        spec = SD.resolve(SD.skeleton(bp, index), card, archetype="G")
        spec["tokens"]["palette"] = PAL.pick("G", 1)  # 엔진이 palette.pick(① 정석)으로 채우는 값
        doc = SR.render_site(spec, site_key="test-g", title=DV.title_for(card),
                             kind=DV.kind_for(card))
        assert 'id="booking-title-booking"' in doc, st["id"]
        assert "참여 신청" in doc, st["id"]
        assert "참여" in _hero_text(doc), st["id"]
        assert "모임 모습" in doc, st["id"]
        assert not re.search(r"<h2\b[^>]*>\s*사진첩\s*</h2>", doc), st["id"]
