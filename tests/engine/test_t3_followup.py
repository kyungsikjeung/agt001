"""T3 후속 수정 (N-2 메뉴·가격 분리, N-3 근거 없는 target·features 방지, N-4 첫 메시지 흡수) 회귀 테스트.

가짜 AI(llm.chat_json monkeypatch)만 사용, DB·실제 NIM 호출 없음.
T3_FAILURE_ANALYSIS.md §3 엔진 2·3·5순위.
"""
import json

import pytest

from app import llm
from app.services import prd_engine as E
from app.services import prd_schema as S


@pytest.fixture
def fake_extract(monkeypatch):
    table: dict[str, list] = {}

    def fake(system, user, **kw):
        text = user.split("[사장님 메시지] ", 1)[-1]
        return json.dumps({"updates": table.get(text, [])}, ensure_ascii=False)

    monkeypatch.setattr(llm, "chat_json", fake)
    return table


def u(slot, value):
    return {"slot": slot, "value": value}


def status(card, key):
    return card["slots"].get(key, {}).get("status", S.EMPTY)


def value(card, key):
    return card["slots"].get(key, {}).get("value")


# ── N-2: 메뉴·가격 분리 ──────────────────────────────────────────────

def test_price_split_from_offerings(fake_extract):
    """'아메리카노 5천원, 라떼 6천원'은 메뉴와 가격으로 나뉘어야 한다 (T2 e013)."""
    msg = "아메리카노 5천원, 라떼 6천원이에요"
    fake_extract[msg] = [u("offerings", "아메리카노 5천원"), u("offerings", "라떼 6천원")]
    card = E.new_card()
    E.turn(card, msg)
    assert value(card, "offerings") == ["아메리카노", "라떼"]
    assert value(card, "price") == "5천원, 6천원"
    assert status(card, "price") == S.FILLED


def test_menu_split_from_price(fake_extract):
    """price에 메뉴가 붙어 있으면('젤네일 5만원부터') 메뉴는 offerings로 가야 한다 (T2 e033)."""
    msg = "젤네일 5만원부터예요"
    fake_extract[msg] = [u("price", "젤네일 5만원부터")]
    card = E.new_card()
    E.turn(card, msg)
    assert "젤네일" in (value(card, "offerings") or [])
    assert "5만원" in (value(card, "price") or "")


def test_pure_values_untouched(fake_extract):
    """가격이 없는 값은 그대로 둔다."""
    msg = "라떼 팔아요"
    fake_extract[msg] = [u("offerings", "라떼")]
    card = E.new_card()
    E.turn(card, msg)
    assert value(card, "offerings") == ["라떼"]
    assert "price" not in card["slots"]


def test_no_split_without_text_evidence(fake_extract):
    """말에도 없는 가격·메뉴로 나누지 않는다 (지어내기 방지)."""
    msg = "라떼 팔아요"
    fake_extract[msg] = [u("offerings", "라떼 5천원")]
    card = E.new_card()
    E.turn(card, msg)
    assert value(card, "offerings") == ["라떼 5천원"]
    assert "price" not in card["slots"]


# ── N-3: 근거 없는 target·features 방지 ──────────────────────────────

def test_ungrounded_features_dropped(fake_extract):
    """말하지 않은 기능은 채우지 않는다 (pension-talkative features 지어냄)."""
    msg = "펜션이에요"
    fake_extract[msg] = [u("business_type", "펜션"), u("features", "온라인 예약")]
    card = E.new_card()
    E.turn(card, msg)
    assert "features" not in card["slots"]


def test_grounded_features_kept(fake_extract):
    """말한 기능은 그대로 채운다."""
    msg = "펜션이고 온라인 예약을 받고 싶어요"
    fake_extract[msg] = [u("business_type", "펜션"), u("features", "온라인 예약")]
    card = E.new_card()
    E.turn(card, msg)
    assert status(card, "features") == S.FILLED


def test_ungrounded_target_dropped_when_not_required(fake_extract):
    """펜션(required 아님)의 근거 없는 target은 채우지 않는다."""
    msg = "펜션이에요"
    fake_extract[msg] = [u("business_type", "펜션"), u("target", "가족 여행객")]
    card = E.new_card()
    E.turn(card, msg)
    assert "target" not in card["slots"]


def test_target_kept_when_required(fake_extract):
    """학원(required)의 target은 기존대로 둔다."""
    msg = "학원이에요"
    fake_extract[msg] = [u("business_type", "학원"), u("target", "초등학생")]
    card = E.new_card()
    E.turn(card, msg)
    assert status(card, "target") == S.FILLED


def test_target_kept_when_answering_its_question(fake_extract):
    """물어보고 답한 칸은 그대로 둔다."""
    card = E.new_card()
    fake_extract["펜션이에요"] = [u("business_type", "펜션")]
    r = E.turn(card, "펜션이에요")
    while not r["done"] and r["question"] and r["question"]["slot"] != "goal":
        r = E.turn(card, "잘 모르겠어요")  # 한 칸만 닫기("알아서 해주세요"는 바로 시안)
    assert r["question"]["slot"] == "goal"
    msg = "예약 문의를 늘리고 싶어요"
    fake_extract[msg] = [u("goal", "예약 문의 늘리기")]
    E.turn(card, msg)
    assert status(card, "goal") == S.FILLED


# ── N-4: 첫 메시지 흡수 ──────────────────────────────────────────────

def test_first_message_slots_not_reasked(fake_extract):
    """첫 턴에 채운 칸은 다시 묻지 않는다."""
    msg = "카페 모퉁이커피예요. 라떼 팔고 전화로 받아요"
    fake_extract[msg] = [u("business_type", "카페"), u("shop_name", "모퉁이커피"),
                         u("offerings", "라떼"), u("contact_method", "전화")]
    card = E.new_card()
    asked_slots = []
    r = E.turn(card, msg)
    while not r["done"]:
        q = r["question"]
        asked_slots.append(q["slot"])
        # 숨은 항목은 '없음'으로, 나머지는 가짜 AI가 아는 범위에서 답한다
        nxt = "없음" if q["kind"] == "multi" else "알아서 해주세요"
        r = E.turn(card, nxt)
    for s in ("business_type", "shop_name", "offerings", "contact_method"):
        assert s not in asked_slots


# ── N-2 프롬프트 문구 ────────────────────────────────────────────────

def test_prompt_has_price_split_rule():
    """추출 프롬프트에 메뉴·가격 분리 규칙이 있어야 한다."""
    prompt = E._system_prompt()
    assert "나눠서" in prompt
    assert "초등 영어" in prompt  # 대상·품목 반례
