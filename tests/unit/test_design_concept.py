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
    card = _card()
    card["concept"] = {**DC.rule_concept(card), "palette": "sage", "lead": "offerings"}
    spec = DV.variants(card)[0]["spec"]
    assert spec["tokens"]["palette"] == "sage"
    assert [s["type"] for s in spec["sections"]][:2] == ["hero", "offerings"]
    hero = spec["sections"][0]
    assert hero["variant"] == "text-only"  # 사진이 없으면 글자 중심 첫 화면
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
