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
    g = E.close_gate(card)
    assert card["slots"]["business_type"]["value"] == "첼로 수리"  # 자동으로 고치지 않는다
    q = g["question"]
    assert q["kind"] == "conflict" and q["options"] == ["첼로 레슨", "첼로 수리"] and "어느 쪽이 맞나요" in q["text"]
    assert card["done"] is False and card["pending"] is q
    # 사장님이 고른 쪽으로 고치고, 게이트가 닫힌다(검토는 다시 돌지 않는다)
    fake["review"] = {"missing": [], "conflicts": [{"slot": "business_type", "said": "엉뚱", "quote": "첼로 레슨 사이트요"}]}
    r = E.turn(card, "첼로 레슨")
    assert r["done"] and card["slots"]["business_type"]["value"] == "첼로 레슨"
    assert E.close_gate(card)["question"] is None


def test_gate_asks_feature_added_by_reviewer_before_approval(fake):
    """대표 지적(9/26): 승인 뒤에 '빠진 게 있다'가 나오던 문제. 검토가 넣은 기능의 확인 질문은 승인 전에 묻는다."""
    card = _card(fake)
    fake["review"] = {"missing": [{"slot": "features", "value": "카카오톡으로 문의 받기", "quote": "문의가 제 카카오톡으로 오게"}],
                      "conflicts": []}
    g = E.close_gate(card)
    assert g["review"]["added"] == ["features"]
    q = g["question"]
    assert q and q["kind"] == "feature" and q["gate"] and "승인 전에 확인할 게 남았어요" in E.format_question(card, q)
    E.turn(card, q["options"][0])
    assert E.close_gate(card)["question"] is None  # 모두 닫혀야 승인으로


def test_skip_closes_feature_and_conflict_checks(fake):
    card = _card(fake)
    fake["review"] = {"missing": [{"slot": "features", "value": "카카오톡으로 문의 받기", "quote": "문의가 제 카카오톡으로 오게"}],
                      "conflicts": []}
    assert E.close_gate(card)["question"]
    r = E.turn(card, "시안 먼저")  # "나머지는 알아서"
    assert r["done"] and E.close_gate(card)["question"] is None


def test_review_runs_once_per_card(fake, monkeypatch):
    card = _card(fake)
    calls = []
    real = E.review
    monkeypatch.setattr(E, "review", lambda c, **k: calls.append(1) or real(c, **k))
    E.close_gate(card)
    E.close_gate(card)
    assert calls == [1]


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
