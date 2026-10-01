"""T2 추출 보충 규칙 (backfill_from_text). AI가 놓친 칸을 사장님 말 조각으로만 더하는지 본다. DB 없이 돌아간다."""

import pytest

from app.services import prd_engine as E
from evals.run_extraction import load_cases


def _card(text, ups):
    card = E.new_card()
    E.apply_updates(card, E.backfill_from_text(text, ups), text)
    return {k: v["value"] for k, v in card["slots"].items() if v.get("value")}


def u(slot, value):
    return {"slot": slot, "value": value}


def test_long_first_message_location_and_name():
    text = "대치동에서 수학 학원 넘버원 해요. 중등부랑 고등부 있고 수강료는 달에 20만원이에요."
    got = _card(text, [u("business_type", "수학 학원")])
    assert got["location"] == "대치동"
    assert got["shop_name"] == "넘버원"


def test_menu_price_pairs_and_target():
    text = "부산 해운대구 우동에서 할매손 칼국수 해요. 칼국수 8천원, 수육 2만원이고 점심에 직장인들이 많이 와요."
    got = _card(text, [u("shop_name", "할매손 칼국수"), u("price", "수육 2만원")])
    assert got["offerings"] == ["칼국수", "수육"]
    assert "8천원" in got["price"] and "2만원" in got["price"]
    assert got["target"] == "직장인"
    assert got["location"] == "부산 해운대구 우동"


def test_target_list_merges_with_ai_value():
    text = "음, 그냥 동네 카페예요. 이름은 뭐 있어요, 작은숲이라고. 오는 손님은 동네 주민들이랑 학생들이에요."
    got = _card(text, [u("business_type", "카페"), u("target", "학생")])
    assert got["target"] == "학생, 동네 주민"
    assert got["shop_name"] == "작은숲"


def test_offerings_from_boast_and_main_items():
    assert _card("그냥 동네 미용실이에요. 파마 잘해요, 특히 중년 아주머니들이 많이 오셔요", [])["offerings"] == ["파마"]
    got = _card("염색이랑 클리닉이 주력이고, 가게 이름은 컬러랩, 위치는 홍대예요", [])
    assert got == {"offerings": ["염색", "클리닉"], "shop_name": "컬러랩", "location": "홍대"}


def test_closed_day_joins_ai_hours():
    text = "매주 월요일 쉬고, 오전 열 시부터 저녁 여덟 시까지 해요"
    got = _card(text, [u("hours", "오전 열 시부터 저녁 여덟 시까지")])
    assert got["hours"].startswith("월요일 휴무")
    # 숫자 없는 휴무일만으로는 영업시간을 만들지 않는다
    assert "hours" not in _card(text, [])


def test_lead_word_business_and_subject_academy():
    assert _card("커피요. 아메리카노 5천원, 라떼 6천원", [])["business_type"] == "커피"
    assert _card("학원 사이트요. 초등 영어. 상담은 카톡으로", [u("business_type", "영어 학원")])["offerings"] == ["영어"]


def test_ai_values_are_kept():
    text = "강남에서 미용실 빛나헤어 해요."
    ups = [u("location", "서울 강남"), u("shop_name", "빛나헤어")]
    assert E.backfill_from_text(text, ups) == ups


@pytest.mark.parametrize("text", [
    "카톡에서 상담해요",
    "집에서 공방 해요",
    "주차 공간이 많아요",
    "알아서 해주세요",
    "나중에 넣을게요",
])
def test_no_backfill_from_non_patterns(text):
    got = E.backfill_from_text(text, [])
    assert not [x for x in got if x["slot"] in ("location", "target", "shop_name", "phone", "hours", "price")]


def test_eval_cases_backfill_never_breaks_must_not():
    """평가 60개에서 보충만으로 must_not·빈 기대를 어기지 않는다 (지어낸 값 0건 유지)."""
    for c in load_cases():
        got = _card(c["text"], [])
        assert not [s for s in c["must_not"] if s in got], c["id"]
        if not c["expect"]:
            assert not got, c["id"]
