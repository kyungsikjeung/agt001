"""시안·사이트 문구 초안 (사용자 요청 9/26: "글만 있고 밋밋하다", 방안 3).

사장님이 말한 내용과 업종으로 첫 화면 한 줄·소개 2~3문장·상품 한 줄 설명을 NIM이 쓴다.
사실은 지어내지 않는다(D26): 원문에 없는 숫자(가격·전화·경력 연수·인원)가 들어간 문장은 버린다.
사장님이 소개(detail)를 직접 말했거나 편집에서 고치면 그 글이 우선이다.
"""
import json
import logging
import re
from typing import Optional

from app import llm
from app.services import numbers
from app.services import prd_engine as E

log = logging.getLogger(__name__)

_SYSTEM = (
    "너는 동네 가게·개인 레슨·모임 홈페이지 문구를 쓰는 카피라이터다. 한국어, 따뜻하고 담백한 '~해요' 말투.\n"
    "규칙: 사장님이 말하지 않은 사실(가격, 전화, 주소, 영업시간, 경력 연수, 수상, 인원, 자격증)은 절대 쓰지 않는다. "
    "숫자는 사장님 원문에 있는 것만 쓴다. 과장(최고, 1위, 유일) 금지. 이모지 금지.\n"
    "문장 규칙(Confetti식 디스커버리 원칙):\n"
    "- 첫 화면 한 줄은 손님이 오기 전 고민·상황을 직접 부른다"
    " (예: '처음 만나는 첼로가 평생의 취미가 되도록'). 업종 일반론('맛있는 식당', '친절한 학원') 금지.\n"
    "- 근거 없는 수식(최고·1위·유일·열정·자부심·오랜 전통)은 쓰지 않는다. "
    "대신 카드에 있는 구체 명사(상품·수업 이름, 시간, 장소, 사장님 표현)를 문장에 넣는다.\n"
    "- 소개는 '왜 시작했는지·누구에게 좋은지' 먼저, 이력·수상 나열은 뒤로.\n"
    "출력은 JSON 하나: {\"tagline\": \"첫 화면 한 줄(25자 이내)\", \"intro\": \"소개 2~3문장(120자 이내)\", "
    "\"items\": {\"<상품·수업 이름>\": \"한 줄 설명(30자 이내)\"}}. items는 주어진 이름만 쓴다."
)


def _clean(text: str, allowed_numbers: set, limit: int) -> str:
    """원문에 없는 숫자가 든 문장은 버리고 길이를 자른다."""
    parts = re.split(r"(?<=[.!?。요다])\s+", (text or "").strip())
    kept = [p for p in parts if p and numbers.numbers_in(p) <= allowed_numbers]
    out = " ".join(kept).strip()
    return out[:limit]


def generate(card: dict) -> Optional[dict]:
    """{"tagline", "intro", "items": {name: desc}, "draft": True} 또는 실패하면 None(시안은 그대로 만든다)."""
    ind = E.industry_of(card)
    offerings = [v for v in ((card["slots"].get("offerings") or {}).get("value") or []) if isinstance(v, str)][:8]
    said = " ".join(card.get("said") or [])[:1500]
    # 디스커버리 브리프: 카드 사실 + 분위기(톤) + 덧붙인 말 + 기능 답변. 근거 없는 값은 넣지 않는다.
    concept = card.get("concept") or {}
    mood = ", ".join(concept.get("mood") or [])
    hidden = card.get("hidden") or {}
    note = str(hidden.get("note") or "")[:200]
    answers = " / ".join(f"{k}: {str(v)[:120]}" for k, v in (card.get("feature_answers") or {}).items())[:600]
    brief = [f"[업종] {ind.name}",
             f"[정리된 요구사항]\n{E.summary_text(card)}",
             f"[상품·수업 이름] {', '.join(offerings) or '(없음)'}"]
    if mood:
        brief.append(f"[분위기·말투] {mood} 느낌을 살린다")
    if note:
        brief.append(f"[사장님 덧붙임] {note}")
    if answers:
        brief.append(f"[기능 답변] {answers}")
    brief.append(f"[사장님 원문] {said or '(없음)'}")
    user = "\n".join(brief)
    try:
        raw = llm.chat_json(_SYSTEM, user, timeout_sec=15.0, max_tokens=500)
        data = json.loads(re.search(r"\{.*\}", raw or "", re.S).group(0))
    except Exception:
        log.exception("문구 초안 실패(건너뜀)")
        return None
    allowed = numbers.numbers_in(said + " " + E.summary_text(card))
    items = data.get("items") if isinstance(data.get("items"), dict) else {}
    out = {
        "tagline": _clean(str(data.get("tagline") or ""), allowed, 40),
        "intro": _clean(str(data.get("intro") or ""), allowed, 200),
        "items": {k: _clean(str(v), allowed, 50) for k, v in items.items() if k in offerings and v},
        "draft": True,
    }
    return out if (out["tagline"] or out["intro"]) else None
