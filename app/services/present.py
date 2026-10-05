"""화면에 내려줄 단추 계약: 질문 선택지(actions_for)와 AI 답장 아래 단추(reply_actions).

화면은 글자를 비교하지 않고 action만 보고 그린다.
- send: 그 글을 보낸다 / type: 입력칸으로 보낸다(보내지 않음) / skip_to_design: 알아서(바로 시안)
- later: 나중에 넣기 / none: 해당 없음(여러 개 고르기) / open_sheet: 화면의 시트를 연다
"""
from typing import Optional

from app.services import control_words as CW
from app.services import geo

TYPE_HINT = "여기에 적어 주세요"
_ACTION = {"type_it": "type", "let_ai_skip": "skip_to_design", "later": "later"}
ADDRESS_ACTION = {"action": "open_sheet", "sheet": "address", "label": "📍 정확한 주소 검색하기",
                  "hint": "지도·오시는 길에 쓸 정확한 주소를 검색해서 골라 주세요.", "owner_only": True}
# 요약·승인 질문이 나오는 상태
SUMMARY_STATE = "AWAIT_APPROVAL"


def actions_for(pending: Optional[dict]) -> list[dict]:
    """질문 선택지마다 {label, action, hint?}."""
    if not pending:
        return []
    multi = pending.get("kind") == "multi"
    out = []
    for opt in pending.get("options") or []:
        cid = CW.classify(opt)
        action = "none" if cid == "none" and multi else _ACTION.get(cid, "send")
        a = {"label": opt, "action": action}
        if action == "type":
            a["hint"] = TYPE_HINT
        out.append(a)
    return out


def location_text(card: Optional[dict]) -> str:
    """주소 칸 글(FILLED·ASSUMED만). 바뀌었는지 보려고 턴 전후로 잰다."""
    return geo._loc_text(card or {})


def reply_actions(card: Optional[dict], loc_before: str, state_before: Optional[str],
                  state_after: Optional[str]) -> list[dict]:
    """AI 답장 아래 단추. 주소는 있는데 지도 위치(location_geo)가 없고, 이번 턴에 주소가 바뀌었거나
    요약·승인 단계에 막 들어왔을 때만 '정확한 주소 검색' 단추를 단다(방장만)."""
    loc = location_text(card)
    if not loc or (card or {}).get("location_geo"):
        return []
    entered = state_after == SUMMARY_STATE and state_before != SUMMARY_STATE
    return [dict(ADDRESS_ACTION)] if loc != loc_before or entered else []
