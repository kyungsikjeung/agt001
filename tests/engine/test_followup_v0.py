"""V2 심화 질문 v0 (REQUIREMENTS_PIPELINE_V2 V2-1): 분기 1개 = 테스트 1개."""
import json

from app import llm
from app.services import prd_engine as E
from app.services import prd_schema as S


def fake_setup(monkeypatch, table):
    def fake(system, user, **kw):
        text = user.split("[사장님 메시지] ", 1)[-1]
        return json.dumps({"updates": table.get(text, [])}, ensure_ascii=False)

    monkeypatch.setattr(llm, "chat_json", fake)


def u(slot, value):
    return {"slot": slot, "value": value}


def test_salon_offerings_asks_price(monkeypatch):
    fake_setup(monkeypatch, {"컷트, 염색해요": [u("offerings", "컷트, 염색")]})
    card = E.new_card("salon")
    r = E.turn(card, "컷트, 염색해요")
    assert r["question"]["kind"] == "followup" and r["question"]["slot"] == "price"
    assert "가격" in r["question"]["text"]


def test_price_answer_fills_price_slot(monkeypatch):
    fake_setup(monkeypatch, {
        "컷트, 염색해요": [u("offerings", "컷트, 염색")],
        "컷트 2만원, 염색 8만원": [u("price", "컷트 2만원, 염색 8만원")],
    })
    card = E.new_card("salon")
    E.turn(card, "컷트, 염색해요")
    E.turn(card, "컷트 2만원, 염색 8만원")
    assert card["slots"]["price"]["status"] == S.FILLED


def test_price_later_is_placeholder(monkeypatch):
    fake_setup(monkeypatch, {"컷트, 염색해요": [u("offerings", "컷트, 염색")]})
    card = E.new_card("salon")
    E.turn(card, "컷트, 염색해요")
    r = E.turn(card, "나중에 넣을게요")
    assert card["slots"]["price"]["status"] == S.PLACEHOLDER
    assert not (r["question"] and r["question"].get("slot") == "price")


def test_no_price_followup_when_price_given(monkeypatch):
    fake_setup(monkeypatch, {"컷트 2만원이에요": [u("offerings", "컷트"), u("price", "2만원")]})
    card = E.new_card("salon")
    r = E.turn(card, "컷트 2만원이에요")
    assert not (r["question"] and r["question"].get("kind") == "followup"
                and r["question"].get("slot") == "price")


def test_phone_followup_when_contact_is_phone(monkeypatch):
    fake_setup(monkeypatch, {"전화로 받아요": [u("contact_method", "전화")]})
    card = E.new_card("salon")
    r = E.turn(card, "전화로 받아요")
    assert r["question"]["kind"] == "followup" and r["question"]["slot"] == "phone"


def test_phone_answer_fills_phone_slot(monkeypatch):
    fake_setup(monkeypatch, {
        "전화로 받아요": [u("contact_method", "전화")],
        "010-0000-1234예요": [u("phone", "010-0000-1234")],
    })
    card = E.new_card("salon")
    E.turn(card, "전화로 받아요")
    E.turn(card, "010-0000-1234예요")
    assert card["slots"]["phone"]["value"] == "010-0000-1234"


def test_no_phone_followup_for_kakao_only(monkeypatch):
    fake_setup(monkeypatch, {"카톡으로 받아요": [u("contact_method", "카카오톡 채널")]})
    card = E.new_card("salon")
    r = E.turn(card, "카톡으로 받아요")
    assert not (r["question"] and r["question"].get("kind") == "followup"
                and r["question"].get("slot") == "phone")


def test_followup_asked_only_once(monkeypatch):
    fake_setup(monkeypatch, {
        "컷트, 염색해요": [u("offerings", "컷트, 염색")],
        "컷트 2만원": [u("price", "컷트 2만원")],
    })
    card = E.new_card("salon")
    E.turn(card, "컷트, 염색해요")
    r = E.turn(card, "컷트 2만원")
    assert card["slots"]["price"]["status"] == S.FILLED
    assert card["followup_asked"].count("price") == 1
    assert not (r["question"] and r["question"].get("kind") == "followup")


def test_academy_offerings_asks_price(monkeypatch):
    fake_setup(monkeypatch, {"초등 영어반 해요": [u("offerings", "초등 영어반")]})
    card = E.new_card("academy")
    r = E.turn(card, "초등 영어반 해요")
    assert r["question"]["kind"] == "followup" and r["question"]["slot"] == "price"


def test_pension_offerings_asks_price(monkeypatch):
    fake_setup(monkeypatch, {"객실 3개예요": [u("offerings", "객실 3개")]})
    card = E.new_card("pension")
    r = E.turn(card, "객실 3개예요")
    assert r["question"]["kind"] == "followup" and r["question"]["slot"] == "price"


def test_bulk_turn_queues_both_followups(monkeypatch):
    """복합 답변도 규칙을 하나도 유실하지 않고 큐에 쌓는다."""
    fake_setup(monkeypatch, {
        "컷트, 염색해요. 전화로 받아요": [u("offerings", "컷트, 염색"), u("contact_method", "전화")],
    })
    card = E.new_card("salon")
    r = E.turn(card, "컷트, 염색해요. 전화로 받아요")
    assert r["question"]["kind"] != "followup"  # 필수·숨은 질문이 먼저
    assert [q["slot"] for q in card.get("followup_queue", [])] == ["price", "phone"]
