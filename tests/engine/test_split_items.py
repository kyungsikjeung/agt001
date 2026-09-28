"""_split_items 조사 나누기 (K6). DB 없이 돌아간다."""
from app.services.prd_engine import _split_items


def test_particles_split():
    assert _split_items("아메리카노와 라떼") == ["아메리카노", "라떼"]
    assert _split_items("김치찌개랑 된장찌개") == ["김치찌개", "된장찌개"]
    assert _split_items("떡볶이랑 순대") == ["떡볶이", "순대"]
    assert _split_items("제육볶음과 계란말이") == ["제육볶음", "계란말이"]
    assert _split_items("비빔밥이랑 국수") == ["비빔밥", "국수"]


def test_no_split_inside_words():
    assert _split_items("고등 수학 과외") == ["고등 수학 과외"]
    assert _split_items("진료 후 알림, 결과 확인") == ["진료 후 알림", "결과 확인"]
    assert _split_items("와플, 사과주스") == ["와플", "사과주스"]
    assert _split_items("사랑방 모임") == ["사랑방 모임"]
    assert _split_items("오이랑 당근") == ["오이", "당근"]
    assert _split_items("커피와케이크") == ["커피와케이크"]


def test_thousands_comma_and_list():
    assert _split_items("아메리카노 4,500원, 라떼 5,000원") == ["아메리카노 4,500원", "라떼 5,000원"]
    assert _split_items(["아메리카노", "라떼"]) == ["아메리카노", "라떼"]


def test_other_delimiters_kept():
    assert _split_items("아메리카노, 라떼") == ["아메리카노", "라떼"]
    assert _split_items("에이드·스무디") == ["에이드", "스무디"]
    assert _split_items("케이크/쿠키") == ["케이크", "쿠키"]
    assert _split_items("커피 그리고 케이크") == ["커피", "케이크"]
