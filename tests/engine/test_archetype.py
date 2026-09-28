"""원형 판정과 청사진 계약 테스트 (BUILD_W1_W2 §1.2·§1.3, J4).

카드 구조 데이터는 card["data"]에 직접 넣어 돈다 (J1a와 독립).
"""
from app.services import archetype
from app.services import site_render

# 청사진 파일 이름 → (원형, 모드).
FILES = {
    "A-dinein": ("A", "dinein"),
    "A-pickup": ("A", "pickup"),
    "B-team": ("B", "team"),
    "B-solo": ("B", "solo"),
}

# §1.4 바인딩 목록.
BINDS = {"hero", "catalog", "staff", "booking", "location", "contact",
         "space_photos", "style_photos", "menu_photos", "order_soon", "none",
         "classes", "timetable", "rooms", "dates", "concerns", "signature"}

# 첫 화면에 쓸 수 있는 변형 (짧은 이름).
HEROS = {"photo-overlay", "photo-side", "cinematic", "arch"}


def _card(industry, mode):
    return {"industry": industry, "slots": {}, "data": {"mode": mode}}


def test_industry_to_archetype():
    """업종 키 → 원형 글자."""
    cases = {"cafe": "A", "restaurant": "A", "salon": "B", "pension": "C",
             "academy": "D", "workshop": "E", "individual": "F",
             "group": "G", "webservice": "H", "other": "A"}
    for industry, want in cases.items():
        assert archetype.of(_card(industry, "dinein"))[0] == want


def test_unknown_industry_falls_back_to_a():
    assert archetype.of(_card("pc방", "dinein"))[0] == "A"
    assert archetype.of(_card(None, "dinein"))[0] == "A"


def test_mode_comes_from_card_data():
    """모드는 card["data"]["mode"]를 그대로 쓴다."""
    assert archetype.of(_card("cafe", "pickup")) == ("A", "pickup")
    assert archetype.of(_card("salon", "solo")) == ("B", "solo")


def test_blueprint_found_and_missing(tmp_path, monkeypatch):
    """<원형>-<모드>가 있으면 읽고, 없으면 None. A~H 모두 청사진이 있어 빈 폴더로 '없음'을 본다."""
    assert archetype.blueprint(_card("cafe", "dinein"))["mode"] == "dinein"
    assert archetype.blueprint(_card("salon", "team"))["mode"] == "team"
    for key in ("workshop", "individual", "group", "webservice"):
        assert archetype.blueprint(_card(key, "")) is not None
    archetype.load.cache_clear()
    monkeypatch.setattr(archetype, "_blueprint_dir", lambda: tmp_path)
    try:
        assert archetype.blueprint(_card("group", "")) is None
    finally:
        archetype.load.cache_clear()


def test_load_accepts_name_with_or_without_suffix():
    assert archetype.load("A-dinein") == archetype.load("A-dinein.json")


def _hero_key(short):
    return short if "--" in short else "hero--" + short


def test_blueprints_follow_contract():
    """청사진 4개가 §1.3 계약을 지킨다."""
    variants = set(site_render.list_variants())
    for name in FILES:
        bp = archetype.load(name)
        strategies = bp["strategies"]
        # ① 전략은 정확히 3개.
        assert len(strategies) == 3, name
        assert [s["tone"] for s in strategies][0] == "calm", name
        assert [s["tone"] for s in strategies][1] == "rich", name
        # v1 정석은 짙은 띠 없음, v2 분위기는 짙은 띠 1곳.
        inverses = [sum(1 for s in st["sections"] if s.get("tone") == "inverse")
                    for st in strategies]
        assert inverses[0] == 0, name
        assert inverses[1] == 1, name
        # ⑤ 짙은 띠는 전략당 최대 1개.
        assert all(n <= 1 for n in inverses), name
        # v3 첫 화면은 v1과 다르게.
        assert strategies[2]["hero"] != strategies[0]["hero"], name
        for st in strategies:
            # 첫 화면은 허용된 4개 중 하나.
            hero = st["hero"]
            assert hero in HEROS or _hero_key(hero) in HEROS, (name, st["id"])
            assert _hero_key(hero) in variants, (name, st["id"])
            ids = {s["id"] for s in st["sections"]}
            # ⑥ primary·secondary는 그 전략의 섹션 id(또는 order-soon).
            for key in ("primary", "secondary"):
                target = bp[key]["target"]
                assert target in ids or target == "order-soon", (name, st["id"], key)
            # ⑦ nav는 최대 4개.
            assert sum(1 for s in st["sections"] if s.get("nav")) <= 4, (name, st["id"])
            for s in st["sections"]:
                # ② type--variant가 렌더러에 있음.
                assert f"{s['type']}--{s['variant']}" in variants, (name, st["id"], s["id"])
                # ③ bind가 §1.4 목록 안.
                assert s["bind"] in BINDS, (name, st["id"], s["id"])
        # ④ 두 번째 섹션(hero 다음)이 3안 모두 다름 (종류+변형으로 본다: A-dinein v1 메뉴판과 v3 시그니처 카드처럼 종류는 같아도 됨).
        seconds = [(st["sections"][0]["type"], st["sections"][0]["variant"]) for st in strategies]
        assert len(set(seconds)) == 3, (name, seconds)


def test_pickup_menu_has_order_flag_and_order_soon_last():
    """픽업 청사진은 메뉴에 order 표시, 맨 끝에 order--soon."""
    for name in ("A-pickup",):
        for st in archetype.load(name)["strategies"]:
            menus = [s for s in st["sections"] if s["id"] == "menu"]
            assert menus and all(s.get("order") is True for s in menus), (name, st["id"])
            last = st["sections"][-1]
            assert last["type"] == "order" and last["variant"] == "soon", (name, st["id"])
            assert last["bind"] == "order_soon", (name, st["id"])


def test_solo_staff_variant_is_solo():
    """B-solo의 staff 섹션은 variant solo."""
    for st in archetype.load("B-solo")["strategies"]:
        staff = [s for s in st["sections"] if s["bind"] == "staff"]
        assert staff and all(s["variant"] == "solo" for s in staff), st["id"]


def test_chat_card_without_industry_uses_business_type():
    # 대화로 만든 카드는 industry가 None이고 업종은 business_type에서 계산된다
    from app.services import prd_engine as E, prd_schema as S
    card = E.new_card()
    E._put(card, "business_type", "미용실", S.FILLED, 1)
    E._put(card, "staff", ["원장 김미용(컷)", "실장 박하나(염색)"], S.FILLED, 1)
    assert archetype.of(card) == ("B", "team")


# 낱말표 판정 (G2). 원형마다 2개 이상, 직접 함수로 본다.
KEYWORD_CASES = {
    "A": ["반찬가게", "수제 케이크 주문"],
    "B": ["필라테스 1:1", "반려견 미용"],
    "C": ["파티룸 대관", "공유오피스"],
    "D": ["어린이 수영 교실", "놀이 어린이집"],
    "E": ["비누 만들기 체험", "원데이 베이킹"],
    "F": ["세무사", "웨딩 사진"],
    "G": ["청년 봉사단", "독서 모임"],
    "H": ["법률 상담 솔루션", "동네 심부름 SaaS"],
}


def test_keyword_archetype_covers_all_archetypes():
    for want, words in KEYWORD_CASES.items():
        assert len(words) >= 2, want
        for word in words:
            assert archetype.keyword_archetype(word) == want, (word, want)


def test_keyword_archetype_none_for_unknown():
    assert archetype.keyword_archetype("동네 가게") is None
    assert archetype.keyword_archetype("") is None
    assert archetype.keyword_archetype(None) is None


def _other_card(business_type):
    from app.services import prd_engine as E, prd_schema as S
    card = E.new_card()
    E._put(card, "business_type", business_type, S.FILLED, 1)
    return card


def test_other_uses_keyword_when_no_override():
    assert archetype.of(_other_card("반려견 미용"))[0] == "B"
    assert archetype.of(_other_card("수제 케이크 주문"))[0] == "A"


def test_override_beats_keyword():
    card = _other_card("세무사")
    card["archetype_override"] = "B"
    assert archetype.of(card)[0] == "B"


def test_archetype_cases_file_scores_80_percent():
    """evals/archetype_cases.json 규칙 판정이 80% 이상."""
    import json
    from pathlib import Path
    cases = json.loads((Path(__file__).resolve().parents[2]
                        / "evals" / "archetype_cases.json").read_text(encoding="utf-8"))
    assert len(cases) >= 30
    hits = sum(1 for c in cases if archetype.of(_other_card(c["business_type"]))[0] == c["expect"])
    assert hits / len(cases) >= 0.8, f"{hits}/{len(cases)}"


def test_flower_shop_is_retail_not_workshop():
    from app.services import prd_schema as S
    assert S.industry_for("꽃집").key == "other" and S.industry_for("플라워 클래스").key == "workshop"
    assert S.industry_for("꽃집 원데이 클래스").key == "workshop"
