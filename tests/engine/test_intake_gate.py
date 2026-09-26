"""입구 게이트 (INTAKE_GATE_DESIGN.md §2~§6): 종류 분류·프로필·기능 판정·예산·금지 요청.

실제 사례(첼로 레슨 + 카카오톡 문의)가 가게 질문으로 새지 않고 기능 요구가 버려지지 않는지 본다.
"""
import json

import pytest

from app import llm
from app.services import intake
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


CELLO = "첼로 레슨 사이트를 만들고 싶어요. 문의 내용이 제 카카오톡으로 오게 해 주세요"


def test_cello_goes_to_individual_profile_and_keeps_kakao_request(fake_extract):
    fake_extract[CELLO] = [u("business_type", "첼로 레슨"), u("features", "문의 내용이 카카오톡으로 전송")]
    card = E.new_card()
    r = E.turn(card, CELLO)
    assert card["industry"] == "individual"
    # 기능 요구는 판정되고, 확인 질문이 필수 칸보다 먼저 나온다
    v = card["features_judged"][0]
    assert v["id"] == "kakao_form_bridge" and v["verdict"] == intake.ALTERNATIVE
    assert r["question"]["kind"] == "feature"
    ack = E.ack_text(card, r["applied"])
    assert "카카오톡" in ack or "카톡" in ack
    # 가게 질문(주차·배송)이 아니라 개인 프로필 질문
    assert "주차" not in r["question"]["text"]
    # 예산: 개인 7 + 확인 기능 1
    assert E.budget(card) == S.BUDGETS["individual"] + 1
    r2 = E.turn(card, "사이트 문의 양식 + 채팅방 알림")
    assert card["feature_answers"]["kakao_form_bridge"] == "사이트 문의 양식 + 채팅방 알림"
    assert r2["question"]["kind"] == "single"
    assert S.question_for(S.INDUSTRIES["individual"], r2["question"]["slot"]).ask == r2["question"]["text"]


def test_unknown_business_asks_site_kind_once(fake_extract):
    fake_extract["회계사무소 사이트요"] = [u("business_type", "회계사무소")]
    card = E.new_card()
    r = E.turn(card, "회계사무소 사이트요")
    assert r["question"]["kind"] == "site_kind"
    assert r["question"]["options"] == list(S.KIND_OPTIONS)
    E.turn(card, "개인·전문가")
    assert card["industry"] == "individual"
    # 업종을 다시 말해도 '기타'로 되돌아가지 않는다
    fake_extract["세무 상담도 해요"] = [u("business_type", "세무 상담")]
    E.turn(card, "세무 상담도 해요")
    assert card["industry"] == "individual"


def test_site_kind_free_answer_not_asked_again(fake_extract):
    fake_extract["회계사무소 사이트요"] = [u("business_type", "회계사무소")]
    card = E.new_card()
    E.turn(card, "회계사무소 사이트요")
    r = E.turn(card, "음 그냥 사무실이에요")
    assert r["question"] is None or r["question"]["kind"] != "site_kind"


def test_group_and_webservice_profiles(fake_extract):
    fake_extract["독서 모임 사이트"] = [u("business_type", "독서 모임")]
    card = E.new_card()
    E.turn(card, "독서 모임 사이트")
    assert card["industry"] == "group" and E.budget(card) == 8
    fake_extract["중고거래 앱 소개 사이트"] = [u("business_type", "중고거래 앱")]
    card2 = E.new_card()
    E.turn(card2, "중고거래 앱 소개 사이트")
    assert card2["industry"] == "webservice" and E.budget(card2) == 12


def test_out_of_beta_feature_goes_to_later_list(fake_extract):
    msg = "카페예요. 온라인 결제도 되게 해 주세요"
    fake_extract[msg] = [u("business_type", "카페"), u("features", "온라인 결제")]
    card = E.new_card()
    r = E.turn(card, msg)
    assert card["later"] == ["결제·온라인 판매"]
    assert "베타" in E.ack_text(card, r["applied"])
    assert r["question"]["kind"] != "feature"  # 베타 밖 기능은 확인 질문 없이 알리기만
    assert "베타 뒤" in E.summary_text(card)
    assert E.budget(card) == S.MAX_QUESTIONS


def test_ready_feature_in_spec(fake_extract):
    msg = "펜션이고 네이버 예약 연결해 주세요"
    fake_extract[msg] = [u("business_type", "펜션"), u("features", "네이버 예약 연결")]
    card = E.new_card()
    E.turn(card, msg)
    E.turn(card, "시안 먼저")
    spec = E.spec_text(card)
    assert "기능 구현 방법" in spec and "예약" in spec


def test_confirm_bonus_capped(fake_extract):
    msg = "카페"
    fake_extract[msg] = [u("business_type", "카페"),
                         u("features", "카톡 채널 연결, 수강 신청, 인스타그램 연동, 행사 신청, 쿠폰 이벤트, 다국어")]
    card = E.new_card()
    E.turn(card, msg)
    assert E.budget(card) == S.MAX_QUESTIONS + S.FEATURE_BONUS_MAX


def test_blocked_request_refused_without_spending_budget(fake_extract):
    card = E.new_card()
    r = E.turn(card, "바카라 홍보 사이트 만들어 주세요")
    assert r["blocked"] and card["asked"] == 0 and not card["slots"]


def test_chatter_twice_nudges_once(fake_extract):
    card = E.new_card()
    E.turn(card, "")
    r1 = E.turn(card, "오늘 날씨가 참 좋네요")
    assert not r1.get("nudge")
    r2 = E.turn(card, "점심은 뭐 먹을까요 고민이에요")
    assert r2.get("nudge") and r2["question"]
    r3 = E.turn(card, "저녁엔 비가 온대요 그렇죠")
    assert not r3.get("nudge")  # 한 번 말했으면 다시 두 번 쌓일 때까지 조용히


def test_multi_select_keeps_extra_words(fake_extract):
    """여러 개 고르기에 덧붙인 말은 버리지 않고 안내 메모로 남긴다(사용자 요청 9/26)."""
    msg = "펜션이에요 바다정원"
    fake_extract[msg] = [u("business_type", "펜션"), u("shop_name", "바다정원"), u("offerings", "객실 3개")]
    card = E.new_card()
    r = E.turn(card, msg)
    assert r["question"]["kind"] == "multi"
    E.turn(card, "반려동물 동반, 주차 — 소형견만 가능하고 주차는 2대예요")
    assert set(card["hidden"]["selected"]) == {"pet", "parking"}
    assert "소형견만" in card["hidden"]["note"]
    assert "소형견만" in E.summary_text(card)


def test_short_answer_goes_to_asked_slot_not_repeated(fake_extract):
    """T3 G3: 한 칸 질문의 짧은 답을 추출이 다른 칸으로 보내도 물은 칸을 채우고 같은 질문을 반복하지 않는다."""
    fake_extract["학원이에요 넘버원"] = [u("business_type", "학원"), u("shop_name", "넘버원")]
    card = E.new_card()
    E.turn(card, "학원이에요 넘버원")
    # 필수 칸 순서대로 오다가 offerings를 물을 때까지 진행
    for _ in range(6):
        q = card["pending"]
        if q and q.get("slot") == "offerings":
            break
        E.turn(card, "알아서 해주세요" if q and q.get("kind") == "single" else "없음")
    assert card["pending"]["slot"] == "offerings"
    fake_extract["초등 미술반"] = [u("target", "초등")]  # 추출이 대상 칸으로 잘못 보냄
    r = E.turn(card, "초등 미술반")
    assert card["slots"]["offerings"]["value"] == ["초등 미술반"]
    assert not (r["question"] and r["question"].get("slot") == "offerings")
