"""베타 F7 글·라벨 고치기. DB 없이 돌아간다."""
from app.services import archetype
from app.services import chat_flow
from app.services import design_concept
from app.services import design_variants as DV
from app.services import palette as PAL
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services import rooms
from app.services import site_data
from app.services import site_render as SR


def test_joined_text_nim_ending():
    assert rooms.joined_text("사장님") == "사장님이 입장했습니다."
    assert rooms.joined_text("민수") == "민수님이 입장했습니다."


def test_honor_keeps_nim_ending():
    assert rooms.honor("사장님") == "사장님"
    assert rooms.honor("민수") == "민수님"


def test_lead_text_pension_offerings():
    assert design_concept.lead_text({"lead": "offerings", "industry": "pension"}) == "객실 먼저"
    assert design_concept.lead_text({"lead": "offerings"}) == "메뉴·상품 먼저"
    assert design_concept.lead_text({"lead": "gallery", "industry": "pension"}) == "사진 먼저"


def test_rule_concept_pension_has_industry():
    card = E.new_card("pension")
    concept = design_concept.rule_concept(card)
    assert concept["industry"] == "pension"


def test_rag_note_drops_unbuilt_item(monkeypatch):
    monkeypatch.setattr(chat_flow.rag, "similar", lambda spec: ["예약 캘린더 자체 구현"])
    result = chat_flow._rag_note("펜션 예약 사이트")
    assert "만들지 않는다" not in result
    assert result == "말씀하신 내용과 업종 기본 구성에 맞춰 설계할게요."


def test_pension_render_uses_checkin_label():
    card = E.new_card("pension")
    E._put(card, "shop_name", "숲속의 쉼", S.FILLED, 1)
    E._put(card, "hours", "15시 / 11시", S.FILLED, 1)
    E._put(card, "location", "강원도 평창군 대관령면 올림픽로 12", S.FILLED, 1)
    card["turn"] = 1
    bp = archetype.load("C")
    spec = site_data.resolve(site_data.skeleton(bp, 0), card, archetype="C")
    spec["tokens"]["palette"] = PAL.pick("C", 1)
    html = SR.render_site(spec, site_key="test-beta-f7", title=DV.title_for(card),
                          kind=DV.kind_for(card))
    assert "입실·퇴실" in html
    assert ">영업<" not in html


def _gate(monkeypatch, skip):
    monkeypatch.setattr(E, "close_gate", lambda card: {"question": None, "review": None})
    monkeypatch.setattr(chat_flow, "_rag_note", lambda spec: "")
    card = E.new_card("restaurant")
    E._put(card, "shop_name", "내맘", S.FILLED, 1)
    E._put(card, "phone", None, S.PLACEHOLDER, 1)
    E._put(card, "location", None, S.PLACEHOLDER, 1)
    session = {"state": "GATHERING", "prd": card}
    reply = chat_flow._gate_or_summary(session, card, None, {"skip": skip})
    return session, card, reply


def test_gate_asks_missing_before_approval(monkeypatch):
    session, card, reply = _gate(monkeypatch, skip=False)
    assert session["state"] == "AWAIT_APPROVAL" and chat_flow.fill_first(session)
    assert "시안 전에 비어 있는 곳을 알려 주세요: 전화번호, 위치" in reply
    assert "시안을 만들어 볼까요" not in reply


def test_gate_skip_goes_straight_to_approval(monkeypatch):
    session, card, reply = _gate(monkeypatch, skip=True)
    assert not chat_flow.fill_first(session) and card["fill_later"] is True
    assert "시안을 만들어 볼까요" in reply
