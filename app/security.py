import re


def sanitize_token(value, max_len: int = 64) -> str:
    """경로 순회(../)와 docker 인자 주입을 막기 위해 영숫자·하이픈·밑줄만 남긴다.

    requirement_id, room_id, member_id에 공통으로 쓴다.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", value or "")
    return cleaned[:max_len]


def sanitize_spec(text, max_len: int = 800) -> str:
    """프롬프트 인젝션 표면을 줄이기 위해 제어문자를 제거하고 길이를 제한한다. 완벽한 방어는 아니다."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text or "")
    return text.strip()[:max_len]
