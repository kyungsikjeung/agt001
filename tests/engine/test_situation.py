"""상황 탐색 J1b (BUILD_W1_W2 §1.6, D53 ③). DB 없이 돌아간다.

llm.chat_json을 가짜로 바꿔서 probe 선택·검증·폴백을 검사한다.
"""
import json

from app import llm
from app.services import card_data
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services import situation


def _card(industry, **slots):
    card = E.new_card(industry)
    for key, value in slots.items():
        E._put(card, key, value, S.FILLED, 1)
    card["turn"] = 1
    return card


def _full_cafe(**slots):
    """필수 칸을 다 채운 카페 카드 (상황 탐색이 붙을 상태)."""
    base = {"business_type": "카페", "shop_name": "모퉁이커피",
            "offerings": ["아메리카노", "라떼"], "hours": "10시~21시",
            "contact_method": "전화", "goal": "가게 알리기"}
    base.update(slots)
    card = _card("cafe", **base)
    card["hidden"] = {"asked": True, "selected": []}
    return card


def _fake_slots(monkeypatch, picked=None, fail=False, seen=None):
    def fake(system, user, **kw):
        if seen is not None:
            seen.append(user)
        if fail:
            raise RuntimeError("nim down")
        return json.dumps({"slots": picked if picked is not None else []}, ensure_ascii=False)
    monkeypatch.setattr(llm, "chat_json", fake)


def test_probe_picks_allowed_slots(monkeypatch):
    seen = []
    _fake_slots(monkeypatch, ["order_mode", "menu_categories"], seen=seen)
    card = _card("cafe", business_type="카페", offerings=["아메리카노"])
    out = situation.probe(card)
    assert [q["slot"] for q in out] == ["order_mode", "menu_categories"]
    for q in out:
        assert q["text"] and 1 <= len(q["options"]) <= S.MAX_OPTIONS + 1
        assert q["options"][-1] == S.LET_AI
    # 전화·주소는 LLM에 주지 않는다
    E._put(card, "phone", "010-0000-1111", S.FILLED, 1)
    E._put(card, "location", "부산 해운대", S.FILLED, 1)
    situation.probe(card)
    assert "010-0000-1111" not in seen[-1] and "해운대" not in seen[-1]


def test_probe_drops_disallowed_and_dupes(monkeypatch):
    _fake_slots(monkeypatch, ["team_mode", "order_mode", "order_mode", "phone", "menu_categories"])
    card = _card("cafe", business_type="카페")
    assert [q["slot"] for q in situation.probe(card)] == ["order_mode", "menu_categories"]


def test_probe_truncates_to_three(monkeypatch):
    monkeypatch.setattr(situation, "ALLOWED", {"A": ("order_mode", "menu_categories", "team_mode", "goal")})
    monkeypatch.setattr(situation, "QUESTIONS",
                        {**situation.QUESTIONS, "goal": ("사이트 목적은 무엇인가요?", ("1", "2"))})
    _fake_slots(monkeypatch, ["goal", "team_mode", "menu_categories", "order_mode"])
    card = _card("cafe", business_type="카페")
    assert [q["slot"] for q in situation.probe(card)] == ["goal", "team_mode", "menu_categories"]


def test_probe_falls_back_to_default_on_error(monkeypatch):
    _fake_slots(monkeypatch, fail=True)
    assert [q["slot"] for q in situation.probe(_card("cafe"))] == ["order_mode", "menu_categories"]
    assert [q["slot"] for q in situation.probe(_card("salon"))] == ["team_mode"]
    # 형식 오류(추출 응답)도 기본값
    monkeypatch.setattr(llm, "chat_json", lambda s, u, **kw: json.dumps({"updates": []}))
    assert [q["slot"] for q in situation.probe(_card("cafe"))] == ["order_mode", "menu_categories"]


def test_probe_skips_known_slots(monkeypatch):
    _fake_slots(monkeypatch, ["order_mode", "menu_categories"])
    card = _card("cafe", business_type="카페", order_mode="매장 방문")
    assert [q["slot"] for q in situation.probe(card)] == ["menu_categories"]
    card = _card("cafe", business_type="카페")
    E._put(card, "order_mode", None, S.REJECTED, 1)
    assert [q["slot"] for q in situation.probe(card)] == ["menu_categories"]


def test_probe_skips_inferred_slots(monkeypatch):
    _fake_slots(monkeypatch, ["team_mode"])
    team = _card("salon", staff=["원장 김미용(컷)", "실장 박하나(염색)"])
    assert situation.probe(team) == []  # 담당자 2명 이상이면 team_mode 생략
    _fake_slots(monkeypatch, ["order_mode", "menu_categories"])
    pickup = _card("cafe", contact_method="픽업 주문")
    assert [q["slot"] for q in situation.probe(pickup)] == ["menu_categories"]
    # 원형 C는 물을 것이 없다
    assert situation.probe(_card("pension")) == []


def test_situation_questions_do_not_use_budget(monkeypatch):
    _fake_slots(monkeypatch, ["order_mode"])
    card = _full_cafe()
    asked = card["asked"]
    r = E._ask_next(card, [], {})
    q = r["question"]
    assert q["slot"] == "order_mode" and q.get("budget_free") is True
    assert card["asked"] == asked and card.get("situation_probed") is True
    r = E.turn(card, "픽업 주문")
    assert card["asked"] == asked  # 답한 뒤에도 한도는 그대로
    assert card["slots"]["order_mode"]["value"] == "픽업 주문"
    assert card_data.build(card)["mode"] == "pickup"


def test_skip_jumps_over_situation(monkeypatch):
    _fake_slots(monkeypatch, ["order_mode", "menu_categories"])
    card = E.new_card()
    r = E.turn(card, "안녕하세요")
    r = E.turn(card, "시안 먼저 보여주세요")
    assert r["done"] and r["question"] is None
    assert card.get("followup_queue") in (None, [])


def test_card_data_reads_new_slots():
    solo = _card("salon", team_mode="혼자")
    assert card_data.build(solo)["mode"] == "solo"
    team = _card("salon", team_mode="2~3명")
    assert card_data.build(team)["mode"] == "team"
    team2 = _card("salon", team_mode="4명 이상")
    assert card_data.build(team2)["mode"] == "team"
    pickup = _card("cafe", order_mode="픽업 주문")
    assert card_data.build(pickup)["mode"] == "pickup"
    visit = _card("cafe", order_mode="매장 방문")
    assert card_data.build(visit)["mode"] == "dinein"


def test_card_data_uses_menu_categories_order():
    card = _card("cafe", offerings=["아메리카노", "딸기라떼", "바스크치즈케이크", "감자샐러드"],
                menu_categories=["디저트", "커피", "음료"])
    cats = card_data.build(card)["catalog"]
    assert [c["name"] for c in cats] == ["디저트", "커피", "음료"]
    by_name = {c["name"]: [i["name"] for i in c["items"]] for c in cats}
    assert by_name["커피"] == ["아메리카노"] and by_name["음료"] == ["딸기라떼"]
    assert by_name["디저트"] == ["바스크치즈케이크", "감자샐러드"]  # 낱말표에 없으면 첫 분류
