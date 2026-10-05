"""상황 탐색 (BUILD_W1_W2 §1.6, D53 ③).

질문 한도 밖의 시안용 질문이다. 무엇을 물을지는 LLM이 고르고 엔진이 검증한다.
LLM이 실패하면 원형별 기본값으로 돌아간다.
"""
import json
import logging
import re

from app import llm
from app.services import prd_schema as S

log = logging.getLogger(__name__)

# 원형별 허용 칸: LLM은 이 안에서만 고른다
ALLOWED: dict[str, tuple[str, ...]] = {
    "A": ("order_mode", "menu_categories"),
    "B": ("team_mode",),
}
# LLM 실패 시 기본값 (허용 목록과 같은 값)
DEFAULT: dict[str, tuple[str, ...]] = {
    "A": ("order_mode", "menu_categories"),
    "B": ("team_mode",),
}

# 칸별 질문 문장·선택지 (기본 선택지는 3개 이하, "알아서 해주세요"는 물을 때 붙인다)
QUESTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "team_mode": ("매장을 혼자 운영하시나요, 함께 운영하시나요?",
                  ("혼자", "2~3명", "4명 이상")),
    "order_mode": ("손님 주문은 어떻게 받으시나요?",
                   ("매장 방문", "주문 앱 링크", "픽업 주문")),
    # 선택지 하나가 분류 묶음 전체다(하나만 고르면 모든 메뉴가 그 분류로 몰리지 않게). "·"로 나뉘어 저장된다.
    "menu_categories": ("메뉴판에 분류를 어떻게 나누면 좋을까요?",
                        ("커피·음료·디저트", "커피·베이커리·디저트", "음료·디저트")),
}

# 이미 정해진 것으로 볼 근거
_FILLED_OR_DONE = (S.FILLED, S.ASSUMED, S.REJECTED)


def _slot(card: dict, key: str) -> dict:
    return (card.get("slots") or {}).get(key) or {}


def _staff_count(card: dict) -> int:
    """담당자 수 (FILLED·ASSUMED만 센다)."""
    slot = _slot(card, "staff")
    if slot.get("status") not in (S.FILLED, S.ASSUMED):
        return 0
    value = slot.get("value")
    items = value if isinstance(value, list) else [value]
    return len([v for v in items if v])


def _contact_text(card: dict) -> str:
    slot = _slot(card, "contact_method")
    value = slot.get("value")
    items = value if isinstance(value, list) else [value]
    return ", ".join(str(v) for v in items if v)


def _candidates(card: dict, arch: str) -> list[str]:
    """물을 수 있는 칸: 허용 목록에서 이미 채운 칸과 추론으로 정해진 것을 뺀다."""
    out = []
    for key in ALLOWED.get(arch, ()):
        if _slot(card, key).get("status") in _FILLED_OR_DONE:
            continue
        if key == "team_mode" and _staff_count(card) >= 2:
            continue  # 담당자가 2명 이상이면 여럿이 운영하는 것이 정해짐
        if key == "order_mode" and "픽업" in _contact_text(card):
            continue  # 픽업 연락이면 픽업 주문이 정해짐
        out.append(key)
    return out


def _slot_text(card: dict, key: str) -> str:
    slot = _slot(card, key)
    value = slot.get("value")
    items = value if isinstance(value, list) else [value]
    return ", ".join(str(v) for v in items if v)


def _user_text(card: dict) -> str:
    """LLM에 주는 카드 요약: 업종·상품 이름·연락 방법만, 전화·주소는 뺀다."""
    ind_key = None
    try:
        from app.services import prd_engine
        ind_key = prd_engine.industry_of(card).key
    except Exception:
        ind_key = card.get("industry")
    lines = [
        f"업종: {_slot_text(card, 'business_type') or ind_key or ''}",
        f"상품: {_slot_text(card, 'offerings')}",
        f"연락 방법: {_slot_text(card, 'contact_method')}",
    ]
    return "\n".join(lines)


def _system_prompt(allowed: tuple[str, ...]) -> str:
    lines = "\n".join(f"- {k}: {S.SLOTS[k].describe}" for k in allowed)
    return (
        "너는 카페·미용실 웹사이트의 시안 구성을 정하는 도우미다. 아래 카드 요약을 보고, "
        "시안 구성을 바꾸는 것만 허용 목록에서 0~3개 고른다. "
        "아무것도 물을 필요가 없으면 빈 목록을 돌려준다. JSON만 출력한다.\n"
        f"허용 목록:\n{lines}\n"
        '출력 형식: {"slots": ["order_mode"]}'
    )


def _ask_llm(card: dict, arch: str, cands: list[str]) -> list[str] | None:
    """LLM 선택. 검증 실패·예외는 None (호출한 쪽이 기본값으로)."""
    allowed = ALLOWED.get(arch, ())
    try:
        raw = llm.chat_json(_system_prompt(allowed), _user_text(card),
                            timeout_sec=12, max_tokens=300)
    except Exception:
        log.exception("상황 탐색 호출 실패(기본값으로)")
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        m = re.search(r"\{.*\}", raw or "", re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except ValueError:
            return None
    slots = data.get("slots") if isinstance(data, dict) else None
    if not isinstance(slots, list):
        return None
    out = []
    for s in slots:
        # 허용 목록 안·이미 아는 칸 제외·중복 없음·3개 이하
        if s in allowed and s in cands and s not in out:
            out.append(s)
    return out[:3]


def _question(key: str) -> dict:
    text, options = QUESTIONS[key]
    return {"slot": key, "text": text, "options": S.choice_options(options[:S.MAX_OPTIONS])}


def probe(card: dict) -> list[dict]:
    """물을 상황 질문 목록. 검증을 통과한 것만, 없으면 빈 목록."""
    from app.services import archetype
    arch, _mode = archetype.of(card)
    cands = _candidates(card, arch)
    if not cands:
        return []
    picked = _ask_llm(card, arch, cands)
    if picked is None:
        picked = [k for k in DEFAULT.get(arch, ()) if k in cands]
    return [_question(k) for k in picked]
