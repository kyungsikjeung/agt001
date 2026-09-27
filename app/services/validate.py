"""저장 전 잘못된 입력 검사 (규칙만, LLM 없음).

엔진이 칸 값을 카드에 적기 전에 부르는 순수 함수들이다.
각 함수는 정상이면 None, 문제면 짧은 한국어 사유 문자열을 돌려준다.
모든 날짜·시각 판단은 한국 시간 기준으로 읽는다.
표준 라이브러리만 쓴다.
"""
import re
from typing import Optional

from app.services.numbers import numbers_in

# 전화번호 자리수가 맞지 않을 때 돌려주는 말
_PHONE_LEN_MSG = "전화번호 자리수가 맞지 않아요"
# 주민등록번호 모양이 들어왔을 때 돌려주는 말
_RRN_MSG = "주민등록번호는 받지 않아요"

# 주민등록번호 모양: 6자리-7자리, 뒤 첫 자리는 1~4
_RRN_HYPHEN_RE = re.compile(r"(?<!\d)\d{6}\s*-\s*[1-4]\d{6}(?!\d)")
# 하이픈 없는 13자리 주민등록번호 모양 (앞 6자리는 생년월일 자리)
_RRN_PLAIN_RE = re.compile(
    r"(?<!\d)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[1-4]\d{6}(?!\d)"
)

# 휴대폰 앞자리
_MOBILE = ("010", "011", "016", "017", "018", "019")
# 지역번호 앞자리 (서울 02 + 경기·충청·전라·경상·강원·제주 031~064)
_AREA = (
    "02", "031", "032", "033", "041", "042", "043", "044",
    "051", "052", "053", "054", "055", "061", "062", "063", "064",
)
# 인터넷·대표번호 앞자리 모양
_INTERNET_RE = re.compile(r"^050\d")
# 1588류 대표번호 모양 (15·16·18로 시작하는 8자리)
_REP_RE = re.compile(r"^1[568]\d\d\d{4}$")


def _only_digits(value: str) -> str:
    """글 속 숫자만 뽑는다."""
    return re.sub(r"\D", "", value or "")


def check_phone(value: str) -> Optional[str]:
    """전화번호 칸 값을 검사한다. 정상이면 None, 문제면 짧은 한국어 사유.

    - 주민등록번호 모양(6자리-7자리, 뒤 첫 자리 1~4)은 따로 막는다.
    - 휴대폰 010 등은 10~11자리, 지역번호 02·031~064는 9~11자리,
      070·050으로 시작하는 번호는 10~11자리, 1588류 대표번호는 8자리여야 한다.
    """
    text = value or ""
    # 주민등록번호 모양이면 전화 규칙보다 먼저 막는다
    if _RRN_HYPHEN_RE.search(text) or _RRN_PLAIN_RE.search(text):
        return _RRN_MSG
    digits = _only_digits(text)
    if not digits:
        return _PHONE_LEN_MSG
    if _REP_RE.match(digits):
        return None
    if digits.startswith("070") or _INTERNET_RE.match(digits):
        return None if 10 <= len(digits) <= 11 else _PHONE_LEN_MSG
    for head in _MOBILE:
        if digits.startswith(head):
            return None if 10 <= len(digits) <= 11 else _PHONE_LEN_MSG
    for head in _AREA:
        if digits.startswith(head):
            # 02는 짧은 자리(9~10자리)도 쓰고 031~064는 10~11자리가 흔해서 9~11자리로 본다
            return None if 9 <= len(digits) <= 11 else _PHONE_LEN_MSG
    return _PHONE_LEN_MSG


# 시간 범위를 읽는 모양 (예: "9~18시", "10시-20시")
_RANGE_RE = re.compile(r"(\d{1,2})\s*[~\-–—]\s*(\d{1,2})\s*시?")
# 낱개 시각 모양 (예: "10시", "15:30")
_HOUR_RE = re.compile(r"(\d{1,2})\s*시")
_CLOCK_RE = re.compile(r"(\d{1,2})\s*:\s*(\d{2})")
# 자정 넘김을 뜻하는 말 (이 말이 있으면 마감 이른 시각을 다음 날 새벽으로 본다)
_MIDNIGHT_RE = re.compile(r"새벽|다음\s*날|다음날|익일|자정|심야|밤\s*늦게")
# 순서를 따지지 않는 말 (체크인보다 체크아웃이 이른 게 정상이다)
_NO_ORDER_RE = re.compile(r"체크인|체크아웃|입실|퇴실")
# 개장·마감을 가리키는 말
_OPEN_WORD_RE = re.compile(r"개장|개점|오픈|시작|부터|열고|여는")
_CLOSE_WORD_RE = re.compile(r"마감|종료|까지|닫|문\s*닫")


# 앞 시간대 말 (오후면 뒤 시각까지 24시간제로 푼다)
_AMPM_RE = re.compile(r"오전|아침|새벽|오후|밤|저녁")


def _hour_with_ampm(hour: int, before: str) -> int:
    """가장 가까운 앞 시간대 말을 따라 24시간제로 바꾼다 (한국 시간 기준)."""
    marks = _AMPM_RE.findall(before)
    if marks and marks[-1] in ("오후", "밤", "저녁") and 1 <= hour <= 11:
        return hour + 12
    return hour


def _hours_in_order(text: str) -> list:
    """글에 나온 시각들을 나온 순서대로 뽑는다."""
    found: list = []
    spans: list = []
    for match in _RANGE_RE.finditer(text):
        for group in (match.group(1), match.group(2)):
            found.append((_hour_with_ampm(int(group), text[: match.start()]), match.start()))
        spans.append(match.span())
    for pattern in (_HOUR_RE, _CLOCK_RE):
        for match in pattern.finditer(text):
            start = match.start()
            # 범위에서 이미 센 자리는 겹쳐 세지 않는다
            if any(begin <= start < end for begin, end in spans):
                continue
            found.append((_hour_with_ampm(int(match.group(1)), text[:start]), start))
    found.sort(key=lambda item: item[1])
    return [hour for hour, _ in found]


def check_hours(value: str) -> Optional[str]:
    """영업시간 칸 값을 검사한다. 정상이면 None, 문제면 짧은 한국어 사유.

    - numbers_in으로 시각을 읽는다 (말로 한 시각도 숫자로 맞춘다).
    - 24를 넘는 시각(25시)은 막는다.
    - 마감이 개장보다 이르면 막는다. 다만 새벽까지 여는 자정 넘김은
      통과시키고 엔진 쪽에서 다음 날 새벽 마감 표시를 붙인다.
    - 체크인·체크아웃처럼 순서가 반대인 게 정상인 말은 통과시킨다.
    - 시간 숫자가 없으면 막는다.
    """
    text = value or ""
    nums = numbers_in(text)  # 말로 한 시각 근거 확인용
    hours = _hours_in_order(text)
    if not hours and not nums:
        return "영업시간 숫자가 없어요"
    if not hours:
        return "영업시간 숫자가 없어요"
    for hour in hours:
        if hour > 24:
            return "24시가 넘는 시간은 없어요"
    if len(hours) >= 2 and not _NO_ORDER_RE.search(text):
        first, last = hours[0], hours[-1]
        close_first = False
        open_match = _OPEN_WORD_RE.search(text)
        close_match = _CLOSE_WORD_RE.search(text)
        # 마감 말이 개장 말보다 먼저 나오면 앞 시각이 마감이다
        if open_match and close_match:
            close_first = close_match.start() < open_match.start()
        elif close_match and not open_match:
            close_first = True
        opened, closed = (last, first) if close_first else (first, last)
        if closed < opened:
            # 새벽 2시 같은 자정 넘김은 허용하고 다음 날 새벽 표시로 넘긴다
            if _MIDNIGHT_RE.search(text) and closed <= 7:
                return None
            return "마감이 개장보다 일러요"
    return None


# 가격 단위 모양 (원 계열)
_PRICE_UNIT_RE = re.compile(r"원|달러|usd|krw|\$|￦|₩", re.IGNORECASE)
# 음수 모양
_NEG_RE = re.compile(r"-\s*\d|−|마이너스|마이나스")
# 비정상으로 보는 하한 (1억 이상)
_BIG_PRICE = 100_000_000


def check_price(value: str) -> Optional[str]:
    """가격 칸 값을 검사한다. 정상이면 None, 문제면 짧은 한국어 사유.

    - numbers_in으로 값을 읽는다 (말로 한 금액도 숫자로 맞춘다).
    - 음수·0원·숫자 없음(예: '주차돼요')·단위 없는 숫자만(5천)·1억 이상 큰 값을 막는다.
    """
    text = value or ""
    if _NEG_RE.search(text):
        return "음수 가격은 안 돼요"
    nums = numbers_in(text)  # 말로 한 금액 근거 확인용
    if not nums:
        return "가격 숫자가 없어요"
    for num in nums:
        if num == 0:
            return "0원으로는 저장할 수 없어요"
    for num in nums:
        if num >= _BIG_PRICE:
            return "가격이 너무 커요"
    if not _PRICE_UNIT_RE.search(text):
        return "가격 단위가 없어요"
    return None


def _luhn_ok(digits: str) -> bool:
    """카드번호 끝자리 검사 (루흐 검사)."""
    total = 0
    for pos, ch in enumerate(reversed(digits)):
        num = ord(ch) - ord("0")
        if pos % 2 == 1:
            num *= 2
            if num > 9:
                num -= 9
        total += num
    return total % 10 == 0


# 카드 후보 모양 (13~16자리 이어진 숫자, 띄어쓰기·하이픈 허용)
_CARD_RE = re.compile(r"\d(?:[\s-]?\d){12,15}")
# 계좌 3묶음 모양 (예: 123-456-789012)
_ACCOUNT_RE = re.compile(r"(?<!\d)(\d{2,6})-(\d{2,6})-(\d{4,8})(?!\d)")
# 계좌를 뜻하는 말
_ACCOUNT_WORD_RE = re.compile(r"계좌|입금|송금|이체")
# 전화 앞자리 모양 (계좌 3묶음에서 빼준다)
_PHONE_HEAD_RE = re.compile(r"^(010|011|016|017|018|019|02|070|050\d|031|032|033|041|042|043|044|051|052|053|054|055|061|062|063|064)")


def contains_sensitive(text: str) -> Optional[str]:
    """민감 정보가 있으면 종류 이름, 없으면 None (저장 금지 판단용).

    - 주민등록번호 모양(6자리-7자리, 뒤 첫 자리 1~4)
    - 카드번호 모양(13~16자리 이어진 숫자 + 루흐 검사)
    - 계좌 모양(계좌 말 옆 숫자 뭉치 또는 3묶음 숫자)
    """
    said = text or ""
    if _RRN_HYPHEN_RE.search(said) or _RRN_PLAIN_RE.search(said):
        return "주민등록번호"
    for match in _CARD_RE.finditer(said):
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 16 and _luhn_ok(digits):
            return "카드번호"
    if _ACCOUNT_WORD_RE.search(said):
        digits = _only_digits(said)
        if len(digits) >= 8:
            return "계좌번호"
    for match in _ACCOUNT_RE.finditer(said):
        head = match.group(0)
        # 전화번호 3묶음(010-1234-5678 등)은 계좌가 아니다
        if _PHONE_HEAD_RE.match(head.replace(" ", "")):
            continue
        return "계좌번호"
    return None
