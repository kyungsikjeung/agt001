"""잘못된 입력 검사 (validate) 표 형태 시험.

과제3 예시(010-123-45, 25시, 마감<개장, -5천원, 900101-1234567 등)를
반드시 포함한다. DB 없이 돌아간다.
"""
import pytest

from app.services.validate import (
    check_hours,
    check_phone,
    check_price,
    contains_sensitive,
)


# 전화: 정상 7개
PHONE_OK = [
    "010-1234-5678",
    "01012345678",
    "02-123-4567",
    "02-1234-5678",
    "031-456-7890",
    "070-1234-5678",
    "1588-1234",
]

# 전화: 걸러야 할 것 7개 (과제3 예시 010-123-45, 900101-1234567 포함)
PHONE_BAD = [
    ("010-123-45", "전화번호 자리수가 맞지 않아요"),
    ("900101-1234567", "주민등록번호는 받지 않아요"),
    ("010-12-3456", "전화번호 자리수가 맞지 않아요"),
    ("02-12-345", "전화번호 자리수가 맞지 않아요"),
    ("1588-123", "전화번호 자리수가 맞지 않아요"),
    ("010-1234-56789", "전화번호 자리수가 맞지 않아요"),
    ("전화번호는 비밀이에요", "전화번호 자리수가 맞지 않아요"),
]


@pytest.mark.parametrize("value", PHONE_OK)
def test_phone_ok(value):
    assert check_phone(value) is None


@pytest.mark.parametrize("value,reason", PHONE_BAD)
def test_phone_bad(value, reason):
    assert check_phone(value) == reason


# 영업시간: 정상 6개 (자정 넘김·체크인 순서 통과 포함)
HOURS_OK = [
    "매일 10시부터 20시까지",
    "월~토 11시부터 21시까지",
    "매일 09~22시",
    "저녁 6시부터 새벽 2시까지",
    "체크인 15시 체크아웃 11시",
    "오후 2시부터 7시까지",
    # 말로 한 시각 (T2 재생: 숫자 모양만 읽어서 "영업시간 숫자가 없어요"로 막던 것)
    "오전 열 시부터 저녁 여덟 시까지",
    "체크인은 세 시부터",
    "수요일 토요일 두 시부터",
]

# 영업시간: 걸러야 할 것 6개 (과제3 예시 25시, 마감<개장 포함)
HOURS_BAD = [
    ("25시까지 해요", "24시가 넘는 시간은 없어요"),
    ("마감 9시 개장 11시", "마감이 개장보다 일러요"),
    ("개장 11시 마감 9시", "마감이 개장보다 일러요"),
    ("10시부터 8시까지", "마감이 개장보다 일러요"),
    ("주말", "영업시간 숫자가 없어요"),
    ("29시 오픈", "24시가 넘는 시간은 없어요"),
    ("한 시간 수업", "영업시간 숫자가 없어요"),
]


@pytest.mark.parametrize("value", HOURS_OK)
def test_hours_ok(value):
    assert check_hours(value) is None


@pytest.mark.parametrize("value,reason", HOURS_BAD)
def test_hours_bad(value, reason):
    assert check_hours(value) == reason


# 가격: 정상 6개
PRICE_OK = [
    "아메리카노 5천원",
    "라떼 6,000원",
    "식사 12000원",
    "원데이 클래스 3만5천원",
    "입장료 1만원",
    "주차 1시간에 5천원",
]

# 가격: 걸러야 할 것 7개 (과제3 예시 -5천원, 5천 포함)
PRICE_BAD = [
    ("-5천원", "음수 가격은 안 돼요"),
    ("-3000원", "음수 가격은 안 돼요"),
    ("0원", "0원으로는 저장할 수 없어요"),
    ("5000", "가격 단위가 없어요"),
    ("아메리카노 5000", "가격 단위가 없어요"),
    ("3억원", "가격이 너무 커요"),
    ("1억원", "가격이 너무 커요"),
]


@pytest.mark.parametrize("value", PRICE_OK)
def test_price_ok(value):
    assert check_price(value) is None


@pytest.mark.parametrize("value,reason", PRICE_BAD)
def test_price_bad(value, reason):
    assert check_price(value) == reason


# 민감 정보: 정상(저장해도 됨) 5개
SENSITIVE_OK = [
    "전화는 010-1234-5678이에요",
    "영업은 10시부터 20시까지예요",
    "라떼 5천원이에요",
    "주차 가능해요",
    "서울 마포구에 있어요",
]

# 민감 정보: 걸러야 할 것 6개 (과제3 예시 900101-1234567 포함)
SENSITIVE_BAD = [
    ("주민번호 900101-1234567", "주민등록번호"),
    ("카드번호 4111-1111-1111-1111", "카드번호"),
    ("카드 4539578763621486", "카드번호"),
    ("카드 6011000990139424", "카드번호"),
    ("계좌 123-456-789012로 보내주세요", "계좌번호"),
    ("국민은행 123456-78-901234", "계좌번호"),
]


@pytest.mark.parametrize("text", SENSITIVE_OK)
def test_sensitive_ok(text):
    assert contains_sensitive(text) is None


@pytest.mark.parametrize("text,kind", SENSITIVE_BAD)
def test_sensitive_bad(text, kind):
    assert contains_sensitive(text) == kind


def test_wonrae_blocks_only_when_it_contradicts_saved_hours():
    """"원래"만 들어가도 영업시간을 막던 문제(9/27 검토): 저장된 시간과 숫자가 다를 때만 확인을 요청한다."""
    from app.services import prd_engine as E
    from app.services import prd_schema as S
    card = E.new_card("cafe")
    assert E._w1_block_reason("hours", "원래 10시에 열어요", card) is None      # 저장된 시간 없음
    E._put(card, "hours", "10~21시", S.FILLED)
    assert E._w1_block_reason("hours", "원래 10시~21시예요", card) is None      # 같은 시간
    assert E._w1_block_reason("hours", "원래 11시~21시였어요", card)             # 다른 시간 → 확인
