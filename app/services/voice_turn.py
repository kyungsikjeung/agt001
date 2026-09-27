"""화면 글 → 소리로 읽을 글 (VOICE_QA_REQUIREMENTS FR-1).

답장은 화면에 맞춰 쓰여 있어 그대로 읽으면 "(질문 3/8 · '시안 먼저'라고…)" 같은 안내와
기호(·, →, 1))까지 소리가 된다. 여기서 읽을 말만 남긴다. 화면 글은 바꾸지 않는다.
"""
import re

# 줄 전체가 괄호로 싸인 안내("(질문 3/8 · …)", "(승인 전에 확인할 게 남았어요)")는 읽지 않는다
_PAREN_LINE = re.compile(r"^\s*\(.*\)\s*$")
# 선택지 "1) 예약 문의 늘리기  2) 가게 알리기"
_OPTION = re.compile(r"(?:(?<=\s)|^)([1-9])\)\s*")
_URL = re.compile(r"https?://\S+")
# 한글·영숫자·기본 문장부호·물결(10~21시)·쉼표 말고는 소리 내지 않는다 (이모지·장식 기호)
_NOISE = re.compile(r"[^\w\s가-힣.,?!~%:/\-]")


def speech_text(text: str) -> str:
    """읽을 글. 비면 빈 문자열."""
    lines = []
    for line in (text or "").splitlines():
        if not line.strip() or _PAREN_LINE.match(line):
            continue
        s = _URL.sub("링크", line)
        s = re.sub(r"^\s*[•\-*]\s*", "", s)                # 글머리 기호
        s = s.replace("→", ", ").replace(" · ", ", ").replace("·", ", ")
        s = re.sub(r"['\"‘’“”「」\[\]]", "", s)            # 따옴표·대괄호는 떼고 안의 말은 둔다
        s = _OPTION.sub(lambda m: f"{m.group(1)}번, ", s)
        s = re.sub(r"\s{2,}(?=\d번, )", ". ", s)           # 선택지 사이 두 칸 → 문장 끊기
        s = _NOISE.sub(" ", s)
        s = re.sub(r"\s+", " ", s).strip(" ,")
        if s:
            lines.append(s if s[-1] in ".?!~" else s + ".")
    return " ".join(lines)
