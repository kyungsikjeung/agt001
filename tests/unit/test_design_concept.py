"""디자인 컨셉 잡기: AI는 목록 안에서만 고르고, 실패하면 업종 규칙 컨셉. 말로 고치기는 컨셉 값만 바꾼다."""
import json

from app import llm
from app.services import design, design_concept as DC, design_variants as DV
from app.services import prd_engine as E
from app.services import prd_schema as S


def _card(ind="restaurant"):
    card = E.new_card()
    card["industry"] = ind
    E._put(card, "business_type", "식당", S.FILLED, 1)
    E._put(card, "shop_name", "황남밥상", S.FILLED, 1)
    E._put(card, "offerings", ["김치찌개", "계란말이"], S.FILLED, 1)
    E._put(card, "hours", "매일 11~20시", S.FILLED, 1)
    return card


def test_ai_values_outside_lists_are_ignored(monkeypatch):
    bad = {"name": "황금빛 만찬", "mood": ["따뜻한", "푸짐한", "정겨운"], "palette": "neon-pink", "font_pair": "comic",
           "density": "roomy", "radius": "round", "lead": "offerings", "reason": "창업 30년 노포라서요"}
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: json.dumps(bad, ensure_ascii=False))
    c = DC.make(_card())
    assert c["source"] == "ai" and c["name"] == "황금빛 만찬"
    assert c["palette"] == "tomato" and c["font_pair"] == "gothic-strong"  # 목록 밖 값은 규칙 값 그대로
    assert c["density"] == "roomy" and c["radius"] == "round"
    assert "30" not in c["reason"]  # 사장님이 말하지 않은 숫자가 든 이유는 버린다


def test_ai_failure_falls_back_to_rule(monkeypatch):
    def boom(*a, **k):
        raise TimeoutError
    monkeypatch.setattr(llm, "chat_json", boom)
    c = DC.make(_card("cafe"))
    assert c["source"] == "rule" and c["palette"] == "coffee" and c["lead"] == "gallery"


def test_keyword_adjust_without_ai(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: "모르겠어요")
    base = DC.rule_concept(_card())
    new, said = DC.adjust(base, "좀 더 고급스럽게 해 주세요")
    assert new["palette"] == "charcoal-gold" and new["font_pair"] == "serif-elegant" and said
    same, said2 = DC.adjust(base, "좋아요")
    assert same == base and said2 == ""


def test_style_request_vs_fact_edit():
    assert DC.is_style_request("더 따뜻한 색으로 바꿔 주세요")
    assert DC.is_style_request("사진 먼저 보여 줘")
    assert not DC.is_style_request("전화번호는 010-1234-5678이에요")


def test_concept_drives_first_variant_and_lead():
    # D43/P3-8: v1=업종 정석(규칙 고정), v2=사장님 분위기(카드 컨셉 반영)
    card = _card()
    card["concept"] = {**DC.rule_concept(card), "palette": "sage", "lead": "offerings"}
    variants = DV.variants(card)
    assert variants[0]["spec"]["tokens"]["palette"] == DC.rule_concept(card)["palette"]
    assert [s["type"] for s in variants[0]["spec"]["sections"]][:2] == ["hero", "offerings"]
    spec = variants[1]["spec"]
    assert spec["tokens"]["palette"] == "sage"
    hero = variants[0]["spec"]["sections"][0]
    assert hero["variant"] == "photo-overlay"  # photo-first: 사진 없어도 기본 그림으로 채운 첫 화면
    assert {"label": "영업", "value": "매일 11~20시"} in hero["content"]["facts"]


def test_concept_board_shows_process(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "generated_dir", tmp_path)
    monkeypatch.setattr(design, "screenshot_many", lambda *a, **k: None)
    card = _card()
    card["concept"] = DC.rule_concept(card)
    design.render_variants("req1", card)
    board = (tmp_path / "req1" / "design" / "index.html").read_text(encoding="utf-8")
    for text in ("정직한 동네 밥상", "대표색", "글꼴", "구성", "시안 3안", "더 고급스럽게", "/design/req1/v2/"):
        assert text in board
    assert "<script" not in board and "<form" not in board


def test_shop_name_is_not_concept_name_and_reason_matches_choices(monkeypatch):
    got = {"name": "황남밥상", "mood": ["따뜻한", "정겨운", "진솔한"], "palette": "coffee", "font_pair": "serif-warm",
           "density": "comfortable", "radius": "soft", "lead": "intro", "reason": "3대째 끓인 국물이라서요"}
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: json.dumps(got, ensure_ascii=False))
    c = DC.make(_card())
    assert c["name"] != "황남밥상"
    assert "3대째" not in c["reason"] and "소개 먼저" in c["reason"]  # 고른 값으로 만든 이유
    card = _card()
    card["said"] = ["3대째 가마솥에 끓여요"]
    assert "3대째" in DC.make(card)["reason"]  # 사장님이 말한 숫자는 써도 된다


def test_validate_concept_accepts_rule_concepts():
    """P3-6: 업종 규칙 컨셉 6개 + 기본값은 검증 통과."""
    for key in ("restaurant", "cafe", "pension", "salon", "academy", "workshop"):
        assert DC.validate_concept(DC._from_rule(key)) == []
    assert DC.validate_concept(DC._from_rule("unknown")) == []


def test_validate_concept_rejects_unknown_token_values():
    """P3-6: 토큰 5종 목록 밖 값은 짚고, _valid()는 base로 되돌린다."""
    base = DC._from_rule("restaurant")
    good = {k: base[k] for k in DC._REQUIRED_KEYS}
    for key, bad_value in (("palette", "neon-pink"), ("font_pair", "comic"),
                           ("density", "super-roomy"), ("radius", "pointy"), ("lead", "reviews")):
        cand = {**good, key: bad_value}
        assert any(key in p and "목록 밖" in p for p in DC.validate_concept(cand)), key
        assert DC._valid(cand, base)[key] == base[key], key


def test_validate_concept_mood_counts():
    """P3-6: 분위기는 3개 — 2개·4개·빈칸 모두 짚고 _valid()도 받아들이지 않는다."""
    base = DC._from_rule("cafe")
    good = {k: base[k] for k in DC._REQUIRED_KEYS}
    for bad_mood in (["따뜻한", "푸짐한"], ["따뜻한", "푸짐한", "정겨운", "고급스러운"], [], ["  ", ""]):
        cand = {**good, "mood": bad_mood}
        assert any("mood" in p for p in DC.validate_concept(cand)), bad_mood
        assert DC._valid(cand, base)["mood"] == base["mood"], bad_mood


def test_validate_concept_mood_item_length():
    """P3-6: 분위기 낱말 8자 초과는 짚는다."""
    base = DC._from_rule("cafe")
    good = {k: base[k] for k in DC._REQUIRED_KEYS}
    cand = {**good, "mood": ["따뜻한", "푸짐한", "아주아주아주긴분위기"]}
    assert any("mood" in p and "8자" in p for p in DC.validate_concept(cand))
    assert DC._valid(cand, base)["mood"] == base["mood"]


def test_validate_concept_name_length():
    """P3-6: 이름 2~16자 — 1자·17자·공백만은 짚고 _valid()도 받아들이지 않는다."""
    base = DC._from_rule("restaurant")
    good = {k: base[k] for k in DC._REQUIRED_KEYS}
    for bad_name in ("밥", "아주아주아주아주아주긴컨셉이름입니다", "   "):
        cand = {**good, "name": bad_name}
        assert any("name" in p for p in DC.validate_concept(cand)), repr(bad_name)
        assert DC._valid(cand, base)["name"] == base["name"], repr(bad_name)


def test_validate_concept_shop_name_ban_both_directions():
    """P3-6: 가게 이름 포함(양방향) 금지 — validate와 _valid가 함께 막는다."""
    base = DC._from_rule("restaurant")
    good = {k: base[k] for k in DC._REQUIRED_KEYS}
    for bad_name in ("황남밥상 이야기", "밥상"):
        cand = {**good, "name": bad_name}
        assert any("가게 이름" in p for p in DC.validate_concept(cand, shop="황남밥상")), bad_name
        assert DC._valid(cand, base, shop="황남밥상")["name"] == base["name"], bad_name


def test_validate_concept_reason_digits_need_said_numbers():
    """P3-6: 사장님이 말하지 않은 숫자가 reason에 있으면 짚고 버린다. 말한 숫자는 둔다."""
    base = DC._from_rule("pension")
    good = {k: base[k] for k in DC._REQUIRED_KEYS}
    bad = {**good, "reason": "창업 30년 노포의 내공을 담았어요"}
    assert any("숫자" in p for p in DC.validate_concept(bad, allowed_digits=frozenset()))
    assert "30" not in DC._valid(bad, base, allowed_digits=frozenset())["reason"]
    ok = {**good, "reason": "3대째 끓인 국물 이야기를 앞에 뒀어요"}
    assert DC.validate_concept(ok, allowed_digits=frozenset({"3"})) == []
    assert DC._valid(ok, base, allowed_digits=frozenset({"3"}))["reason"] == ok["reason"]
    short = {**good, "reason": "짧아요"}
    assert any("reason" in p for p in DC.validate_concept(short))


def test_validate_concept_empty_object_and_non_dict():
    """P3-6: 빈 객체는 8키 모두 비어 있다고 짚는다. dict가 아니면 한 줄로 막는다."""
    problems = DC.validate_concept({})
    for key in DC._REQUIRED_KEYS:
        assert any(p.startswith(f"{key}:") for p in problems), key
    assert DC.validate_concept(["not", "a", "dict"]) == ["명세가 JSON 객체가 아니에요"]
    assert DC._REQUIRED_KEYS == ("name", "mood", "palette", "font_pair", "density", "radius", "lead", "reason")


def test_validate_concept_matches_valid_on_fuzz_cases():
    """P3-6: validate 통과 ⟺ _valid 전면 수용. 불일치 1건도 허용 안 함."""
    base = DC._from_rule("salon")
    shop, allowed = "단정한 손끝", frozenset({"2"})
    cases = [
        {k: base[k] for k in DC._REQUIRED_KEYS},
        {**{k: base[k] for k in DC._REQUIRED_KEYS}, "palette": "nope"},
        {**{k: base[k] for k in DC._REQUIRED_KEYS}, "mood": ["깔끔한"]},
        {**{k: base[k] for k in DC._REQUIRED_KEYS},
         "mood": ["깔끔한", "세련된", "부드러운", "여유로운"]},
        {**{k: base[k] for k in DC._REQUIRED_KEYS}, "name": "x"},
        {**{k: base[k] for k in DC._REQUIRED_KEYS}, "name": "단정한 손끝 특선"},
        {**{k: base[k] for k in DC._REQUIRED_KEYS}, "reason": "2호점의 여유를 담아 정리했어요"},
        {**{k: base[k] for k in DC._REQUIRED_KEYS}, "reason": "10년 단골의 마음을 담았어요"},
        {},
    ]
    for cand in cases:
        problems = DC.validate_concept(cand, shop, allowed)
        accepted = DC._valid(cand, base, shop, allowed)
        if problems == []:
            assert accepted["reason"] == str(cand["reason"]).strip()
            for k in ("palette", "font_pair", "density", "radius", "lead"):
                assert accepted[k] == cand[k], (k, cand)
            assert accepted["name"] == str(cand["name"]).strip()
            assert accepted["mood"] == [str(m).strip() for m in cand["mood"] if str(m).strip()]
        else:
            # 실패 케이스: 지적된 키의 값은 _valid()가 그대로 받아들이지 않는다
            for p in problems:
                key = p.split(":")[0]
                if key in ("palette", "font_pair", "density", "radius", "lead"):
                    assert accepted[key] == base[key], (key, cand)
                elif key == "name":
                    assert accepted["name"] == base["name"], cand
                elif key == "mood":
                    assert accepted["mood"] == base["mood"], cand
                elif key == "reason":
                    raw = str(cand.get("reason") or "").strip()
                    assert not raw or accepted["reason"] != raw, (cand, accepted)


def test_validate_concept_reports_schema_problems():
    """P3-6: 목록 밖 키·분위기 개수·가게 이름·지어낸 숫자를 짚는다."""
    bad = {"name": "황남밥상", "mood": ["따뜻한", "푸짐한"], "palette": "neon-pink",
           "font_pair": "comic", "density": "roomy", "radius": "round",
           "lead": "offerings", "reason": "창업 30년 노포라서요"}
    problems = DC.validate_concept(bad, shop="황남밥상")
    assert any("palette" in p for p in problems)
    assert any("font_pair" in p for p in problems)
    assert any("mood" in p for p in problems)
    assert any("가게 이름" in p for p in problems)
    assert any("숫자" in p for p in problems)
    ok = {"name": "정직한 동네 밥상", "mood": ["따뜻한", "푸짐한", "정겨운"], "palette": "tomato",
          "font_pair": "gothic-strong", "density": "comfortable", "radius": "soft",
          "lead": "offerings", "reason": "메뉴를 가장 먼저 보여 드려요"}
    assert DC.validate_concept(ok, shop="황남밥상", allowed_digits=frozenset()) == []
