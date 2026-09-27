"""요구사항 엔진 독립 검증 테스트 (소유: 검증자 V).

기준은 실제 코드(app/services/prd_engine.py, prd_schema.py)이며, 가짜 AI
(llm.chat_json을 monkeypatch)로 경계 조건을 확인한다. DB 불필요.

규칙: 기대와 다르게 동작하는 것은 실패하는 테스트로 남긴다 (수정 금지).
실패 테스트의 결함 내용은 docs/product/reviews/REQUIREMENTS_ENGINE_VERIFICATION.md에 기록.
"""
import json
import re

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


def digits(s):
    return re.sub(r"\D", "", s or "")


# 기준 발화: 카페 필수 5칸(business_type·shop_name·offerings·hours·contact_method)을
# 한 번에 채운다. hours는 근거 검사(숫자 일치)를 통과하는 값으로 둔다.
FULL_CAFE_MSG = "카페 모퉁이커피예요. 라떼 팔고 10시부터 22시까지 해요"
FULL_CAFE_UPS = [
    u("business_type", "카페"),
    u("shop_name", "모퉁이커피"),
    u("offerings", "라떼"),
    u("hours", "10시~22시"),
]


def fill_cafe_minus_goal(fake_extract, card):
    """카페 필수 5칸을 채우고 숨은 항목('없음')까지 넘겨 goal 질문에서 멈춘다."""
    msg = FULL_CAFE_MSG + ". 전화로 받아요"
    fake_extract[msg] = list(FULL_CAFE_UPS) + [u("contact_method", "전화")]
    r = E.turn(card, msg)
    assert r["question"]["kind"] == "multi"
    r2 = E.turn(card, "없음")
    assert r2["question"]["slot"] == "goal"
    return r2


def pending_owner_card(fake_extract):
    """방장 확인 대기 상태(D52 전에 저장된 세션)를 직접 만든다. 새 대화에서는 더 생기지 않는다."""
    card = E.new_card()
    E._put(card, "phone", "010-0000-3333", S.PENDING_OWNER, 1, "h-daughter")
    card["pending"] = E._confirm_question(card)
    assert card["pending"]["kind"] == "owner_confirm"
    return card


# ── A. 선택지 답의 변형 ──────────────────────────────────────────────

def test_single_choice_fuzzy_answer_with_particle(fake_extract):
    """연락 방법 질문에 '전화요'라고 답하면 '전화'로 받아들여야 한다."""
    card = E.new_card()
    fake_extract[FULL_CAFE_MSG] = list(FULL_CAFE_UPS)
    r = E.turn(card, FULL_CAFE_MSG)
    assert r["question"]["kind"] == "multi"
    r2 = E.turn(card, "없음")
    assert r2["question"]["slot"] == "contact_method"
    E.turn(card, "전화요")
    assert status(card, "contact_method") == S.FILLED


def test_owner_confirm_uppercase_yes(fake_extract):
    """방장 확인에 'YES'라고 답해도 승인으로 받아들여야 한다."""
    card = pending_owner_card(fake_extract)
    E.turn(card, "YES", by="h-owner", is_owner=True)
    assert status(card, "phone") == S.FILLED


def test_owner_confirm_polite_yes(fake_extract):
    """방장 확인에 '네, 맞아요'라고 답해도 승인으로 받아들여야 한다."""
    card = pending_owner_card(fake_extract)
    E.turn(card, "네, 맞아요", by="h-owner", is_owner=True)
    assert status(card, "phone") == S.FILLED


def test_let_ai_paraphrase_not_recognized(fake_extract):
    """'알아서 해줘'(요 없음)도 '알아서 해주세요'와 같아야 한다."""
    card = E.new_card()
    fake_extract["카페예요"] = [u("business_type", "카페")]
    E.turn(card, "카페예요")  # → 가게 이름 질문
    E.turn(card, "알아서 해줘")
    assert status(card, "shop_name") == S.PLACEHOLDER


# ── B. 숨은 항목 여러 개 고르기 ──────────────────────────────────────

def pension_multi_card(fake_extract):
    msg = "강릉 바다정원 펜션이고 객실 3개예요"
    fake_extract[msg] = [u("business_type", "펜션"), u("shop_name", "바다정원 펜션"),
                         u("offerings", "객실 3개")]
    card = E.new_card()
    r = E.turn(card, msg)
    assert r["question"]["kind"] == "multi"
    return card


def test_hidden_partial_display_name(fake_extract):
    """표시 이름 일부만 말해도 골라져야 한다 ('주차 돼요' → 주차)."""
    card = pension_multi_card(fake_extract)
    E.turn(card, "주차 돼요")
    assert card["hidden"]["selected"] == ["parking"]


def test_hidden_none_mixed_with_selection(fake_extract):
    """'없음'과 다른 말이 섞이면 고른 항목은 살아야 한다."""
    card = pension_multi_card(fake_extract)
    E.turn(card, "주차는 되는데 나머지는 없음")
    assert "parking" in card["hidden"]["selected"]


def test_hidden_negation_ignored(fake_extract):
    """부정은 선택이 되면 안 된다 ('주차는 안 돼요' → 미선택)."""
    card = pension_multi_card(fake_extract)
    E.turn(card, "주차는 안 돼요")
    assert "parking" not in card["hidden"]["selected"]


def test_hidden_none_exact(fake_extract):
    """버튼 그대로 '없음'이면 빈 선택으로 끝난다."""
    card = pension_multi_card(fake_extract)
    E.turn(card, "없음")
    assert card["hidden"] == {"asked": True, "selected": []}


def test_hidden_multi_option_count_within_four(fake_extract):
    """숨은 항목 질문의 선택지 합계는 4개 이하여야 한다."""
    card = pension_multi_card(fake_extract)
    # NOTE: 업종별 숨은 항목 5개 + '없음' 구성이면 이 상한을 넘는다.
    assert len(card["pending"]["options"]) <= 4


# ── C. 방장 확인 ─────────────────────────────────────────────────────

def test_nonowner_confirm_does_not_apply(fake_extract):
    """방장이 아닌 사람의 '네'는 확정이 되면 안 된다."""
    card = pending_owner_card(fake_extract)
    E.turn(card, "네", by="h-daughter", is_owner=False)
    assert status(card, "phone") == S.PENDING_OWNER


def test_owner_free_answer_drops_pending_confirmation(fake_extract):
    """방장 확인 대기 중 방장의 자유 대답이 추출에 걸리면, 대기 중이던
    확인 질문이 조용히 사라지면 안 된다."""
    card = pending_owner_card(fake_extract)
    msg2 = "전화번호가 010-1111-2222로 바뀌었어요"
    fake_extract[msg2] = [u("phone", "010-1111-2222")]
    E.turn(card, msg2, by="h-owner", is_owner=True)
    assert card["pending"] is not None
    assert card["pending"]["kind"] == "owner_confirm"


# ── D. 뺄 것 ─────────────────────────────────────────────────────────

def test_exclude_value_with_particles_not_normalized(fake_extract):
    """AI가 조사까지 붙여 돌려줘도('바비큐는 빼주세요') 섹션에서 빠져야 한다."""
    fake_extract["펜션이고 바비큐장, 객실 소개할래요"] = [
        u("business_type", "펜션"), u("sections", "바비큐장"), u("sections", "객실 소개")]
    fake_extract["아 바비큐는 빼주세요"] = [u("exclude", "바비큐는 빼주세요")]
    card = E.new_card()
    E.turn(card, "펜션이고 바비큐장, 객실 소개할래요")
    E.turn(card, "아 바비큐는 빼주세요")
    assert card["slots"]["sections"]["value"] == ["객실 소개"]


def test_exclude_substring_removes_compound_section(fake_extract):
    """'바비큐' 제외가 '바비큐장' 섹션을 치우는 현재 동작을 기록한다."""
    fake_extract["펜션이고 바비큐장, 객실 소개할래요"] = [
        u("business_type", "펜션"), u("sections", "바비큐장"), u("sections", "객실 소개")]
    fake_extract["아 바비큐는 빼주세요"] = [u("exclude", "바비큐")]
    card = E.new_card()
    E.turn(card, "펜션이고 바비큐장, 객실 소개할래요")
    E.turn(card, "아 바비큐는 빼주세요")
    assert card["slots"]["sections"]["value"] == ["객실 소개"]


# ── E. 업종 변경 ─────────────────────────────────────────────────────

def test_industry_change_refreshes_assumed_sections(fake_extract):
    """템플릿(펜션)으로 시작해 '카페예요'라고 바꾸면, 가정된 섹션도
    카페 기본값으로 바뀌어야 한다."""
    card = E.new_card("pension")
    fake_extract["사실 카페예요"] = [u("business_type", "카페")]
    E.turn(card, "사실 카페예요")
    assert card["industry"] == "cafe"
    assert card["slots"]["sections"]["value"] == list(S.INDUSTRIES["cafe"].default_sections)


# ── F. 거절 후 다시 요청 ──────────────────────────────────────────────

def test_reject_then_correct_after_finalize(fake_extract):
    """건너뛰기로 확정한 뒤 '가격은 3만원이에요'라고 고치면 반영돼야 한다."""
    card = E.new_card()
    E.turn(card, "안녕하세요")
    r = E.turn(card, "시안 먼저 보여주세요")
    assert r["done"]
    msg = "가격은 3만원이에요"
    fake_extract[msg] = [u("price", "3만원")]
    r2 = E.turn(card, msg)
    assert r2["done"]
    assert card["slots"]["price"]["value"] == "3만원"
    assert status(card, "price") == S.FILLED


def test_needless_area_can_be_rejected(fake_extract):
    """'목적은 필요 없어요'라고 하면 그 영역은 다시 묻지 않아야 한다."""
    card = E.new_card()
    fill_cafe_minus_goal(fake_extract, card)
    assert card["pending"]["slot"] == "goal"
    E.turn(card, "목적은 필요 없어요")
    assert status(card, "goal") == S.REJECTED


def test_confirm_shape_never_used(fake_extract):
    """가정값이 있어도 확인형 질문('{value}로 할까요?')은 나오지 않음을 기록한다."""
    card = E.new_card()
    fill_cafe_minus_goal(fake_extract, card)
    r2 = E.turn(card, S.LET_AI)  # 목적을 가정으로 채움
    assert status(card, "goal") == S.ASSUMED
    texts = []
    if not r2["done"]:
        texts.append(r2["question"]["text"])
        r3 = E.turn(card, "없음")
        if not r3["done"] and r3["question"]:
            texts.append(r3["question"]["text"])
    assert not any("할까요" in t for t in texts)


# ── G. 질문 상한 ─────────────────────────────────────────────────────

def test_question_cap_placeholders_and_done(fake_extract):
    """8회 상한에 닿으면 사실 칸은 자리 표시로 마쳐야 한다."""
    card = E.new_card()
    for _ in range(12):
        r = E.turn(card, "음")
        if r["done"]:
            break
    assert card["done"] and card["asked"] == S.MAX_QUESTIONS
    assert status(card, "phone") == S.PLACEHOLDER
    assert status(card, "location") == S.PLACEHOLDER
    assert card["hidden"]["asked"] is True


def test_facts_on_last_allowed_turn_survive(fake_extract):
    """마지막 질문 기회에 말한 사실은 상한 정리 때 지워지면 안 된다."""
    card = E.new_card()
    for _ in range(7):
        E.turn(card, "음")
    msg = "전화는 010-0000-7777이에요"
    fake_extract[msg] = [u("phone", "010-0000-7777")]
    E.turn(card, msg)
    r = E.turn(card, "음")
    assert r["done"]
    assert status(card, "phone") == S.FILLED


def test_chatter_consumes_question_budget(fake_extract):
    """질문과 무관한 잡담은 질문 횟수를 쓰지 않아야 한다."""
    card = E.new_card()
    fake_extract["카페예요"] = [u("business_type", "카페")]
    E.turn(card, "카페예요")
    assert card["asked"] == 1
    E.turn(card, "오늘 날씨가 좋네요")
    assert card["asked"] == 1


def test_empty_message_consumes_question_budget(fake_extract):
    """빈 메시지는 질문 횟수를 쓰지 않아야 한다."""
    card = E.new_card()
    E.turn(card, "")
    assert card["asked"] == 0


# ── H. 추출 실패 ─────────────────────────────────────────────────────

def test_extract_exception_keeps_conversation(monkeypatch):
    """추출 호출이 매번 터져도 대화는 멈추지 않아야 한다."""
    calls = []

    def broken(system, user, **kw):
        calls.append(1)
        raise RuntimeError("nim down")

    monkeypatch.setattr(llm, "chat_json", broken)
    card = E.new_card()
    r = E.turn(card, "카페예요")
    assert r["question"]["slot"] == "business_type"
    assert len(calls) == 1  # 예외는 즉시 빈 목록으로 (재시도 없음)


# ── I. 숫자 표기 ─────────────────────────────────────────────────────

def test_korean_numeral_phone_normalized(fake_extract):
    """한글 숫자 전화('공일공…')는 숫자 형태로 정규화돼야 한다."""
    msg = "전화번호는 공일공 일일일일 이이이이예요"
    fake_extract[msg] = [u("phone", "공일공 일일일일 이이이이")]
    card = E.new_card()
    E.turn(card, msg)
    assert status(card, "phone") == S.FILLED
    assert digits(card["slots"]["phone"]["value"]) == "01011112222"


def test_fullwidth_digits_fact_kept(fake_extract):
    """전각 숫자 전화는 AI가 반각으로 돌려줘도 근거 있음으로 봐야 한다."""
    msg = "전화는 ０１０-１１１１-２２２２예요"
    fake_extract[msg] = [u("phone", "010-1111-2222")]
    card = E.new_card()
    E.turn(card, msg)
    assert status(card, "phone") == S.FILLED


# ── J. 길이·잡담 ──────────────────────────────────────────────────────

def test_very_long_message_no_crash(fake_extract):
    """아주 긴 메시지에도 추출 반영과 질문이 정상이어야 한다."""
    msg = "모퉁이커피 " + "가" * 5000
    fake_extract[msg] = [u("shop_name", "모퉁이커피")]
    card = E.new_card()
    fake_extract["카페예요"] = [u("business_type", "카페")]
    E.turn(card, "카페예요")
    r = E.turn(card, msg)
    assert r["applied"] == ["shop_name"]
    assert r["question"] is not None


def test_unrelated_chatter_keeps_pending(fake_extract):
    """잡담 뒤에도 직전 질문(가게 이름)이 유지돼야 한다."""
    card = E.new_card()
    fake_extract["카페예요"] = [u("business_type", "카페")]
    r = E.turn(card, "카페예요")
    assert r["question"]["slot"] == "shop_name"
    r2 = E.turn(card, "오늘 날씨가 좋네요")
    assert r2["question"]["slot"] == "shop_name"


# ── K. 선택지 개수·진행 표시 ──────────────────────────────────────────

def test_single_choice_option_count_within_four(fake_extract):
    """한 칸 질문의 선택지는 합계 4개 이하, 마지막은 '알아서 해주세요'다."""
    card = E.new_card()
    r = E.turn(card, "안녕하세요")
    q = r["question"]
    assert q["kind"] == "single" and q["slot"] == "business_type"
    assert len(q["options"]) <= S.MAX_OPTIONS + 1
    assert q["options"][-1] == S.LET_AI


def test_progress_indicator_format(fake_extract):
    """질문에는 진행 표시(질문 n/8)와 건너뛰기 안내가 있어야 한다."""
    card = E.new_card()
    r = E.turn(card, "안녕하세요")
    text = E.format_question(card, r["question"])
    assert f"질문 1/{S.MAX_QUESTIONS}" in text
    assert "시안 먼저" in text


def test_shop_name_let_ai_placeholder_not_assumed(fake_extract):
    """가게 이름은 '알아서 해주세요'여도 지어내지 않고 자리 표시다."""
    card = E.new_card()
    fake_extract["카페예요"] = [u("business_type", "카페")]
    E.turn(card, "카페예요")
    E.turn(card, S.LET_AI)
    assert status(card, "shop_name") == S.PLACEHOLDER


def test_pending_single_free_answer_applies_and_clears(fake_extract):
    """대기 중 자유 대답은 해당 칸에 들어가고 다음 질문으로 넘어간다."""
    card = E.new_card()
    fake_extract["카페예요"] = [u("business_type", "카페")]
    E.turn(card, "카페예요")
    msg = "바다정원 펜션"
    fake_extract[msg] = [u("shop_name", "바다정원 펜션")]
    r = E.turn(card, msg)
    assert r["applied"] == ["shop_name"]
    assert r["question"]["slot"] == "offerings"


def test_skip_word_not_recognized(fake_extract):
    """'건너뛰고 시안 보여줘' 같은 건너뛰기 말도 마무리가 돼야 한다."""
    card = E.new_card()
    E.turn(card, "안녕하세요")
    r = E.turn(card, "건너뛰고 시안 보여줘")
    assert r["done"]
