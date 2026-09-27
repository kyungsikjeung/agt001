"""여러 개 고르기(숨은 항목)에 목록 밖 항목 추가 (사장님 요청 9/27: "바비큐 넣고 싶은데 고를 게 없다")."""
import json

import pytest

from app import llm
from app.services import prd_engine as E


@pytest.fixture(autouse=True)
def no_extract(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda system, user, **kw: json.dumps({"updates": []}))


def ask_multi(industry):
    card = E.new_card(industry)
    ind = E.industry_of(card)
    card["pending"] = {"slot": None, "kind": "multi", "options": [l for _, l in ind.hidden[:3]] + ["없음"], "text": "?"}
    card["asked"] = 1
    return card


def test_unlisted_only_is_kept_and_not_reasked():
    card = ask_multi("cafe")
    r = E.turn(card, "바비큐 가능해요")
    assert card["hidden"] == {"asked": True, "selected": [], "extra": ["바비큐"]}
    assert not (r["question"] and r["question"]["kind"] == "multi")


def test_ui_format_picks_note_and_extra():
    card = ask_multi("pension")
    E.turn(card, "주차, 반려동물 동반 — 소형견만 가능 / 추가: 바비큐장, 테라스석")
    h = card["hidden"]
    assert h["selected"] == ["parking", "pet"]
    assert h["extra"] == ["바비큐장", "테라스석"]
    assert h["note"].startswith("소형견만")


def test_extra_only_ui_format():
    card = ask_multi("cafe")
    E.turn(card, "추가: 테라스석")
    assert card["hidden"]["extra"] == ["테라스석"] and card["hidden"]["selected"] == []


def test_leftover_particles_are_not_note():
    card = ask_multi("pension")
    E.turn(card, "주차 — 바비큐도 돼요")
    assert set(card["hidden"]["selected"]) == {"parking", "bbq"}
    assert "note" not in card["hidden"]


def test_other_slot_talk_goes_to_extraction_not_extra():
    card = ask_multi("cafe")
    E.turn(card, "가게 이름은 달빛카페예요")
    assert not card["hidden"].get("extra")


def test_more_options_carry_rest_of_list():
    card = E.new_card("pension")
    for k, v in (("business_type", "펜션"), ("shop_name", "바다정원"), ("offerings", ["객실 3개"])):
        E._put(card, k, v, E.S.FILLED)
    q = E.next_question(card)
    assert q["kind"] == "multi" and len(q["options"]) == 4
    assert q["more_options"] == ["픽업", "장기 숙박 할인"]


def test_summary_lists_extra():
    card = ask_multi("cafe")
    E.turn(card, "주차 / 추가: 테라스석")
    assert "테라스석" in E.summary_text(card)


def test_note_only_ui_format_is_note_not_extra():
    card = ask_multi("pension")
    E.turn(card, "— 소형견만 가능해요")
    assert card["hidden"] == {"asked": True, "selected": [], "note": "소형견만 가능해요"}


def test_note_and_extra_without_picks():
    card = ask_multi("pension")
    E.turn(card, "— 소형견만 가능해요 / 추가: 바비큐장")
    assert card["hidden"]["extra"] == ["바비큐장"]
    assert card["hidden"]["note"] == "소형견만 가능해요"
