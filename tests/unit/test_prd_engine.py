"""요구사항 엔진 규칙 테스트 (REQUIREMENTS_ENGINE_PLAN.md §4 T1). 가짜 추출기로 결정적으로 검사한다."""
import json

import pytest

from app import llm
from app.services import prd_engine as E
from app.services import prd_schema as S


@pytest.fixture
def fake_extract(monkeypatch):
    """메시지 → 추출 결과를 표로 정하는 가짜 AI. 표에 없으면 빈 결과."""
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


def test_invented_facts_are_dropped(fake_extract):
    msg = "카페 모퉁이커피예요"
    fake_extract[msg] = [u("business_type", "카페"), u("shop_name", "모퉁이커피"),
                         u("phone", "010-0000-1111"), u("hours", "10시~22시"), u("location", "부산 해운대")]
    card = E.new_card()
    E.turn(card, msg)
    assert status(card, "shop_name") == S.FILLED
    for fact in ("phone", "hours", "location"):
        assert status(card, fact) == S.EMPTY, fact


def test_grounded_facts_are_kept(fake_extract):
    msg = "전화는 010-0000-2222, 영업은 11시부터 21시, 해운대에 있어요"
    fake_extract[msg] = [u("phone", "010-0000-2222"), u("hours", "11시~21시"), u("location", "해운대")]
    card = E.new_card()
    E.turn(card, msg)
    assert [status(card, k) for k in ("phone", "hours", "location")] == [S.FILLED] * 3


def test_one_question_with_at_most_four_choices(fake_extract):
    card = E.new_card()
    r = E.turn(card, "안녕하세요")
    q = r["question"]
    assert q["kind"] == "single" and q["slot"] == "business_type"
    assert len(q["options"]) <= S.MAX_OPTIONS + 1 and q["options"][-1] == S.LET_AI
    text = E.format_question(card, q)
    assert text.count("?") == 1 and "질문 1/8" in text


def test_question_order_follows_industry(fake_extract):
    fake_extract["도자기 공방이에요"] = [u("business_type", "도자기 공방")]
    card = E.new_card()
    r = E.turn(card, "도자기 공방이에요")
    assert card["industry"] == "workshop"
    assert r["question"]["slot"] == "shop_name"
    assert "applied" in r and r["applied"] == ["business_type"]


def test_let_ai_assumes_non_fact_and_placeholders_fact(fake_extract):
    fake_extract["카페예요"] = [u("business_type", "카페")]
    card = E.new_card()
    E.turn(card, "카페예요")                     # → 가게 이름 질문
    E.turn(card, S.LET_AI)                      # 가게 이름은 지어내지 않고 자리 표시
    assert status(card, "shop_name") == S.PLACEHOLDER
    r = E.turn(card, "모르겠어요")               # 모름은 "알아서"처럼 닫는다 (T3 r5: 되풀이하면 중복·질문 수 초과)
    assert status(card, "offerings") == S.ASSUMED
    assert r["question"] is None or r["question"]["slot"] != "offerings"


def test_hidden_items_asked_once_as_multi_select(fake_extract):
    msg = "강릉 바다정원 펜션이고 객실 3개예요"
    fake_extract[msg] = [u("business_type", "펜션"), u("shop_name", "바다정원 펜션"), u("offerings", "객실 3개")]
    card = E.new_card()
    r = E.turn(card, msg)
    assert r["question"]["kind"] == "multi"
    assert "주차" in r["question"]["options"] and r["question"]["options"][-1] == "없음"
    E.turn(card, "주차, 반려동물 동반")
    assert card["hidden"] == {"asked": True, "selected": ["parking", "pet"]}
    r2 = E.turn(card, "전화요")
    assert r2["question"] is None or r2["question"]["kind"] != "multi"


def test_skip_phrase_finalizes_with_placeholders(fake_extract):
    card = E.new_card()
    E.turn(card, "안녕하세요")
    r = E.turn(card, "나머지는 알아서, 시안 먼저 볼게요")
    assert r["done"] and card["done"]
    assert status(card, "phone") == S.PLACEHOLDER and status(card, "location") == S.PLACEHOLDER
    assert status(card, "shop_name") == S.PLACEHOLDER
    assert "[가게 이름 입력 필요]" in E.summary_text(card)


def test_question_cap_is_eight(fake_extract):
    card = E.new_card()
    for _ in range(12):
        r = E.turn(card, "음")
        if r["done"]:
            break
    assert card["done"] and card["asked"] == S.MAX_QUESTIONS


def test_exclude_removes_items(fake_extract):
    fake_extract["펜션이고 바비큐장, 객실 소개할래요"] = [u("business_type", "펜션"), u("sections", "바비큐장"), u("sections", "객실 소개")]
    fake_extract["아 바비큐는 빼주세요"] = [u("exclude", "바비큐")]
    card = E.new_card()
    E.turn(card, "펜션이고 바비큐장, 객실 소개할래요")
    E.turn(card, "아 바비큐는 빼주세요")
    assert card["slots"]["sections"]["value"] == ["객실 소개"]
    assert "바비큐" in card["slots"]["exclude"]["value"]


def test_group_facts_need_owner_confirmation(fake_extract):
    fake_extract["번호는 010-0000-3333이에요"] = [u("phone", "010-0000-3333")]
    card = E.new_card()
    r = E.turn(card, "번호는 010-0000-3333이에요", by="h-daughter", is_owner=False)
    assert status(card, "phone") == S.PENDING_OWNER
    assert r["question"]["kind"] == "owner_confirm"
    E.turn(card, "네", by="h-daughter", is_owner=False)      # 방장이 아니면 확정되지 않는다
    assert status(card, "phone") == S.PENDING_OWNER
    E.turn(card, "네", by="h-owner", is_owner=True)
    assert status(card, "phone") == S.FILLED


def test_template_prefills_structure_not_facts():
    card = E.new_card("pension")
    assert status(card, "business_type") == S.ASSUMED and status(card, "sections") == S.ASSUMED
    assert "shop_name" not in card["slots"] and "phone" not in card["slots"]


def test_does_not_reask_filled_slot(fake_extract):
    msg = "카페 모퉁이커피, 대표 메뉴는 라떼, 전화로 받아요, 가게 알리려고요"
    fake_extract[msg] = [u("business_type", "카페"), u("shop_name", "모퉁이커피"), u("offerings", "라떼"),
                         u("contact_method", "전화"), u("goal", "가게 알리기")]
    card = E.new_card()
    asked = []
    r = E.turn(card, msg)
    while not r["done"]:
        asked.append(r["question"]["slot"])
        r = E.turn(card, "없음" if r["question"]["kind"] == "multi" else S.LET_AI)
    assert not {"business_type", "shop_name", "offerings", "contact_method", "goal"} & set(asked)


def test_malformed_ai_output_retries_then_continues(monkeypatch):
    calls = []

    def broken(system, user, **kw):
        calls.append(1)
        return "We need to extract the slots..."

    monkeypatch.setattr(llm, "chat_json", broken)
    card = E.new_card()
    r = E.turn(card, "카페예요")
    assert len(calls) == 2           # 한 번 재시도
    assert r["question"]["slot"] == "business_type"  # 대화는 멈추지 않는다


def test_unknown_industry_skips_generic_hidden_items_and_keeps_features(fake_extract):
    """실제 사례: '첼로 사이트, 문의가 제 카카오톡으로' → 엉뚱한 '주차·배송' 질문 대신 기능을 붙잡는다."""
    msg = "첼로사이트를 만들고 싶어요. 사용자가 입력한 문의 내용이 저의 카카오톡 채팅방으로 전송되었으면 좋겠어요"
    fake_extract[msg] = [u("business_type", "첼로"), u("features", "카카오톡으로 문의 받기")]
    card = E.new_card()
    r = E.turn(card, msg)
    assert card["industry"] == "other"
    assert r["question"]["kind"] != "multi"
    assert card["slots"]["features"]["value"] == ["카카오톡으로 문의 받기"]
    ack = E.ack_text(card, r["applied"])
    assert "카카오톡으로 문의 받기" in ack and ack.startswith("이렇게 이해했어요")
