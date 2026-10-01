"""말로 한 숫자 → 실제 숫자 (사실 근거 확인용, B-5 보강).

사장님은 "오후 세 시", "열한 시", "3만5천원", "십이만원"처럼 말하는데 AI는 "15:00", "35,000원"으로 적는다.
글자끼리 비교하면 근거가 있는데도 "지어낸 값"으로 버리게 된다(T2 평가: 영업시간 20%).
여기서는 양쪽에서 숫자를 뽑아 값으로 비교한다. 표준 라이브러리만 쓴다(평가 도구도 함께 쓴다).
"""
import re

# 시각 앞의 고유어 수 ("세 시", "열한 시"). 긴 것부터 맞춘다.
_NATIVE_HOURS = {"열한": 11, "열두": 12, "한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7,
                 "여덟": 8, "아홉": 9, "열": 10}
_NATIVE_RE = re.compile(r"(열한|열두|다섯|여섯|일곱|여덟|아홉|한|두|세|네|열)\s*시")

_SINO_DIGIT = {"영": 0, "공": 0, "일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
_SMALL_UNIT = {"십": 10, "백": 100, "천": 1000}
# 숫자·한자어 수·단위가 이어진 덩어리 (예: "3만5천", "십이만", "1,500", "15").
_CHUNK_RE = re.compile(r"[0-9][0-9,]*(?:\.[0-9]+)?(?:\s*[십백천만억]\s*[0-9]*)*|[영공일이삼사오육칠팔구십백천만억]+")


def _parse_chunk(chunk: str):
    """'3만5천' → 35000, '십이만' → 120000, '1,500' → 1500. 숫자가 아니면 None."""
    s = chunk.replace(",", "").replace(" ", "")
    if not s:
        return None
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", s):
        v = float(s)
        return int(v) if v.is_integer() else v
    total, section, num = 0, 0, None
    i = 0
    while i < len(s):
        ch = s[i]
        if ch.isdigit():
            m = re.match(r"[0-9]+", s[i:])
            num = int(m.group(0))
            i += len(m.group(0))
            continue
        if ch in _SINO_DIGIT:
            num = _SINO_DIGIT[ch]
        elif ch in _SMALL_UNIT:
            section += (num if num is not None else 1) * _SMALL_UNIT[ch]
            num = None
        elif ch in ("만", "억"):
            unit = 10_000 if ch == "만" else 100_000_000
            section += num or 0
            total += (section or 1) * unit
            section, num = 0, None
        else:
            return None
        i += 1
    value = total + section + (num or 0)
    return value


# 한자어 수 뒤에 오면 숫자로 보는 단위·세는 말
_COUNTER_RE = re.compile(r"\s*(원|시|분|명|개|층|평|년|월|일|살|곳|박|인분|대|석|회|번째|km|m\b)")


def _sino_is_number(chunk: str, after: str) -> bool:
    """한글로 된 수 덩어리가 문맥상 숫자인지. 글자 목록이 아니라 앞뒤 모양으로 판단한다.

    - 뒤에 단위·세는 말이 오면 숫자 ("삼만오천원", "이십 명", "만 원")
    - 숫자 글자가 둘 이상 이어지면 숫자 ("십이만", "이십")
    - 그 밖은 낱말의 일부 ("만들기", "천연", "천천히", "매일", "구성", "사실")
    한 글자 수("이", "사", "구")는 "이분", "구분", "이곳"처럼 낱말에 흔해서 겹치지 않는 단위 앞에서만 숫자로 본다.
    """
    if len(chunk) == 1 and chunk in _SINO_DIGIT:
        return re.match(r"\s*([시만천원층평]|인분|번째)", after) is not None
    if _COUNTER_RE.match(after):
        return True
    return len(chunk) >= 2 and any(c in _SINO_DIGIT for c in chunk)


def numbers_in(text: str) -> set:
    """글 속의 숫자들. 시각은 고유어도 숫자로 바꾼다('오후 세 시' → {3, 15})."""
    t = text or ""
    found: set = set()
    for m in _NATIVE_RE.finditer(t):
        found.add(_NATIVE_HOURS[m.group(1)])
    t = _NATIVE_RE.sub(" ", t)
    # "공일공"처럼 한 자리씩 읽은 전화번호가 한자어 수로 합쳐지지 않게, 한 글자짜리 수만 이어진 7자 이상은 건너뛴다.
    for m in _CHUNK_RE.finditer(t):
        chunk = m.group(0)
        if re.fullmatch(r"[영공일이삼사오육칠팔구]{2,}", chunk):
            continue  # 한 자리씩 읽은 수(전화번호 등)는 전화 규칙이 맡는다
        if not chunk[0].isdigit() and not _sino_is_number(chunk, t[m.end():]):
            continue
        v = _parse_chunk(chunk)
        if v is not None:
            found.add(v)
    # 오후·밤·저녁 뒤의 1~11시는 24시간제 값도 함께 넣는다(AI가 15:00으로 적는 경우).
    for m in re.finditer(r"(오후|밤|저녁)\s*(\d{1,2}|열한|열두|다섯|여섯|일곱|여덟|아홉|한|두|세|네|열)\s*시", text or ""):
        h = int(m.group(2)) if m.group(2).isdigit() else _NATIVE_HOURS[m.group(2)]
        if 1 <= h <= 11:
            found.add(h + 12)
    return found


def native_hours_to_digits(text: str) -> str:
    """고유어 시각을 숫자 시각으로 ('오후 세 시' → '오후 3시'). '한 시간'처럼 길이를 뜻하는 말은 두고, 나머지 글자는 그대로 둔다."""
    return re.sub(r"(열한|열두|다섯|여섯|일곱|여덟|아홉|한|두|세|네|열)\s*시(?!간)",
                  lambda m: f"{_NATIVE_HOURS[m.group(1)]}시", text or "")


def value_numbers(value: str) -> set:
    """AI가 적은 값의 숫자들. '15:00'의 00, '35,000원'의 쉼표 등은 값 하나로 본다."""
    v = re.sub(r"(\d{1,2}):00\b", r"\1시", value or "")
    v = re.sub(r"(\d{1,2}):(\d{2})\b", r"\1시 \2분", v)
    nums = numbers_in(v)
    return {n for n in nums if n != 0}


def grounded_numbers(value: str, text: str) -> bool:
    """값의 숫자가 모두 원문에 있으면 True. 값에 숫자가 없으면 None 대신 True(숫자 비교 대상 아님)."""
    vn = value_numbers(value)
    if not vn:
        return True
    tn = numbers_in(text)
    # "다섯 시"를 AI가 "17시"로 적는 경우: 13~24는 12를 뺀 값이 원문에 있으면 근거로 본다.
    return all(n in tn or (isinstance(n, int) and 13 <= n <= 24 and n - 12 in tn) for n in vn)
