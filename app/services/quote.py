"""견적: 3안(A/B/C) + 추천을 NIM에게 구조화된 JSON으로 생성시킨다.

시안 페이지가 quote.amount/basis를 그대로 노출하므로 자유 텍스트가 아니라 JSON으로 받는다.
NIM 호출 실패는 정적 견적으로, JSON 파싱 실패는 자유 텍스트로 폴백한다.
"""
import copy
import json
import logging
import re

from app import llm

log = logging.getLogger(__name__)

STATIC_QUOTE_FALLBACK = {
    "ok": True,
    "options": [
        {"id": "A", "weeks": 2, "amount": 3500000, "desc": "표준 웹 프로젝트 기본안"},
        {"id": "B", "weeks": 1, "amount": 2000000, "desc": "최소 기능 우선 구현"},
        {"id": "C", "weeks": 3, "amount": 5500000, "desc": "고급 커스터마이징 포함"},
    ],
    "recommended": "B",
    "raw": (
        "⚠ 견적 엔진(NIM) 연결이 원활하지 않아 기본 견적을 보여드립니다. "
        "실제 견적은 담당자가 다시 확인 후 안내드립니다.\n\n"
        "A: 2주, 3,500,000원 – 표준 웹 프로젝트 기본안\n"
        "B: 1주, 2,000,000원 – 최소 기능 우선 구현\n"
        "C: 3주, 5,500,000원 – 고급 커스터마이징 포함\n\n"
        "추천: B"
    ),
}

_PROMPT = (
    "너는 소프트웨어 외주 견적 담당자다. 아래 고객 요청을 보고, "
    "예산/일정이 다른 3가지 안(A/B/C)과 그중 추천안을 JSON으로만 응답해라. "
    "마크다운 코드블록이나 설명 문구 없이 JSON 객체 하나만 출력해라. 형식:\n"
    '{"options": [{"id": "A", "weeks": 2, "amount": 1500000, "desc": "..."}, '
    '{"id": "B", "weeks": 1, "amount": 1000000, "desc": "..."}, '
    '{"id": "C", "weeks": 3, "amount": 2500000, "desc": "..."}], "recommended": "B"}\n\n'
    "고객 요청: {user_text}"
)


def parse_quote(raw: str) -> dict:
    try:
        cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned)
        options = {o["id"]: o for o in data["options"]}
        if data["recommended"] not in options:
            raise ValueError("recommended id not in options")
        return {"ok": True, "options": data["options"], "recommended": data["recommended"], "raw": raw}
    except Exception:
        log.warning("견적 JSON 파싱 실패, 자유 텍스트로 폴백")
        return {"ok": False, "raw": raw}


def build_quote(user_text: str) -> dict:
    try:
        raw = llm.chat([{"role": "user", "content": _PROMPT.replace("{user_text}", user_text)}])
    except Exception:
        log.exception("견적 NIM 호출 실패, 정적 견적으로 폴백")
        return copy.deepcopy(STATIC_QUOTE_FALLBACK)
    return parse_quote(raw)


def format_quote_text(quote: dict) -> str:
    if not quote["ok"]:
        return quote["raw"]
    lines = [f"{o['id']}: {o['weeks']}주, {o['amount']:,}원 – {o['desc']}" for o in quote["options"]]
    lines.append(f"\n추천: {quote['recommended']}")
    return "\n".join(lines)


def recommended_option(quote: dict) -> tuple[int, str]:
    """시안에 노출할 (금액, 근거). 파싱 실패 견적이면 기본값."""
    if quote.get("ok"):
        rec = next(o for o in quote["options"] if o["id"] == quote["recommended"])
        return rec["amount"], rec["desc"]
    return 0, "견적 산정 실패 — 자유 텍스트 견적 참고"
