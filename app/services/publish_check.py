"""게시 전 검사 (DESIGN_PIPELINE_PLAN.md §13.5 S-5).

공개 사이트에 올리기 직전의 HTML을 보고, 아래가 하나라도 있으면 게시를 막는다.
정해진 부품으로만 그리는 우리 렌더러 결과물은 이 검사를 항상 통과한다
(외부 스크립트·외부 폼 없음, 문의 폼은 상대 주소, 자동 이동 없음, 비밀값 없음,
내부 iframe 없음).
"""
import re

_EXTERNAL_SCRIPT = re.compile(r"<script[^>]*\bsrc\s*=\s*[\"']https?://", re.I)
_EXTERNAL_FORM = re.compile(r"<form[^>]*\baction\s*=\s*[\"']https?://", re.I)
_META_REFRESH = re.compile(r"<meta[^>]*\bhttp-equiv\s*=\s*[\"']?refresh", re.I)
_LOCATION_OUT = re.compile(
    r"(?:window\.)?location(?:\.href)?\s*=\s*[\"']https?://"
    r"|location\.(?:replace|assign)\s*\(\s*[\"']https?://", re.I)
_SECRET = re.compile(
    r"sk-[A-Za-z0-9_-]{8,}"
    r"|xox[bpas]-[A-Za-z0-9-]{8,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|(?i:(?:api[_-]?key|api[_-]?secret|secret[_-]?key|access[_-]?token))\s*[:=]\s*[\"'][^\"']{6,}[\"']")
# S-6: CSP sandbox 우회. 공개본은 내부 iframe을 쓰지 않으므로, sandbox 없는
# iframe이나 격리를 푸는 토큰(미리보기 검사 S-2와 같은 금지 목록)이 있으면 막는다.
_IFRAME_TAG = re.compile(r"<iframe\b[^>]*>", re.I)
_IFRAME_SANDBOX = re.compile(r"\bsandbox(?:\s*=\s*\"([^\"]*)\")?", re.I)
_SANDBOX_FORBIDDEN = ("allow-same-origin", "allow-forms", "allow-top-navigation")


class PublishBlockedError(ValueError):
    """게시 전 검사에 걸린 공개 시도. reasons에 사람 말 설명 목록."""

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def check_html(html_text: str) -> list[str]:
    """위반 사유 목록. 비어 있으면 게시해도 된다."""
    text = html_text or ""
    reasons = []
    if _EXTERNAL_SCRIPT.search(text):
        reasons.append("외부 스크립트가 들어 있어요")
    if _EXTERNAL_FORM.search(text):
        reasons.append("외부로 보내는 문의 양식이 들어 있어요")
    if _META_REFRESH.search(text) or _LOCATION_OUT.search(text):
        reasons.append("다른 곳으로 자동 이동하는 코드가 들어 있어요")
    if _SECRET.search(text):
        reasons.append("열쇠처럼 보이는 값이 들어 있어요")
    for tag in _IFRAME_TAG.findall(text):
        m = _IFRAME_SANDBOX.search(tag)
        tokens = m.group(1) or "" if m else None
        if tokens is None or any(t in tokens for t in _SANDBOX_FORBIDDEN):
            reasons.append("격리를 풀 수 있는 화면이 들어 있어요")
            break
    return reasons


def assert_publishable(html_text: str) -> None:
    """위반이 있으면 PublishBlockedError. design.publish_choice가 부른다."""
    reasons = check_html(html_text)
    if reasons:
        raise PublishBlockedError(reasons)
