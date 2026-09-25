"""말로 한 숫자 근거 확인 (T2 평가 1차: 영업시간 20%의 원인)."""
import pytest

from app.services.numbers import grounded_numbers as g
from app.services import prd_engine as E


@pytest.mark.parametrize("value,text", [
    ("3시", "체크인은 세 시부터라예"),
    ("15:00", "체크인은 오후 세 시고"),
    ("11:00", "체크아웃은 오전 열한 시예요"),
    ("35,000원", "원데이클래스 3만5천원이고"),
    ("120,000원", "정규반은 한 달에 십이만원이에요"),
    ("150000원", "1박에 15만원이고요"),
    ("10:00~22:00", "오전 10시부터 밤 10시까지"),
    ("17시", "영업은 다섯 시부터 해요"),
])
def test_spoken_numbers_are_grounded(value, text):
    assert g(value, text)


@pytest.mark.parametrize("value,text", [
    ("2만원", "칼국수 8천원"),
    ("5시", "세 시부터"),
    ("9,000원", "가격은 나중에 알려 드릴게요"),
])
def test_invented_numbers_rejected(value, text):
    assert not g(value, text)


def test_engine_grounded_uses_numbers_but_phone_stays_strict():
    assert E.grounded("hours", "15:00", "오후 세 시부터")
    assert E.grounded("price", "35,000원", "3만5천원이에요")
    assert not E.grounded("phone", "010-1234-5678", "전화는 나중에")
    assert E.grounded("phone", "010-0000-6789", "전화는 공일공에 0000에 6789번")
