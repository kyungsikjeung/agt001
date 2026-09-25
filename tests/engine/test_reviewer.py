"""리뷰어 에이전트: 빠진 요구는 원문 인용이 있을 때만 채우고, 지어낸 인용·사실은 버리고, 어긋난 값은 묻는다."""
import json

import pytest

from app import llm
from app.services import prd_engine as E
from app.services import prd_schema as S

CELLO = "첼로 레슨 사이트요. 문의가 제 카카오톡으로 오게 해 주세요"


@pytest.fixture
def fake(monkeypatch):
    box = {"extract": [], "review": {"missing": [], "conflicts": []}}

    def chat_json(system, user, **kw):
        if system.startswith("너는 웹사이트 요구사항 검토자다"):
            return json.dumps(box["review"], ensure_ascii=False)
        return json.dumps({"updates": box["extract"]}, ensure_ascii=False)

    monkeypatch.setattr(llm, "chat_json", chat_json)
    return box


def _card(fake):
    fake["extract"] = [{"slot": "business_type", "value": "첼로 레슨"}]  # 추출기가 카톡 요구를 놓친 상황
    card = E.new_card()
    E.turn(card, CELLO)
    fake["extract"] = []
    E.turn(card, "시안 먼저")
    return card


def test_reviewer_adds_dropped_feature_with_real_quote(fake):
    card = _card(fake)
    assert not card["slots"].get("features")
    fake["review"] = {"missing": [{"slot": "features", "value": "카카오톡으로 문의 받기", "quote": "문의가 제 카카오톡으로 오게"}],
                      "conflicts": []}
    r = E.review(card)
    assert r["ok"] and "features" in r["added"]
    assert card["slots"]["features"]["by"] == "reviewer"
    assert card["features_judged"]  # 기능 사례집 판정까지 이어진다
    assert "빠진 게 있어 넣었어요" in E.review_text(card)


def test_reviewer_drops_invented_quote_and_fact(fake):
    card = _card(fake)
    fake["review"] = {"missing": [{"slot": "phone", "value": "010-1234-5678", "quote": "전화는 010-1234-5678"},
                                  {"slot": "goal", "value": "수강생 모집", "quote": "수강생 모으고 싶어요"}],
                      "conflicts": []}
    r = E.review(card)
    assert r["added"] == []
    assert card["slots"].get("phone", {}).get("value") in (None, "")


def test_reviewer_conflict_is_asked_not_applied(fake):
    card = _card(fake)
    E._put(card, "business_type", "첼로 수리", S.FILLED, 1)  # 정리가 원문과 다르게 된 상황
    fake["review"] = {"missing": [], "conflicts": [{"slot": "business_type", "said": "첼로 레슨", "quote": "첼로 레슨 사이트요"}]}
    E.review(card)
    assert "확인해 주세요" in E.review_text(card)
    assert card["slots"]["business_type"]["value"] == "첼로 수리"  # 자동으로 고치지 않는다


def test_assumed_values_are_not_conflicts(fake):
    card = _card(fake)
    fake["review"] = {"missing": [], "conflicts": [
        {"slot": "goal", "said": "상담·문의 늘리기 (가정)", "quote": "첼로 레슨 사이트요"},
        {"slot": "business_type", "said": "첼로 레슨", "quote": "첼로 레슨 사이트요"}]}  # 같은 값
    E.review(card)
    assert E.review_text(card) == ""


def test_reviewer_failure_is_silent(fake, monkeypatch):
    card = _card(fake)
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("nim down")))
    r = E.review(card)
    assert r["ok"] is False and E.review_text(card) == ""


def test_said_keeps_recent_and_skips_blocked(fake):
    card = E.new_card()
    E.turn(card, "바카라 홍보 사이트")
    assert card.get("said") in (None, [])
    for i in range(E.SAID_MAX + 5):
        E.turn(card, f"메시지 {i}")
    assert len(card["said"]) == E.SAID_MAX and card["said"][-1] == f"메시지 {E.SAID_MAX + 4}"
