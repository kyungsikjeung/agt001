"""T3 r5 수정 3건 테스트 (근거 공용 기준·모름 닫기·막연한 값 버리기).

가짜 AI(llm.chat_json monkeypatch)만 쓴다. 작성법은 test_followup_v0.py(fake_setup)와
test_intake_gate.py(fake_extract)를 따른다.
"""
import json

import pytest

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


# ── A: 근거 공용 기준 ─────────────────────────────────────────────

# 과제 표 그대로 (history는 사장님 원문).
# 경계 사례 ("방에서 바다 전망", "방에서 바다가 보여요")는 False로 둔다.
# 판단: "전망"이라는 핵심 명사가 원문에 없어 지어냄으로 본다. 뜻은 가깝지만
# 슬롯 오기입(방 설명이 offerings에)까지 구제하지 않기 위해 탈락이 맞다.
GROUNDED_TABLE = [
    (True, "카카오톡 채널로 연락 받기", "카톡 채널로 연락 주세요"),
    (True, "카카오톡 채널로 신청 받기", "카톡 채널로 신청 받고 수업 안내랑 작품 사진 넣고 싶어요"),
    (True, "전화로 예약 받기", "전화로 예약 받으려구요"),
    (True, "네이버 예약 연동", "매일 10시부터 8시까지고 네이버 예약으로 받아요"),
    (True, "피아노 그룹반", "반 구성는 피아노 개인반, 그룹반예요"),
    (True, "객실 3개", "객실 3개 있어요"),
    (False, "많음", "메뉴 많은데 뭘 넣어야 할지"),
    (False, "메뉴판 구성", "메뉴판도 뭘 넣어야 할지 모르겠어요"),
    (False, "캔들 만들기", "캔들 만드는데 뭘 넣어야 할지"),
    (False, "초등학생", "영어 학원 사이트요. 고등 내신반 있고"),
    (False, "방에서 바다 전망", "방에서 바다가 보여요"),
    (False, "단체 수업", "원데이 클래스 3만5천원이고 정규반도 있어요"),
]


@pytest.mark.parametrize(("want", "value", "history"), GROUNDED_TABLE)
def test_grounded_phrase_table(want, value, history):
    assert E.grounded_phrase(value, history) is want


def test_in_history_uses_same_rule():
    # 느슨했던 쪽: 낱말 하나 겹친다고 근거가 아니다
    assert E._in_history("메뉴판 구성", "메뉴판도 뭘 넣어야 할지 모르겠어요") is False
    # 엄격했던 쪽: 별칭·어미 바꿔말은 근거로 본다
    assert E._in_history("카카오톡 채널로 연락 받기", "카톡 채널로 연락 주세요") is True


def _score_with(slot, value, owner_said):
    from evals import run_simulation as rs
    facts = {}
    sc = {"id": "t3r5", "industry": "cafe", "expect": {"required": []}, "facts": facts, "unknown": []}
    card = {"slots": {slot: {"value": value, "status": S.FILLED, "evidence": [], "by": None}},
            "hidden": {"asked": True, "selected": []}, "asked": 1}
    res = {"final_card": card,
           "transcript": [{"role": "사장님", "name": "사장님", "text": owner_said}],
           "questions": [], "current_facts": facts, "confirmed": True, "turns": 1}
    return rs.score_dialogue(sc, res)


def test_scorer_forgives_paraphrase():
    score = _score_with("features", "카카오톡 채널로 신청 받기", "카톡 채널로 신청 받고 싶어요")
    assert score["invented"] == []


def test_scorer_keeps_vague_invented():
    score = _score_with("goal", "메뉴판 구성", "메뉴판도 뭘 넣어야 할지 모르겠어요")
    assert any(i["slot"] == "goal" for i in score["invented"])


# ── B: "모르겠어요"로 닫기 ────────────────────────────────────────

def test_dontknow_closes_single(monkeypatch):
    fake_setup(monkeypatch, {})
    card = E.new_card("cafe")
    card["pending"] = {"slot": "goal", "kind": "single",
                       "options": ["예약·문의 늘리기", S.LET_AI], "text": "?"}
    r = E.turn(card, "잘 모르겠어요")
    assert card["slots"]["goal"]["status"] == S.ASSUMED
    assert card["slots"]["goal"]["value"] == E._default_for(card, "goal")
    assert not (r["question"] and r["question"].get("slot") == "goal")


def test_dontknow_closes_followup(monkeypatch):
    fake_setup(monkeypatch, {})
    card = E.new_card("cafe")
    card["pending"] = {"slot": "hours", "kind": "followup", "options": [E.LATER],
                       "text": "몇 시부터 몇 시까지 여나요? 예: 10시~21시"}
    r = E.turn(card, "몰라요")
    assert card["slots"]["hours"]["status"] == S.PLACEHOLDER
    assert not (r["question"] and r["question"].get("slot") == "hours")


def test_dontknow_not_asked_again(monkeypatch):
    fake_setup(monkeypatch, {})
    card = E.new_card("cafe")
    card["pending"] = {"slot": "contact_method", "kind": "single",
                       "options": ["전화", S.LET_AI], "text": "?"}
    r = E.turn(card, "글쎄요")
    assert card["slots"]["contact_method"]["status"] == S.ASSUMED
    seen = [r["question"]["slot"]] if r["question"] else []
    for _ in range(3):
        r = E.turn(card, "모름")
        if r["question"]:
            seen.append(r["question"]["slot"])
    assert "contact_method" not in seen


# ── C: 막연한 말은 칸 값으로 저장하지 않기 ─────────────────────────

def test_vague_offerings_dropped(monkeypatch):
    fake_setup(monkeypatch, {
        "메뉴 많은데 뭘 넣어야 할지": [u("offerings", "많음")],
        "라떼 팔고 종류가 많음": [u("offerings", "라떼, 많음")],
    })
    card = E.new_card("restaurant")
    E.turn(card, "메뉴 많은데 뭘 넣어야 할지")
    assert "많음" not in ((card["slots"].get("offerings") or {}).get("value") or [])
    card2 = E.new_card("restaurant")
    E.turn(card2, "라떼 팔고 종류가 많음")
    assert card2["slots"]["offerings"]["value"] == ["라떼"]


def test_vague_hours_not_stored_and_asks_once(monkeypatch):
    fake_setup(monkeypatch, {"주말에 열어요": [u("hours", "주말")]})
    card = E.new_card("workshop")
    r = E.turn(card, "주말에 열어요")
    assert card["slots"].get("hours", {}).get("status") != S.FILLED
    assert r["question"] and r["question"]["slot"] == "hours"
    assert "몇 시부터" in r["question"]["text"]
    assert card["followup_asked"].count("hours") == 1
    E.turn(card, "주말요")
    assert card["followup_asked"].count("hours") == 1


def test_hours_with_numbers_kept(monkeypatch):
    # 회귀: 숫자 있는 시간은 기존처럼 저장된다
    fake_setup(monkeypatch, {"10시부터 21시까지요": [u("hours", "10시~21시")]})
    card = E.new_card("cafe")
    E.turn(card, "10시부터 21시까지요")
    assert card["slots"]["hours"]["value"] == "10시~21시"
    assert card["slots"]["hours"]["status"] == S.FILLED


def test_numeric_hours_not_overwritten_by_vague(monkeypatch):
    # 숫자 있는 기존 값은 막연한 말로 덮지 않는다
    fake_setup(monkeypatch, {"주말에 열어요": [u("hours", "주말")]})
    card = E.new_card("workshop")
    E._put(card, "hours", "10시~21시", S.FILLED, 0)
    E.turn(card, "주말에 열어요")
    assert card["slots"]["hours"]["value"] == "10시~21시"


# ── D: 직접 답 가드 (길이·막연한 말·잡담·hidden 오염) ───────────────────

def test_empty_extract_does_not_fill_chatter(monkeypatch):
    # 추출이 빈손이면 잡담을 물은 칸으로 넣지 않는다 ("오늘 날씨가 좋네요" → 가게 이름 X).
    # 빈손 반복은 stuck 3회가 자리 표시로 닫는다.
    fake_setup(monkeypatch, {"카페예요": [u("business_type", "카페")]})
    card = E.new_card()
    E.turn(card, "카페예요")
    assert card["pending"]["slot"] == "shop_name"
    r = E.turn(card, "오늘 날씨가 좋네요")
    assert card["slots"].get("shop_name", {}).get("status") != S.FILLED
    assert r["question"]["slot"] == "shop_name"


def test_empty_extract_single_char_not_filled(monkeypatch):
    # 한 글자 추임새("음")는 직접 답으로 받지 않는다.
    fake_setup(monkeypatch, {})
    card = E.new_card("restaurant")
    E._put(card, "business_type", "식당", S.FILLED, 1)
    E._put(card, "shop_name", "시장손맛 분식", S.FILLED, 1)
    card["pending"] = {"slot": "offerings", "kind": "single",
                       "options": ["알아서 해주세요"], "text": "?"}
    card["asked"] = 4
    E.turn(card, "음")
    assert card["slots"].get("offerings", {}).get("status") != S.FILLED


def test_wrong_slot_vague_not_filled(monkeypatch):
    # 추출이 엇나간 경우에도 막연한 말("많음")은 offerings에 넣지 않는다.
    fake_setup(monkeypatch, {"많음": [u("target", "많음")]})
    card = E.new_card("restaurant")
    E._put(card, "business_type", "식당", S.FILLED, 1)
    E._put(card, "shop_name", "시장손맛 분식", S.FILLED, 1)
    card["pending"] = {"slot": "offerings", "kind": "single",
                       "options": ["알아서 해주세요"], "text": "?"}
    card["asked"] = 4
    E.turn(card, "많음")
    assert card["slots"].get("offerings", {}).get("status") != S.FILLED


def test_empty_extract_vague_still_dropped(monkeypatch):
    # 직접 답이라도 막연한 말("많음")은 offerings에 넣지 않는다.
    fake_setup(monkeypatch, {})
    card = E.new_card("restaurant")
    E._put(card, "business_type", "식당", S.FILLED, 1)
    E._put(card, "shop_name", "시장손맛 분식", S.FILLED, 1)
    card["pending"] = {"slot": "offerings", "kind": "single",
                       "options": ["알아서 해주세요"], "text": "?"}
    card["asked"] = 4
    E.turn(card, "많음")
    assert card["slots"].get("offerings", {}).get("status") != S.FILLED


# ── E: hidden 오염 차단 (F4) ──────────────────────────────────────

def test_hidden_answer_does_not_pollute_offerings(monkeypatch):
    # hidden 답("단체 수업")만으로 offerings를 채우지 않는다. hidden 선택은 유지.
    fake_setup(monkeypatch, {"단체 수업도 해요": [u("offerings", "단체 수업")]})
    card = E.new_card("workshop")
    card["said"] = ["성수동 근처에서 손빛 도자기 공방 해요. 원데이 클래스 3만5천원이고 정규반도 있어요."]
    card["turn"] = 2
    card["hidden"] = {"asked": True, "selected": ["group"]}
    applied = E.apply_updates(card, [u("offerings", "단체 수업")], "단체 수업도 해요")
    assert applied == []
    assert card["slots"].get("offerings", {}).get("status") != S.FILLED
    assert card["hidden"]["selected"] == ["group"]


def test_offerings_with_prior_evidence_kept(monkeypatch):
    # 먼저 말한 메뉴(바비큐)는 hidden 라벨과 겹쳐도 유지한다.
    fake_setup(monkeypatch, {})
    card = E.new_card("pension")
    card["said"] = ["펜션 사이트요. 객실이랑 바비큐장 넣고 싶어요."]
    card["turn"] = 2
    card["hidden"] = {"asked": True, "selected": ["bbq"]}
    applied = E.apply_updates(card, [u("offerings", "바비큐")], "바비큐요")
    assert applied == ["offerings"]
    assert card["slots"]["offerings"]["value"] == ["바비큐"]


# ── F: 공유방 비방장 required 확인 확대 (F6) ───────────────────────

def test_nonowner_answer_fills_directly(monkeypatch):
    # D52(전원 동의로 대체): 딸(비방장)의 연락방법·목록 답도 바로 들어가고, 여러 항목이 모두 남는다.
    fake_setup(monkeypatch, {})
    card = E.new_card("cafe")
    card["turn"] = 3
    card["said"] = ["아메리카노, 한라봉차요"]
    E.apply_updates(card, [u("contact_method", "전화"), u("offerings", "아메리카노"), u("offerings", "한라봉차")],
                    "아메리카노, 한라봉차요", by="h-wife", is_owner=False)
    assert card["slots"]["contact_method"]["status"] == S.FILLED
    assert card["slots"]["offerings"]["value"] == ["아메리카노", "한라봉차"]


def test_owner_required_nonfact_fills_directly(monkeypatch):
    # 방장은 그대로 확정된다 (질문 1회 증가 없음).
    fake_setup(monkeypatch, {})
    card = E.new_card("pension")
    card["turn"] = 3
    card["said"] = ["펜션 사이트요"]
    applied = E.apply_updates(
        card, [u("contact_method", "전화")], "전화", by="h-owner", is_owner=True)
    assert applied == ["contact_method"]
    assert card["slots"]["contact_method"]["status"] == S.FILLED


def test_price_followup_uses_industry_example():
    # z2 pension-group: 펜션·학원에 미용실 예시('컷트 2만원')가 나가던 문제.
    for ind, want in (("pension", "객실 요금"), ("academy", "수강료"), ("salon", "컷 2만원 30분")):
        card = E.new_card(ind)
        E._maybe_followup(card, ["offerings"])
        text = card["followup"]["text"]
        assert want in text and "나중에 넣을게요" in text
        assert ind == "salon" or "컷 " not in text
