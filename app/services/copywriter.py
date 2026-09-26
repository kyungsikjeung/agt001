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
    user = (f"[업종] {ind.name}\n[정리된 요구사항]\n{E.summary_text(card)}\n"
            f"[상품·수업 이름] {', '.join(offerings) or '(없음)'}\n[사장님 원문] {said or '(없음)'}")
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
