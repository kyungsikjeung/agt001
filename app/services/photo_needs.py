"""항목 사진 필요 판단 (BETA_FLOW_PLAN §2.7).

- 항목 후보(items): 원형별로 객실·메뉴·시술·수업·작업 이름을 뽑는다 (LLM 없이 결정론).
- 판단(judge): 후보 중 사진이 있으면 좋은 항목을 LLM이 고른다. 카드에 sig로 저장해 한 번만 묻는다.
- 실패하면 규칙으로 대신한다. 카드가 깨져도 절대 올리지 않는다.
"""
import json
import logging
import re

from app import llm

log = logging.getLogger(__name__)

# 수업 이름에 이 말이 있으면 사진을 기대한다 (규칙 판단용).
_CLASS_PHOTO_WORDS = ("체험", "원데이", "공방", "만들기")

_JUDGE_SYSTEM = (
    "너는 작은 가게 홈페이지의 항목 중 사진이 있으면 좋은 항목을 고르는 도우미다. "
    "손님이 사진을 보고 고르거나 결과를 미리 보고 싶어하는 항목만 고른다. "
    "주어진 이름만 그대로 쓴다. 다른 이름은 쓰지 않는다. "
    '출력은 JSON 한 줄: {"need": ["이름1", "이름2"]}'
)


def _names_of(data: dict, key: str) -> list[str]:
    out = []
    for entry in data.get(key) or []:
        name = str((entry or {}).get("name") or "").strip()
        if name and name not in out:
            out.append(name)
    return out


def _catalog_names(data: dict) -> list[str]:
    out = []
    for group in data.get("catalog") or []:
        for item in (group or {}).get("items") or []:
            name = str((item or {}).get("name") or "").strip()
            if name and name not in out:
                out.append(name)
    return out


def items(card: dict) -> list[dict]:
    """항목 후보 [{"name": ..., "kind": ...}]. 최대 8개, 빈 이름 빼고 중복 없이."""
    try:
        from app.services import archetype
        from app.services import card_data
        arch = archetype.of(card)[0]
        data = card_data.build(card)
    except Exception:
        return []
    try:
        if arch == "C":
            raw = [(n, "room") for n in _names_of(data, "rooms")]
        elif arch == "A":
            raw = [(n, "menu") for n in _catalog_names(data)]
        elif arch == "B":
            raw = [(n, "style") for n in _catalog_names(data)]
        elif arch in ("D", "E"):
            names = _names_of(data, "classes") or _catalog_names(data)
            raw = [(n, "class") for n in names]
        else:
            raw = [(n, "work") for n in _catalog_names(data)]
    except Exception:
        return []
    out = []
    for name, kind in raw:
        if name and name not in [i["name"] for i in out]:
            out.append({"name": name, "kind": kind})
        if len(out) >= 8:
            break
    return out


def _rule_need(candidates: list[dict]) -> list[str]:
    """LLM이 실패할 때 쓰는 규칙: 수업은 말로 가리고 나머지는 모두 필요."""
    need = []
    for item in candidates:
        if item.get("kind") in ("room", "menu", "style", "work"):
            need.append(item["name"])
        elif item.get("kind") == "class" and any(w in item["name"] for w in _CLASS_PHOTO_WORDS):
            need.append(item["name"])
    return need


def _industry_name(card: dict) -> str:
    try:
        from app.services import prd_engine
        return prd_engine.industry_of(card).name or ""
    except Exception:
        return ""


def judge(card: dict) -> list[str]:
    """사진이 필요한 항목 이름 목록. 같은 후보(sig)면 저장된 값을 바로 쓴다."""
    candidates = items(card)
    if not candidates:
        try:
            card["photo_needs"] = {"sig": "", "need": []}
        except Exception:
            pass
        return []
    names = [i["name"] for i in candidates]
    sig = "|".join(names)
    try:
        stored = (card or {}).get("photo_needs") or {}
    except Exception:
        stored = {}
    if stored.get("sig") == sig and isinstance(stored.get("need"), list):
        return [n for n in stored["need"] if n in names]
    try:
        user = f"업종: {_industry_name(card)}\n항목: {', '.join(names)}"
        raw = llm.chat_json(_JUDGE_SYSTEM, user, timeout_sec=10, max_tokens=200)
        # 앞뒤에 설명이 붙어 오면 가장 바깥 {...}만 읽는다 (다른 LLM 호출과 같은 방식).
        m = re.search(r"\{.*\}", raw or "", re.S)
        data = json.loads(m.group(0) if m else raw)
        raw_need = data.get("need") if isinstance(data, dict) else None
        if not isinstance(raw_need, list):
            raise ValueError("need 없음")
        need = [n for n in names if n in raw_need]
    except Exception:
        log.exception("사진 필요 판단 실패(규칙으로 대신함)")
        need = _rule_need(candidates)
    try:
        card["photo_needs"] = {"sig": sig, "need": need}
    except Exception:
        pass
    return need


def needed(card: dict) -> list[str]:
    """저장된 판단 결과. 후보가 바뀌었으면 빈 목록 (LLM을 부르지 않는다)."""
    try:
        sig = "|".join(i["name"] for i in items(card))
        stored = (card or {}).get("photo_needs") or {}
        if stored.get("sig") == sig and isinstance(stored.get("need"), list):
            names = {i["name"] for i in items(card)}
            return [n for n in stored["need"] if n in names]
        return []
    except Exception:
        return []


def missing(card: dict) -> list[str]:
    """필요한 항목 중 사장님 사진도 AI 그림도 없는 이름."""
    try:
        out = []
        for name in needed(card):
            try:
                from app.services import card_data
                hit = card_data.item_photo(card, name)
            except Exception:
                hit = None
            if hit:
                continue
            ai = ((card or {}).get("ai_images") or {}).get("item:" + name) or {}
            if ai.get("url"):
                continue
            out.append(name)
        return out
    except Exception:
        return []


def photo_tags(card: dict) -> list[dict]:
    """사진 올리기에 붙이는 태그 목록. 판단이 없으면 후보 전체 + 가게·공간."""
    try:
        names = needed(card) or [i["name"] for i in items(card)]
    except Exception:
        names = []
    tags = [{"tag": "item:" + n, "label": n} for n in names]
    tags.append({"tag": "space", "label": "가게·공간"})
    return tags


def valid_tag(card: dict, tag) -> bool:
    """올리기 태그가 지금 카드에 맞는지. 아니면 버린다."""
    try:
        if tag in ("hero", "space", "notice"):
            return True  # notice 태그는 공지 사진용(D58)
        if isinstance(tag, str) and tag.startswith("item:"):
            return tag[5:] in [i["name"] for i in items(card)]
        return False
    except Exception:
        return False
