"""요구사항 엔진 (REQUIREMENTS_ENGINE_PLAN.md §3, §7; DECISIONS.md D20~D26).

원칙: 추출은 AI(정해진 JSON), 무엇을 물을지는 규칙. 사장님이 말하지 않은 사실은 채우지 않는다.
카드는 dict로 세션에 저장된다(sessions.prd). 이 모듈은 카드만 바꾸고 저장은 호출한 쪽이 한다.
"""
import json
import logging
import re
from typing import Optional

from app import llm
from app.services import prd_schema as S

log = logging.getLogger(__name__)

SKIP_PHRASES = ("시안 먼저", "나머지는 알아서", "나머지 알아서", "그만 물어", "바로 만들어", "이제 보여")
YES_WORDS = ("네", "예", "응", "맞아요", "맞아", "맞습니다", "좋아요", "yes")
NO_WORDS = ("아니요", "아니오", "아니", "no", "틀려요")
NONE_WORDS = ("없음", "없어요", "해당 없음", "없습니다", "다 없어요")
LATER = "나중에 넣을게요"
_SATISFIED = (S.FILLED, S.ASSUMED, S.PLACEHOLDER, S.REJECTED)


# ── 카드 ──────────────────────────────────────────────────────────────

def new_card(template_industry: Optional[str] = None) -> dict:
    card = {"v": 1, "industry": None, "slots": {}, "hidden": {"asked": False, "selected": []},
            "asked": 0, "turn": 0, "pending": None, "done": False}
    if template_industry in S.INDUSTRIES:
        # D26: 업종과 구성만 가정으로 채우고, 가게 사실은 비운다.
        ind = S.INDUSTRIES[template_industry]
        card["industry"] = ind.key
        _put(card, "business_type", ind.name, S.ASSUMED)
        _put(card, "sections", list(ind.default_sections), S.ASSUMED)
    return card


def _put(card, key, value, status, turn=None, by=None):
    card["slots"][key] = {"value": value, "status": status, "evidence": [] if turn is None else [turn], "by": by}


def _slot(card, key) -> dict:
    return card["slots"].get(key) or {"value": None, "status": S.EMPTY, "evidence": [], "by": None}


def _satisfied(card, key) -> bool:
    return _slot(card, key)["status"] in _SATISFIED


def industry_of(card) -> S.Industry:
    if card.get("industry") in S.INDUSTRIES:
        return S.INDUSTRIES[card["industry"]]
    return S.industry_for(_slot(card, "business_type").get("value"))


# ── 추출 (AI) ─────────────────────────────────────────────────────────

_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["updates"],
    "properties": {"updates": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["slot", "value"],
        "properties": {"slot": {"type": "string", "enum": list(S.SLOTS)}, "value": {"type": "string"}}}}},
}


def _system_prompt() -> str:
    lines = "\n".join(f"- {s.key}: {s.describe}" for s in S.SLOTS.values())
    return (
        "너는 소상공인 웹사이트 요구사항을 정리하는 추출기다. 사장님의 이번 메시지에서 아래 칸에 해당하는 말만 뽑는다.\n"
        "규칙: 사장님이 실제로 말한 것만 뽑는다. 말하지 않은 전화번호·주소·가격·영업시간은 절대 만들지 않는다. "
        "해당하는 말이 없으면 그 칸은 넣지 않는다. 값이 여러 개인 칸은 항목마다 한 줄씩 따로 넣는다. "
        "직전 질문에 대한 짧은 대답(예: '전화요')은 그 질문의 칸으로 해석한다. JSON만 출력한다.\n"
        f"칸 정의:\n{lines}\n출력 형식(JSON 스키마):\n{json.dumps(_SCHEMA, ensure_ascii=False)}"
    )


def _parse_updates(raw: str) -> Optional[list[dict]]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        # 앞뒤에 설명이 붙은 경우를 위해 가장 바깥 {...}만 한 번 더 시도한다.
        m = re.search(r"\{.*\}", raw or "", re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except ValueError:
            return None
    ups = data.get("updates") if isinstance(data, dict) else None
    if not isinstance(ups, list):
        return None
    out = []
    for u in ups:
        if isinstance(u, dict) and u.get("slot") in S.SLOTS and isinstance(u.get("value"), str):
            value = u["value"].strip()[:200]
            if value:
                out.append({"slot": u["slot"], "value": value})
    return out


def extract(text: str, last_question: Optional[str]) -> list[dict]:
    """형식이 틀리면 한 번 다시 시도하고, 그래도 틀리거나 시간이 넘으면 빈 목록(대화는 계속된다)."""
    user = (f"[직전 질문] {last_question}\n" if last_question else "") + f"[사장님 메시지] {text}"
    for attempt in range(2):
        try:
            ups = _parse_updates(llm.chat_json(_system_prompt(), user))
        except Exception:
            log.exception("요구사항 추출 호출 실패")
            return []
        if ups is not None:
            return ups
        log.warning("요구사항 추출 형식 오류 (시도 %d)", attempt + 1)
    return []


# ── 규칙 ──────────────────────────────────────────────────────────────

def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def grounded(slot: str, value: str, text: str) -> bool:
    """사실 칸 값이 사장님 메시지에 근거가 있는지. 없으면 AI가 지어낸 것으로 보고 버린다."""
    if slot not in S.FACT_SLOTS:
        return True
    d = _digits(value)
    if d:
        return d in _digits(text)
    # 숫자 없는 사실(예: 지역명)은 두 글자 이상 낱말 하나 이상이 메시지에 있어야 한다.
    words = [w for w in re.split(r"[\s,·/]+", value) if len(w) >= 2]
    return bool(words) and any(w in text for w in words)


def _split_items(value) -> list[str]:
    if isinstance(value, list):
        return [v for v in value if v]
    return [p.strip() for p in re.split(r"[,·/]|그리고|랑|와|과", value or "") if p.strip()]


def apply_updates(card: dict, updates: list[dict], text: str, by=None, is_owner=True) -> list[str]:
    """추출 결과를 규칙에 맞춰 카드에 넣는다. 반영한 칸 키 목록을 돌려준다."""
    turn = card["turn"]
    applied = []
    for u in updates:
        key, value = u["slot"], u["value"]
        if not grounded(key, value, text):
            log.info("근거 없는 사실 버림: %s", key)
            continue
        spec = S.SLOTS[key]
        if key == "exclude":
            excl = set(_split_items(_slot(card, "exclude").get("value")) + _split_items(value))
            _put(card, "exclude", sorted(excl), S.FILLED, turn, by)
            for k in ("sections", "offerings"):
                cur = _slot(card, k)
                if cur.get("value"):
                    kept = [v for v in cur["value"] if not any(e in v for e in excl)]
                    card["slots"][k]["value"] = kept
            applied.append(key)
            continue
        if spec.fact and not is_owner:
            # D24: 공유방에서 방장이 아닌 사람이 말한 사실은 방장이 확인해야 카드에 들어간다.
            _put(card, key, value, S.PENDING_OWNER, turn, by)
            applied.append(key)
            continue
        if spec.multi:
            cur = _slot(card, key)
            items = list(cur["value"]) if cur["status"] == S.FILLED and cur.get("value") else []
            for item in _split_items(value):
                if item not in items:
                    items.append(item)
            excl = _split_items(_slot(card, "exclude").get("value"))
            items = [i for i in items if not any(e in i for e in excl)]
            _put(card, key, items, S.FILLED, turn, by)
        else:
            _put(card, key, value, S.FILLED, turn, by)
        if key == "business_type":
            card["industry"] = S.industry_for(value).key
        applied.append(key)
    return applied


def _default_for(card, key):
    ind = industry_of(card)
    if key == "business_type":
        # 업종을 가정으로 정하면 필수 칸이 바뀌므로, 모르는 업종은 지금 업종(대개 '기타')으로 둔다.
        return ind.name
    if key == "sections":
        return list(ind.default_sections)
    q = S.question_for(ind, key)
    real = [o for o in q.options if o not in (LATER, S.LET_AI)]
    return real[0] if real else None


def _answer_pending(card: dict, text: str, by, is_owner: bool) -> Optional[bool]:
    """직전 질문의 선택지·예/아니오 대답을 AI 없이 처리한다. 처리했으면 True, 선택지 대답이 아니면 None."""
    p = card.get("pending")
    if not p:
        return None
    t = text.strip()
    key = p.get("slot")
    if p["kind"] == "owner_confirm":
        if not is_owner:
            return None
        if t in YES_WORDS:
            card["slots"][key]["status"] = S.FILLED
        elif t in NO_WORDS:
            card["slots"].pop(key, None)
        else:
            return None
        card["pending"] = None
        return True
    if p["kind"] == "multi":
        if any(w in t for w in NONE_WORDS):
            selected = []
        else:
            selected = [k for k, label in industry_of(card).hidden if label in t or label.split("·")[0] in t]
            if not selected:
                return None  # 목록 밖 대답은 자유 대답으로 추출한다
        card["hidden"] = {"asked": True, "selected": selected}
        card["pending"] = None
        return True
    # 한 칸 질문
    if t == S.LET_AI:
        if S.SLOTS[key].fact or key == "shop_name":
            _put(card, key, None, S.PLACEHOLDER, card["turn"], by)
        else:
            _put(card, key, _default_for(card, key), S.ASSUMED, card["turn"], by)
    elif t == LATER:
        _put(card, key, None, S.PLACEHOLDER, card["turn"], by)
    elif t in p.get("options", []):
        if S.SLOTS[key].fact and not is_owner:
            _put(card, key, t, S.PENDING_OWNER, card["turn"], by)
        else:
            value = [t] if S.SLOTS[key].multi else t
            _put(card, key, value, S.FILLED, card["turn"], by)
            if key == "business_type":
                card["industry"] = S.industry_for(t).key
    else:
        return None
    card["pending"] = None
    return True


def next_question(card: dict) -> Optional[dict]:
    """다음에 물을 것 하나. 없으면 None."""
    ind = industry_of(card)
    # 1) 방장 확인이 필요한 사실
    for key, slot in card["slots"].items():
        if slot["status"] == S.PENDING_OWNER:
            return {"slot": key, "kind": "owner_confirm", "options": ["네", "아니요"],
                    "text": f"{S.label_for(ind, key)}을(를) '{slot['value']}'(으)로 받았어요. 방장님, 맞나요?"}
    # 2) 필수 칸 (업종별 순서)
    missing = [k for k in ind.required if not _satisfied(card, k)]
    done_count = len(ind.required) - len(missing)
    # 3) 숨은 항목은 필수 칸이 절반 넘게 찼을 때 한 번 (D21).
    #    업종을 모르면(기타) 묻지 않는다 — 일반 목록("주차·배송")은 엉뚱한 질문이 된다.
    if (ind.key != "other" and not card["hidden"]["asked"] and ind.hidden
            and (done_count >= 3 or not missing)):
        labels = [label for _, label in ind.hidden]
        return {"slot": None, "kind": "multi", "options": labels + ["없음"],
                "text": "해당되는 것을 모두 골라 주세요. 사이트에 안내해 드릴게요."}
    if missing:
        q = S.question_for(ind, missing[0])
        return {"slot": missing[0], "kind": "single", "options": list(q.options) + [S.LET_AI], "text": q.ask}
    return None


def finalize(card: dict) -> None:
    """질문을 마칠 때: 남은 필수 칸은 가정(사실 칸은 자리 표시)으로 채운다 (D20, D23)."""
    ind = industry_of(card)
    card["industry"] = ind.key  # 가정값이 업종(과 필수 칸)을 바꾸지 않게 고정한다
    for key in ind.required:
        if not _satisfied(card, key):
            if S.SLOTS[key].fact or key == "shop_name":
                _put(card, key, None, S.PLACEHOLDER)
            else:
                _put(card, key, _default_for(card, key), S.ASSUMED)
    if not _satisfied(card, "sections"):
        _put(card, "sections", list(ind.default_sections), S.ASSUMED)
    contact = str(_slot(card, "contact_method").get("value") or "")
    if not _satisfied(card, "phone") and ("전화" in contact or _slot(card, "contact_method")["status"] != S.FILLED):
        _put(card, "phone", None, S.PLACEHOLDER)
    if not _satisfied(card, "location"):
        _put(card, "location", None, S.PLACEHOLDER)
    # 숨은 항목을 묻기 전에 마쳤으면(건너뛰기·질문 상한) 다시 묻지 않는다.
    card["hidden"]["asked"] = True
    card["pending"] = None
    card["done"] = True


def turn(card: dict, text: str, by=None, is_owner=True) -> dict:
    """사장님 메시지 하나를 처리하고 다음에 할 말을 돌려준다."""
    card["turn"] += 1
    t = (text or "").strip()
    applied: list[str] = []
    wants_skip = any(p in t for p in SKIP_PHRASES)
    if t and not wants_skip:
        answered = _answer_pending(card, t, by, is_owner)
        if not answered:
            last_q = (card.get("pending") or {}).get("text")
            applied = apply_updates(card, extract(t, last_q), t, by, is_owner)
            card["pending"] = None if applied else card.get("pending")
    q = None if wants_skip or card["asked"] >= S.MAX_QUESTIONS else next_question(card)
    if q is None:
        finalize(card)
        return {"done": True, "question": None, "applied": applied}
    card["asked"] += 1
    card["pending"] = q
    card["done"] = False
    return {"done": False, "question": q, "applied": applied}


# ── 사람이 읽는 형태 ────────────────────────────────────────────────

def format_question(card: dict, q: dict) -> str:
    if q["kind"] == "multi":
        opts = " · ".join(q["options"])
        body = f"{q['text']}\n{opts}"
    else:
        body = q["text"] + "\n" + "  ".join(f"{i + 1}) {o}" for i, o in enumerate(q["options"]))
    return f"{body}\n\n(질문 {card['asked']}/{S.MAX_QUESTIONS} · '시안 먼저'라고 하시면 나머지는 알아서 채울게요)"


def _display(ind, key, slot) -> str:
    value = slot.get("value")
    if slot["status"] == S.PLACEHOLDER:
        return f"[{S.label_for(ind, key)} 입력 필요]"
    text = ", ".join(value) if isinstance(value, list) else (value or "AI가 정함")
    return f"{text} (가정)" if slot["status"] == S.ASSUMED else text


_SUMMARY_ORDER = ("business_type", "shop_name", "goal", "target", "offerings", "sections", "features", "exclude",
                  "contact_method", "phone", "hours", "location", "price", "detail")


def ack_text(card: dict, applied: list[str]) -> str:
    """이번 메시지에서 알아들은 것을 되짚는다. 사장님이 말한 요구가 버려지지 않았음을 보여준다."""
    if not applied:
        return ""
    ind = industry_of(card)
    parts = []
    for key in dict.fromkeys(applied):
        slot = card["slots"].get(key)
        if not slot or slot.get("value") in (None, "", []):
            continue
        value = ", ".join(slot["value"]) if isinstance(slot["value"], list) else slot["value"]
        parts.append(f"{S.label_for(ind, key)} '{value}'")
    return ("이렇게 이해했어요: " + " · ".join(parts) + "\n\n") if parts else ""


def summary_text(card: dict) -> str:
    ind = industry_of(card)
    lines = [f"• {S.label_for(ind, k)}: {_display(ind, k, card['slots'][k])}"
             for k in _SUMMARY_ORDER if k in card["slots"] and card["slots"][k]["status"] != S.REJECTED]
    hidden = [label for key, label in ind.hidden if key in card["hidden"]["selected"]]
    if hidden:
        lines.append(f"• 안내할 것: {', '.join(hidden)}")
    return "\n".join(lines)


def spec_text(card: dict) -> str:
    """코드생성에 넘길 요구사항 요약. 자리 표시 칸은 [..]로 남겨 지어내지 못하게 한다."""
    return "요구사항 카드:\n" + summary_text(card) + "\n(가정)은 기본값, [..] 자리는 비워 두고 자리 표시로 남길 것."
