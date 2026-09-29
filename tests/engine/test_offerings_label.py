"""offerings 라벨 오기입 수정 (G2). DB 없이 돌아간다."""
from app.services import prd_engine as E
from app.services import prd_schema as S


def test_joined_particle_not_stored():
    # 재현: "메뉴와 가격"이 "와 가격"으로 저장되던 문제
    c = E.new_card("restaurant")
    c["turn"] = 3
    applied = E.apply_updates(
        c,
        [{"slot": "offerings", "value": "메뉴와 가격"}],
        "메뉴와 가격, 단체 예약 안내, 주차 정보를 넣고 싶어요.",
    )
    assert "offerings" not in applied
    slot = c["slots"].get("offerings") or {}
    assert slot.get("status") != S.FILLED
    val = slot.get("value") or []
    assert not any("와 가격" in str(v) for v in (val if isinstance(val, list) else [val]))


def test_real_items_with_particle_kept():
    c = E.new_card("restaurant")
    c["turn"] = 3
    applied = E.apply_updates(
        c,
        [{"slot": "offerings", "value": "김치찌개와 제육볶음"}],
        "김치찌개와 제육볶음",
    )
    assert applied == ["offerings"]
    assert c["slots"]["offerings"]["value"] == ["김치찌개", "제육볶음"]


def test_label_word_dropped_but_real_kept():
    c = E.new_card("restaurant")
    c["turn"] = 3
    applied = E.apply_updates(
        c,
        [{"slot": "offerings", "value": "메뉴, 김치찌개"}],
        "메뉴, 김치찌개",
    )
    assert applied == ["offerings"]
    assert c["slots"]["offerings"]["value"] == ["김치찌개"]


def test_strip_label_still_works():
    cafe = E.new_card("cafe")
    ind = E.industry_of(cafe)
    assert S.label_for(ind, "offerings") == "대표 메뉴"
    assert E._strip_label(ind, "offerings", "대표 메뉴 아메리카노") == "아메리카노"
    rest = E.new_card("restaurant")
    rind = E.industry_of(rest)
    assert "메뉴" in S.label_for(rind, "offerings")
    assert E._strip_label(rind, "offerings", "메뉴는 김치찌개") == "김치찌개"
    # 붙임 조사 뒤에는 라벨을 떼지 않는다
    assert E._strip_label(rind, "offerings", "메뉴와 가격") == "메뉴와 가격"


def test_josa_follows_batchim():
    assert E._josa("메뉴", "은는") == "메뉴는"
    assert E._josa("가게 이름", "은는") == "가게 이름은"
    assert E._josa("서울", "으로", quote=True) == "'서울'로"
    assert E._josa("강남", "으로", quote=True) == "'강남'으로"
    assert E._josa("종로구", "으로", quote=True) == "'종로구'로"
    assert E._josa("내맘", "이라고", quote=True) == "'내맘'이라고"
    assert E._josa("010-1234", "으로", quote=True) == "'010-1234'(으)로"
