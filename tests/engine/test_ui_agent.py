"""UI 에이전트 조각 검증·적용·개선·원형 판정 테스트 (J11).

LLM은 가짜로 바꾼다. DB를 쓰지 않는다.
"""
import json
import time

from app import llm
from app.services import archetype, design_variants as DV, prd_engine as E, prd_schema as S, ui_agent


def _cafe_card():
    """규칙 3안이 나오는 카페 카드."""
    card = E.new_card()
    E._put(card, "business_type", "카페", S.FILLED, 1)
    E._put(card, "shop_name", "모퉁이 커피", S.FILLED, 1)
    E._put(card, "phone", "010-1234-5678", S.FILLED, 1)
    E._put(card, "hours", "매일 10시~22시", S.FILLED, 1)
    E._put(card, "location", "서울 마포구 연남로 12", S.FILLED, 1)
    E._put(card, "offerings", ["아메리카노", "라떼"], S.FILLED, 1)
    E._put(card, "detail", "조용한 동네 카페", S.FILLED, 1)
    return card


def _other_card():
    card = E.new_card()
    E._put(card, "business_type", "필라테스", S.FILLED, 1)
    E._put(card, "shop_name", "바른 몸", S.FILLED, 1)
    E._put(card, "offerings", ["개인 레슨"], S.FILLED, 1)
    return card


def _fake_chat_json(monkeypatch, replies):
    """replies를 차례로 돌려주는 가짜. 부른 system·user를 calls에 남긴다."""
    calls = []

    def fake(system, user, **kw):
        calls.append((system, user, kw))
        reply = replies[min(len(calls) - 1, len(replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(llm, "chat_json", fake)
    return calls


def test_validate_drops_bad_fields():
    card = _cafe_card()
    variants = DV.variants(card)
    v1 = variants[0]["spec"]
    ids = [s["id"] for s in v1["sections"]]
    raw = {"v1": {
        "palette": "hot-pink",  # 후보 밖
        "tone": "loud",  # 허용 밖
        "order": ids[:-1],  # 빠짐
        "hide": ["menu", "around", "space"],  # 앞의 둘은 못 숨김, space(gallery)는 됨
        "labels": {"menu": "0123456789013", "space": "공간 안내"},
        "subtitle": "아메리카노 99999원",  # 카드에 없는 숫자
        "inverse": "no-such-id",
    }}
    cleaned = ui_agent.validate_patch(card, variants, raw)["v1"]
    assert "palette" not in cleaned and "tone" not in cleaned
    assert "order" not in cleaned and "subtitle" not in cleaned and "inverse" not in cleaned
    assert cleaned["hide"] == ["space"]
    assert cleaned["labels"] == {"space": "공간 안내"}


def test_validate_keeps_good_subtitle_with_card_number():
    card = _cafe_card()
    variants = DV.variants(card)
    raw = {"v1": {"subtitle": "매일 10시에 열어요"}}  # 10은 영업시간 사실
    assert ui_agent.validate_patch(card, variants, raw)["v1"]["subtitle"] == "매일 10시에 열어요"


def test_apply_applies_valid_and_keeps_copy():
    card = _cafe_card()
    variants = DV.variants(card)
    before = json.dumps(variants[0]["spec"], ensure_ascii=False)
    card["design_patch"] = {"v1": {
        "palette": "coffee",
        "tone": "calm",
        "order": ["around", "space", "menu", "inquiry"],
        "labels": {"menu": "대표 메뉴"},
        "subtitle": "모퉁이에서 내리는 커피",
        "inverse": None,
    }}
    out = ui_agent.apply(card, variants)
    assert len(out) == 3
    spec = out[0]["spec"]
    assert spec["tokens"]["palette"] == "coffee"
    assert [s["id"] for s in spec["sections"] if s["type"] != "hero"] == ["around", "space", "menu", "inquiry"]
    menu = next(s for s in spec["sections"] if s["id"] == "menu")
    assert menu["label"] == "대표 메뉴"
    hero = next(s for s in spec["sections"] if s["type"] == "hero")
    assert hero["content"]["subtitle"] == "모퉁이에서 내리는 커피"
    assert all(s.get("tone") != "inverse" for s in spec["sections"])
    # 입력은 그대로(사본을 돌려준다)
    assert json.dumps(variants[0]["spec"], ensure_ascii=False) == before


def test_apply_inverse_single_place():
    card = _cafe_card()
    variants = DV.variants(card)
    card["design_patch"] = {"v2": {"tone": "rich", "inverse": "menu"}}
    spec = ui_agent.apply(card, variants)[1]["spec"]
    marked = [s["id"] for s in spec["sections"] if s.get("tone") == "inverse"]
    assert marked == ["menu"]


def test_apply_never_raises():
    card = _cafe_card()
    variants = DV.variants(card)
    for bad in (None, "nope", {"v1": "nope"}, {"v9": {"palette": "coffee"}}, {"v1": {"order": "menu"}}):
        card["design_patch"] = bad
        out = ui_agent.apply(card, variants)
        assert len(out) == 3


def test_improve_success(monkeypatch):
    card = _cafe_card()
    variants = DV.variants(card)
    calls = _fake_chat_json(monkeypatch, [json.dumps({"v1": {"labels": {"menu": "대표 메뉴"}}, "v2": {}, "v3": {}})])
    patch = ui_agent.improve(card, variants, timeout_sec=20)
    assert patch["v1"] == {"labels": {"menu": "대표 메뉴"}}
    assert patch["v2"] == {} and patch["v3"] == {}
    assert patch["made_at"] and patch["model"]
    assert len(calls) == 1
    # 전화·주소는 프롬프트에 넣지 않는다
    assert "010-1234" not in calls[0][0] + calls[0][1]
    assert "연남로" not in calls[0][0] + calls[0][1]


def test_improve_retries_once_with_reason(monkeypatch):
    card = _cafe_card()
    variants = DV.variants(card)
    # 첫 화면 부제를 바꾸면 카드 사실(소개 말)이 사라져 안전 검사 탈락
    bad = json.dumps({"v1": {"subtitle": "모퉁이에서 내리는 커피"}})
    calls = _fake_chat_json(monkeypatch, [bad, json.dumps({"v1": {}, "v2": {}, "v3": {}})])
    patch = ui_agent.improve(card, variants, timeout_sec=20)
    assert patch is not None and patch["v1"] == {}
    assert len(calls) == 2
    assert "사유" in calls[1][1]  # 두 번째 호출에 탈락 사유가 붙는다


def test_improve_none_on_llm_error(monkeypatch):
    card = _cafe_card()
    _fake_chat_json(monkeypatch, [RuntimeError("boom")])
    assert ui_agent.improve(card, DV.variants(card), timeout_sec=20) is None


def test_improve_none_on_timeout(monkeypatch):
    card = _cafe_card()
    variants = DV.variants(card)

    def slow(system, user, **kw):
        time.sleep(0.3)
        return json.dumps({"v1": {}, "v2": {}, "v3": {}})

    monkeypatch.setattr(llm, "chat_json", slow)
    assert ui_agent.improve(card, variants, timeout_sec=0.05) is None


def test_judge_other_sets_override(monkeypatch):
    card = _other_card()
    assert archetype.of(card)[0] == "A"
    _fake_chat_json(monkeypatch, [json.dumps({"archetype": "B", "reason": "1:1 레슨 예약"})])
    assert archetype.judge(card) == "B"
    assert card["archetype_override"] == "B"
    assert archetype.of(card)[0] == "B"


def test_judge_skips_non_other(monkeypatch):
    card = _cafe_card()
    calls = _fake_chat_json(monkeypatch, [json.dumps({"archetype": "B", "reason": "x"})])
    assert archetype.judge(card) is None
    assert "archetype_override" not in card and not calls


def test_judge_none_on_failure(monkeypatch):
    card = _other_card()
    _fake_chat_json(monkeypatch, [RuntimeError("boom")])
    assert archetype.judge(card) is None
    assert "archetype_override" not in card
    _fake_chat_json(monkeypatch, [json.dumps({"archetype": "Z"})])
    assert archetype.judge(card) is None
