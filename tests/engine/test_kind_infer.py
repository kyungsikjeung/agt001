"""처음 보는 종류 추론 (KIND_INFER_CONTRACT 받아들이는 조건 ①~④).

추출과 추론이 같은 llm.chat_json을 쓰므로, 가짜 하나로 둘 다 나눠 맡는다.
추출 호출은 "[사장님 메시지]"를 담고, 추론 호출은 "만들 사이트:"로 시작한다.
"""
import json

import pytest

from app import llm
from app.services import prd_engine as E
from app.services import prd_schema as S


class _Boom(Exception):
    pass


@pytest.fixture
def fake_llm(monkeypatch):
    state = {"extract": {}, "infer": None, "infer_calls": 0, "infer_user": None}

    def fake(system, user, **kw):
        if user.startswith("만들 사이트:"):
            state["infer_calls"] += 1
            state["infer_user"] = user
            res = state["infer"]
            if isinstance(res, Exception):
                raise res
            return res
        text = user.split("[사장님 메시지] ", 1)[-1]
        return json.dumps({"updates": state["extract"].get(text, [])}, ensure_ascii=False)

    monkeypatch.setattr(llm, "chat_json", fake)
    return state


def u(slot, value):
    return {"slot": slot, "value": value}


MSG = "회계사무소 사이트요"


def _first_turn(state, infer_res):
    state["extract"][MSG] = [u("business_type", "회계사무소")]
    state["infer"] = infer_res
    card = E.new_card()
    return card, E.turn(card, MSG)


def test_inferred_group_fills_sections(fake_llm):
    """① group 추론이면 4지선다 없이 업종이 바뀌고 needs가 담을 내용이 된다."""
    card, r = _first_turn(fake_llm, json.dumps({"kind": "group", "needs": ["모임 일정", "회원 소개"]},
                                               ensure_ascii=False))
    assert r["question"]["kind"] == "single"
    assert card["industry"] == "group"
    assert card["slots"]["sections"]["value"] == ["모임 일정", "회원 소개"]
    assert card["slots"]["sections"]["status"] == S.ASSUMED
    # 추론에는 업종 칸 값만 보낸다
    assert fake_llm["infer_user"] == "만들 사이트: 회계사무소"


def test_inferred_shop_stays_other_without_site_kind(fake_llm):
    """② shop 추론이면 가게이므로 기타에 두고 4지선다를 묻지 않는다."""
    card, r = _first_turn(fake_llm, json.dumps({"kind": "shop"}, ensure_ascii=False))
    assert card["industry"] == "other"
    assert card["kind_asked"] is True
    assert r["question"]["kind"] != "site_kind"


@pytest.mark.parametrize("bad", [
    json.dumps({"kind": "alien", "needs": []}, ensure_ascii=False),
    "깨진 JSON {{{",
    _Boom("터짐"),
])
def test_infer_failure_falls_back_to_site_kind_once(fake_llm, bad):
    """③ 허용 밖 kind·깨진 JSON·예외면 4지선다로 되돌아가고 다시 추론하지 않는다."""
    card, r = _first_turn(fake_llm, bad)
    assert r["question"]["kind"] == "site_kind"
    assert r["question"]["options"] == list(S.KIND_OPTIONS)
    assert E.next_question(card)["kind"] == "site_kind"
    assert fake_llm["infer_calls"] == 1


def test_needs_validation(fake_llm):
    """④ needs 검증: 13자 이상·영문 낱말·중복·숫자 아닌 값은 버리고 최대 6개."""
    from app.services import kind_infer
    fake_llm["infer"] = json.dumps({"kind": "event", "needs": [
        "날짜와 장소", "0123456789013자긴이름", "meeting 안내", "날짜와 장소", 123,
        "오시는 길", "사진", "연락하기", "마음 전하실 곳", "인사말", "식사 안내",
    ]}, ensure_ascii=False)
    res = kind_infer.infer("돌잔치")
    assert res["kind"] == "event" and res["industry"] == "event"
    assert res["needs"] == ["날짜와 장소", "오시는 길", "사진", "연락하기", "마음 전하실 곳", "인사말"]
