"""전화번호 저장 형식 (10/4): 빌더에서 01096567830처럼 숫자만 넣어도 010-9656-7830으로 저장한다.

카드 phone 칸은 공개 사이트에 그대로 보이는 글이라, 저장 형식 = 사람이 읽는 표준 표기(하이픈)로 맞춘다.
전화 걸기 링크(tel:)는 렌더러가 숫자만 따로 뽑는다(site_render._digits). 프런트 입력 칸의 자동 하이픈
(frontend/src/editor/phone.ts)과 같은 규칙이다.
"""
import re
from typing import Optional


def _split(digits: str) -> list[str]:
    n = len(digits)
    if digits.startswith("02"):                       # 서울: 02-123-4567 / 02-1234-5678
        return [digits[:2], digits[2:n - 4], digits[n - 4:]]
    if n == 8:                                        # 대표번호: 1588-1234
        return [digits[:4], digits[4:]]
    if n == 12:                                       # 안심번호: 0507-1234-5678
        return [digits[:4], digits[4:8], digits[8:]]
    return [digits[:3], digits[3:n - 4], digits[n - 4:]]   # 010-1234-5678, 031-123-4567


def format_phone(raw: Optional[str]) -> Optional[str]:
    """전화번호로 읽히면 하이픈 표준 표기, 아니면 None(글은 손대지 않게 부른 쪽이 원문을 쓴다).

    숫자·공백·하이픈·괄호·점·+만 있을 때만 번호로 본다("카톡으로 문의"처럼 글이 섞이면 None).
    +82 / 82로 시작하면 0으로 바꾼다.
    """
    text = (raw or "").strip()
    if not text or not re.fullmatch(r"[\d\s\-().+]+", text):
        return None
    digits = re.sub(r"\D", "", text)
    if digits.startswith("82") and len(digits) in (11, 12):
        digits = "0" + digits[2:]
    if re.fullmatch(r"1[568]\d{6}", digits):
        return "-".join(_split(digits))
    if digits.startswith("02") and len(digits) in (9, 10):
        return "-".join(_split(digits))
    if re.fullmatch(r"050\d{9}", digits) or re.fullmatch(r"0[1-9]\d{8,9}", digits):
        return "-".join(_split(digits))
    return None
