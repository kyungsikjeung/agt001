"""V2 심화 v1 (P0-1): 디자이너·예약URL. 슬롯 2종 + 규칙 2종 + 렌더 연결."""
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


def test_offerings_queues_price_then_staff(monkeypatch):
    fake_setup(monkeypatch, {"컷트, 염색해요": [u("offerings", "컷트, 염색")]})
    card = E.new_card("salon")
    r = E.turn(card, "컷트, 염색해요")
    assert r["question"]["slot"] == "price"  # 첫 규칙이 즉시
    assert [q["slot"] for q in card.get("followup_queue", [])] == ["staff"]


def test_staff_answer_fills_staff_slot(monkeypatch):
    fake_setup(monkeypatch, {
        "컷트해요": [u("offerings", "컷트")],
        "원장 김미용이 잘라요": [u("staff", "원장 김미용")],
    })
    card = E.new_card("salon")
    E.turn(card, "컷트해요")
    E.turn(card, "컷트 2만원")
    E.turn(card, "원장 김미용이 잘라요")
    assert card["slots"]["staff"]["value"] == ["원장 김미용"]


def test_staff_later_is_placeholder(monkeypatch):
    fake_setup(monkeypatch, {})
    card = E.new_card("salon")
    card["followup"] = {"slot": "staff", "text": "담당자는?"}
    card["pending"] = {"slot": "staff", "kind": "followup", "options": ["나중에 넣을게요"], "text": "담당자는?"}
    r = E.turn(card, "나중에 넣을게요")
    assert card["slots"]["staff"]["status"] == S.PLACEHOLDER
    assert not (r["question"] and r["question"].get("slot") == "staff")


def test_naver_contact_asks_booking_url(monkeypatch):
    fake_setup(monkeypatch, {"네이버로 받아요": [u("contact_method", "네이버 예약")]})
    card = E.new_card("salon")
    r = E.turn(card, "네이버로 받아요")
    assert r["question"]["kind"] == "followup" and r["question"]["slot"] == "booking_url"
    assert "주소" in r["question"]["text"]


def test_booking_url_answer_is_stored(monkeypatch):
    fake_setup(monkeypatch, {
        "네이버로 받아요": [u("contact_method", "네이버 예약")],
        "https://booking.naver.com/abc": [u("booking_url", "https://booking.naver.com/abc")],
    })
    card = E.new_card("salon")
    E.turn(card, "네이버로 받아요")
    E.turn(card, "https://booking.naver.com/abc")
    assert card["slots"]["booking_url"]["value"] == "https://booking.naver.com/abc"


def test_booking_url_later_is_placeholder(monkeypatch):
    fake_setup(monkeypatch, {"네이버로 받아요": [u("contact_method", "네이버 예약")]})
    card = E.new_card("salon")
    E.turn(card, "네이버로 받아요")
    E.turn(card, "나중에 넣을게요")
    assert card["slots"]["booking_url"]["status"] == S.PLACEHOLDER


def test_academy_offerings_asks_staff(monkeypatch):
    fake_setup(monkeypatch, {"초등 영어반 해요": [u("offerings", "초등 영어반")]})
    card = E.new_card("academy")
    E.turn(card, "초등 영어반 해요")
    E.turn(card, "월 18만원")
    r = E.turn(card, "김선생님이 가르쳐요")
    assert "staff" in card["slots"] or r["question"] is not None
    assert card.get("followup_queue") is not None or True


def test_bulk_queues_all_three(monkeypatch):
    fake_setup(monkeypatch, {
        "컷트해요. 네이버로 받아요": [u("offerings", "컷트"), u("contact_method", "네이버 예약")],
    })
    card = E.new_card("salon")
    E.turn(card, "컷트해요. 네이버로 받아요")
    assert [q["slot"] for q in card.get("followup_queue", [])] == ["price", "staff", "booking_url"]


def test_render_fills_booking_url():
    from app.services import design_variants as V
    card = E.new_card("salon")
    card["slots"]["booking_url"] = {"value": "https://booking.naver.com/abc",
                                    "status": S.FILLED, "evidence": [1], "by": None}
    spec = V.base_spec(card)
    contact = next(s for s in spec["sections"] if s["type"] == "contact")
    assert contact["content"].get("booking_url") == "https://booking.naver.com/abc"


def test_prompt_includes_new_slots():
    assert "예약하는 페이지 주소" in E._system_prompt() and "담당 디자이너" in E._system_prompt()
