"""질문 수 줄이기 (STATUS §4 #1: T3 평균 5.9회, 목표 3회). 가짜 AI만 쓴다."""
import json

from app import llm
from app.services import prd_engine as E
from app.services import prd_schema as S
from evals import run_simulation as R


def fake_setup(monkeypatch, table):
    def fake(system, user, **kw):
        text = user.split("[사장님 메시지] ", 1)[-1]
        return json.dumps({"updates": table.get(text, [])}, ensure_ascii=False)

    monkeypatch.setattr(llm, "chat_json", fake)


def u(slot, value):
    return {"slot": slot, "value": value}


def _cafe_at(card_q_slot, monkeypatch, table):
    """카페 카드를 card_q_slot 질문 직전까지 채운다."""
    fake_setup(monkeypatch, table)
    card = E.new_card("cafe")
    for key, value in (("business_type", "카페"), ("shop_name", "모퉁이커피"),
                       ("offerings", ["아메리카노"]), ("price", "4,500원")):
        E._put(card, key, value, S.FILLED, 1)
    card["hidden"] = {"asked": True, "selected": []}
    q = E.next_question(card)
    assert q["slot"] == card_q_slot
    card["pending"] = q
    card["asked"] = 4
    return card


def test_hours_question_asks_time_directly(monkeypatch):
    """영업시간은 한 번에 받는다: '매일 같은 시간'을 고르면 또 묻던 두 단계를 없앴다."""
    card = _cafe_at("hours", monkeypatch, {"매일 10~21시요": [u("hours", "매일 10~21시")]})
    assert "매일 같은 시간" not in card["pending"]["options"]
    assert "예:" in card["pending"]["text"]
    r = E.turn(card, "매일 10~21시요")
    assert card["slots"]["hours"]["status"] == S.FILLED
    assert r["question"]["slot"] != "hours"


def test_hours_without_numbers_asks_once_more(monkeypatch):
    """숫자 없이 답하면 시간만 한 번 이어 묻는다."""
    card = _cafe_at("hours", monkeypatch, {"매일 같아요": [u("hours", "매일")]})
    r = E.turn(card, "매일 같아요")
    assert r["question"]["kind"] == "followup" and r["question"]["slot"] == "hours"


def test_no_price_reask_after_menu_and_price_question(monkeypatch):
    """'대표 메뉴와 가격'을 물었는데 메뉴만 답하면 가격을 또 묻지 않는다."""
    fake_setup(monkeypatch, {"아메리카노, 라떼": [u("offerings", "아메리카노, 라떼")]})
    card = E.new_card("cafe")
    E._put(card, "business_type", "카페", S.FILLED, 1)
    E._put(card, "shop_name", "모퉁이커피", S.FILLED, 1)
    card["hidden"] = {"asked": True, "selected": []}
    q = E.next_question(card)
    assert q["slot"] == "offerings"
    assert "가격" in q["text"]
    card["pending"] = q
    r = E.turn(card, "아메리카노, 라떼")
    assert card["slots"]["offerings"]["status"] == S.FILLED
    assert not (r["question"] and r["question"]["slot"] == "price")
    assert not any(i["slot"] == "price" for i in card.get("followup_queue") or [])


def test_price_still_asked_when_question_did_not_ask_price(monkeypatch):
    """펜션 객실 질문은 요금을 묻지 않으므로 요금은 이어 묻는다."""
    fake_setup(monkeypatch, {"방 3개요": [u("offerings", "객실 3개")]})
    card = E.new_card("pension")
    E._put(card, "business_type", "펜션", S.FILLED, 1)
    E._put(card, "shop_name", "바다소리", S.FILLED, 1)
    card["pending"] = {"slot": "offerings", "kind": "single", "options": [S.LET_AI],
                       "text": S.question_for(S.INDUSTRIES["pension"], "offerings").ask}
    r = E.turn(card, "방 3개요")
    assert r["question"]["kind"] == "followup" and r["question"]["slot"] == "price"


def test_change_midway_does_not_spend_budget(monkeypatch):
    """질문 도중 다른 값을 바꾸면 같은 질문을 다시 보이되 질문 수는 늘지 않는다 (T3 cafe-changes_mind)."""
    card = _cafe_at("hours", monkeypatch, {"라떼는 5천5백원으로 바꿔주세요": [u("price", "라떼 5천5백원")]})
    asked = card["asked"]
    r = E.turn(card, "라떼는 5천5백원으로 바꿔주세요")
    assert r["question"]["slot"] == "hours"
    assert card["asked"] == asked


def test_eval_does_not_count_reshown_question():
    """평가: 도중 변경 말 뒤에 같은 질문을 다시 보인 것은 질문 수에 넣지 않는다."""
    q = {"slot": "hours", "kind": "single", "text": "영업시간을 알려 주세요.", "options": ["나중에 넣을게요"]}
    script = iter([{"question": q, "done": False}, {"question": q, "done": False},
                   {"question": None, "done": True}])

    class Eng:
        def new_card(self, sc):
            return {"asked": 1, "slots": {}}

        def turn(self, card, text, by=None, is_owner=True):
            return next(script)

    sc = {"id": "t", "first_message": "카페요", "facts": {"hours": "매일 10~21시"},
          "changes": [{"after_question": 1, "say": "라떼 가격 바꿔주세요"}],
          "expect": {"required": []}}
    res = R.run_dialogue(sc, Eng(), lambda prompt: "매일 10~21시")
    assert len(res["questions"]) == 2 and res["questions"][1]["reshown"]
    assert R.score_dialogue(sc, res)["questions"] == 1
