"""저신뢰 재확인 (STT 뭉개짐 1회 확인) + normalize_words 테스트.

경계: 신규 LLM 에이전트 금지(D34). _confirm_question/close_gate 재사용만.
가짜 AI(llm.chat_json monkeypatch)만 쓴다.
"""
import json

import pytest

from app import llm
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services import stt


def fake_setup(monkeypatch, table):
    def fake(system, user, **kw):
        text = user.split("[사장님 메시지] ", 1)[-1]
        return json.dumps({"updates": table.get(text, [])}, ensure_ascii=False)

    monkeypatch.setattr(llm, "chat_json", fake)


def u(slot, value):
    return {"slot": slot, "value": value}


# ── stt.normalize_words ──────────────────────────────────────────

def test_word_fixes_within_limit():
    assert len(stt._WORD_FIXES) <= 20


def test_normalize_words_garbles():
    assert stt.normalize_words("객실세계 있어요") == "객실 세 개 있어요"
    assert stt.normalize_words("테이블세게 2층에") == "테이블 세 개 2층에"
    assert stt.normalize_words("바베큐장 있어요") == "바비큐장 있어요"
    assert stt.normalize_words("김치찌게 9천원") == "김치찌개 9천원"
    # 일반 발화는 그대로
    assert stt.normalize_words("이 사진 일단 올릴게요") == "이 사진 일단 올릴게요"
    assert stt.normalize_words("") == ""


def test_transcribe_applies_digits_then_words(monkeypatch):
    monkeypatch.setattr(stt, "to_wav16k", lambda data: b"wav")
    monkeypatch.setattr(
        stt, "_recognize",
        lambda wav: "객실세계 있고 번호는 공일공 공공공공 일이삼사입니다.")
    assert stt.transcribe(b"fake") == "객실 세 개 있고 번호는 010-0000-1234입니다."


# ── prd_engine 뭉개짐 1회 확인 ────────────────────────────────────

def _pension_base():
    card = E.new_card("pension")
    E._put(card, "business_type", "펜션", S.FILLED, 0)
    E._put(card, "shop_name", "바다정원", S.FILLED, 0)
    return card


def test_digit_count_does_not_confirm():
    card = _pension_base()
    E.apply_updates(card, [u("offerings", "객실 3개")], "객실 3개 있어요")
    assert card.get("word_confirm_queue") in (None, [])
    q = E._confirm_question(card)
    assert q is None or q.get("kind") != "word_confirm"


def test_korean_count_queues_one_confirm(monkeypatch):
    fake_setup(monkeypatch, {"객실 세 개 있어요": [u("offerings", "객실 세 개")]})
    card = _pension_base()
    r = E.turn(card, "객실 세 개 있어요")
    q = r["question"]
    assert q["kind"] == "word_confirm"
    assert q["slot"] == "offerings"
    assert "객실 3개 맞나요?" in q["text"]
    assert q["options"] == ["네", "아니요"]
    # 확인 질문은 예산을 쓰지 않는다
    assert card["asked"] == 0


def test_yes_keeps_and_asks_once(monkeypatch):
    fake_setup(monkeypatch, {"객실 세 개 있어요": [u("offerings", "객실 세 개")]})
    card = _pension_base()
    E.turn(card, "객실 세 개 있어요")
    r2 = E.turn(card, "네")
    assert "객실 세 개" in card["slots"]["offerings"]["value"]
    assert (r2["question"] or {}).get("kind") != "word_confirm"
    # 다시 같은 값이 들어와도 1회 원칙으로 묻지 않는다
    E.apply_updates(card, [u("offerings", "객실 세 개")], "객실 세 개 있어요")
    assert E._confirm_question(card) is None or \
        E._confirm_question(card).get("kind") != "word_confirm"


def test_no_removes_value(monkeypatch):
    fake_setup(monkeypatch, {"객실 세 개 있어요": [u("offerings", "객실 세 개")]})
    card = _pension_base()
    E.turn(card, "객실 세 개 있어요")
    E.turn(card, "아니요")
    assert "offerings" not in card["slots"] or \
        "객실 세 개" not in str(card["slots"].get("offerings", {}).get("value"))


def test_confirm_needs_no_llm(monkeypatch):
    # D34: 확인 응답 턴에 LLM을 부르면 실패
    def boom(*a, **k):
        raise AssertionError("턴마다 에이전트 금지(D34)")

    monkeypatch.setattr(llm, "chat_json", boom)
    card = _pension_base()
    E.apply_updates(card, [u("offerings", "객실 세 개")], "객실 세 개 있어요")
    card["pending"] = E._confirm_question(card)
    assert card["pending"]["kind"] == "word_confirm"
    r = E.turn(card, "네")
    assert "객실 세 개" in card["slots"]["offerings"]["value"]
    assert (r["question"] or {}).get("kind") != "word_confirm"


def test_close_gate_reuses_confirm(monkeypatch):
    fake_setup(monkeypatch, {})
    card = _pension_base()
    E.apply_updates(card, [u("offerings", "테이블 두 개")], "테이블 두 개 있어요")
    out = E.close_gate(card)
    assert out["question"] is not None
    assert out["question"]["kind"] == "word_confirm"
    assert "테이블 2개 맞나요?" in out["question"]["text"]
