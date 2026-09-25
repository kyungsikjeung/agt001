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
