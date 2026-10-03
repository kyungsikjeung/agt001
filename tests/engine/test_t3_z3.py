"""T3 z3·T2 r3 실패 재발 방지 (2026-10-01): 같은 메시지 값 덮어쓰기, 체크인 라벨, 편의 항목, 말로 한 시각."""
import json

from app import llm
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services import validate as V


def fake_setup(monkeypatch, table):
    def fake(system, user, **kw):
        text = user.split("[사장님 메시지] ", 1)[-1]
        return json.dumps({"updates": table.get(text, [])}, ensure_ascii=False)

    monkeypatch.setattr(llm, "chat_json", fake)


def u(slot, value):
    return {"slot": slot, "value": value}


def test_same_message_hours_are_joined_not_overwritten():
    # pension-talkative: "체크인 3시" + "체크아웃 11시"가 따로 오면 뒤엣것만 남던 문제
    card = E.new_card("pension")
    text = "체크인은 오후 3시 체크아웃은 11시예요."
    E.apply_updates(card, [u("hours", "체크인 오후 3시"), u("hours", "체크아웃 11시")], text)
    value = card["slots"]["hours"]["value"]
    assert "체크인" in value and "3시" in value and "체크아웃" in value and "11시" in value


def test_checkin_label_is_kept_in_value():
    # 업종 라벨 "체크인·아웃 시간"의 "체크인"을 떼면 체크아웃과 구별이 안 된다
    card = E.new_card("pension")
    E.apply_updates(card, [u("hours", "체크인은 오후 3시 체크아웃은 11시")], "체크인은 오후 3시 체크아웃은 11시예요.")
    assert card["slots"]["hours"]["value"].startswith("체크인")


def test_same_message_prices_and_targets_are_joined():
    # T2 e025(가격 둘), e016(대상 둘): 단일 칸이라 마지막 값만 남던 문제
    card = E.new_card("restaurant")
    text = "칼국수 8천원, 수육 2만원이고 동네 주민들이랑 학생들이 많이 와요."
    E.apply_updates(card, [u("price", "8천원"), u("price", "2만원"),
                           u("target", "동네 주민"), u("target", "학생")], text)
    assert "8천원" in card["slots"]["price"]["value"] and "2만원" in card["slots"]["price"]["value"]
    assert card["slots"]["target"]["value"] == "동네 주민, 학생"


def test_name_is_not_joined_in_same_message():
    card = E.new_card("cafe")
    E.apply_updates(card, [u("shop_name", "작은숲"), u("shop_name", "큰숲")], "작은숲, 아니 큰숲이에요")
    assert card["slots"]["shop_name"]["value"] == "큰숲"


def test_amenity_is_not_offering_on_first_message(monkeypatch):
    # restaurant-changes_mind: 첫 메시지 "포장·배달 안내"가 메뉴로 들어가 메뉴 질문을 건너뛰던 문제
    msg = "고깃집 사이트요. 매일 11시부터 9시까지고 포장·배달 안내도 넣고 전화로 연락 받으려구요."
    fake_setup(monkeypatch, {msg: [u("business_type", "고깃집"), u("offerings", "포장·배달"),
                                   u("contact_method", "전화")]})
    card = E.new_card()
    E.turn(card, msg)
    assert not card["slots"].get("offerings") or card["slots"]["offerings"]["status"] == S.EMPTY
    assert "takeout" in card["hidden"]["selected"]


def test_offerings_emptied_by_exclude_are_asked_again():
    card = E.new_card("restaurant")
    E.apply_updates(card, [u("offerings", "삼겹살")], "삼겹살 팔아요")
    E.apply_updates(card, [u("exclude", "삼겹살")], "삼겹살은 빼주세요")
    assert card["slots"]["offerings"]["status"] == S.EMPTY
    card["slots"]["shop_name"] = {"value": "숯불향", "status": S.FILLED, "evidence": [], "by": None}
    assert E.next_question(card)["slot"] == "offerings"


def test_hours_question_asks_time_directly():
    # salon-terse 9회: "매일 같은 시간" 고른 뒤 "몇 시부터?"를 또 묻던 질문 하나를 없앤다
    q = S.question_for(S.INDUSTRIES["salon"], "hours")
    assert "몇 시부터" in q.ask
    assert "매일 같은 시간" not in q.options


def test_spoken_hours_pass_validation():
    # T2 e037·e045: "열 시부터 여덟 시까지"가 '숫자 없음'으로 막혀 저장되지 않던 문제
    assert V.check_hours("오전 열 시부터 저녁 여덟 시까지 해요") is None
    assert V.check_hours("수요일 토요일 두 시부터") is None
    assert V.check_hours("두 시간 수업") is not None  # 걸리는 시간은 시각이 아니다
    card = E.new_card()
    text = "매주 월요일 쉬고, 오전 열 시부터 저녁 여덟 시까지 해요"
    E.apply_updates(card, [u("hours", "오전 열 시부터 저녁 여덟 시까지")], text)
    assert card["slots"]["hours"]["status"] == S.FILLED
