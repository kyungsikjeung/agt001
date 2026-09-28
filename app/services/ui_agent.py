"""UI 에이전트 (J11, UI_AGENT_PLAN §4).

울타리 친 명세 개선기다. HTML·CSS를 쓰지 않고 design_patch 조각만 만든다.
고칠 수 있는 칸(안마다): palette(원형 후보 안)·tone(calm|rich)·order(첫 화면 뒤
순서, 원래 id만)·hide(부를 수 있는 종류만)·labels(12자 이하)·subtitle(40자 이하,
카드 숫자만)·inverse(짙은 띠 한 곳 또는 null). 틀린 칸은 버리고 예외는 내지 않는다.
"""
import copy
import datetime
import json
import logging
import re
import time

from app import llm
from app.config import settings

log = logging.getLogger(__name__)

# 숨길 수 있는 섹션 종류. 예약·상품·연락·길안내는 숨기면 손님이 행동을 못 한다.
HIDABLE_TYPES = frozenset({"gallery", "intro", "features", "video", "concerns"})
TONES = ("calm", "rich")
ARCHETYPES = ("A", "B", "C", "D", "E", "F", "G", "H")

_IMPROVE_SYSTEM = (
    "너는 웹사이트 시안 3안을 다듬는 도우미다. HTML·CSS를 쓰지 않고, 각 안의 조각을 "
    "JSON 하나로만 출력한다.\n"
    "고칠 수 있는 칸(안마다):\n"
    '- "palette": 허용 팔레트 안의 이름 하나\n'
    '- "tone": "calm" 또는 "rich"\n'
    '- "order": 첫 화면 뒤 섹션 id 순서(원래 안의 id만, 빠짐·중복 없이)\n'
    "- \"hide\": 숨길 섹션 id 목록(부를 수 있는 종류만)\n"
    '- "labels": {섹션 id: 12자 이하 제목}\n'
    "- \"subtitle\": 첫 화면 부제(40자 이하. 숫자는 카드 요약에 있는 숫자만)\n"
    '- "inverse": 짙은 띠 섹션 id 하나 또는 null(한 곳만)\n'
    "바꾸지 않을 칸은 빼고, 바꾸지 않을 안은 빈 {}로 둔다. "
    "카드 요약에 없는 사실(전화·주소·가격·이름·숫자)은 쓰지 않는다.\n"
    '출력 형식: {"v1": {...}, "v2": {...}, "v3": {...}}'
)

_JUDGE_SYSTEM = (
    "너는 가게 설명을 보고 손님 동선 원형 하나를 고르는 도우미다. JSON만 출력한다.\n"
    "원형: A(방문·메뉴형: 카페·식당) B(사람 예약형: 미용실·PT) C(공간 예약형: 펜션·스튜디오) "
    "D(상담·등록형: 학원) E(클래스·체험형: 공방) F(작업·의뢰형: 사진·전문가) "
    "G(모임·단체형: 동호회·교회) H(서비스·상품형: 웹서비스·판매).\n"
    '출력 형식: {"archetype": "B", "reason": "이유 한 줄"}'
)


def _arch_of(card: dict) -> str:
    """카드의 원형 글자. 모르면 A."""
    try:
        from app.services import archetype
        arch = archetype.of(card or {})[0]
    except Exception:
        arch = "A"
    return arch if arch in ARCHETYPES else "A"


def _sections_of(spec: dict) -> list:
    secs = (spec or {}).get("sections") or []
    return [s for s in secs if isinstance(s, dict)]


def _ctx(spec: dict) -> dict:
    """검증용 문맥: id별 섹션, 첫 화면 뒤 id 목록."""
    secs = _sections_of(spec)
    by_id = {s.get("id"): s for s in secs if isinstance(s.get("id"), str)}
    hero_ids = {s.get("id") for s in secs if s.get("type") == "hero"}
    rest = [sid for sid in by_id if sid not in hero_ids]
    return {"by_id": by_id, "rest": rest}


def _facts(card: dict) -> list:
    """카드 사실 값(사장님이 말한 칸). 지어내기 검사의 기준이다."""
    from app.services import prd_schema as S
    slots = (card or {}).get("slots") or {}
    out = []
    for slot in slots.values():
        if not isinstance(slot, dict) or slot.get("status") != S.FILLED:
            continue
        value = slot.get("value")
        items = value if isinstance(value, list) else [value]
        for item in items:
            text = str(item or "").strip()
            if text and text not in out:
                out.append(text)
    return out


def _numbers(text: str) -> set:
    return set(re.findall(r"\d+", text or ""))


def _fact_numbers(card: dict) -> set:
    found = set()
    for fact in _facts(card):
        found |= _numbers(fact)
    return found


def _clean_palette(value, arch: str):
    from app.services import palette
    cands = palette.ARCHETYPE_PALETTES.get(arch, palette.ARCHETYPE_PALETTES["A"])
    return value if isinstance(value, str) and value in cands else None


def _clean_tone(value):
    return value if value in TONES else None


def _clean_order(value, ctx: dict):
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        return None
    if set(value) == set(ctx["rest"]) and len(value) == len(ctx["rest"]):
        return list(value)
    return None


def _clean_hide(value, ctx: dict) -> list:
    """못 숨기는 종류·없는 id는 버린다."""
    if not isinstance(value, list):
        return []
    out = []
    for vid in value:
        sec = ctx["by_id"].get(vid) if isinstance(vid, str) else None
        if sec is not None and sec.get("type") in HIDABLE_TYPES and vid not in out:
            out.append(vid)
    return out


def _clean_labels(value, ctx: dict) -> dict:
    if not isinstance(value, dict):
        return {}
    out = {}
    for sid, text in value.items():
        if sid in ctx["by_id"] and isinstance(text, str) and 1 <= len(text) <= 12:
            out[sid] = text
    return out


def _clean_subtitle(value, card: dict):
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not (1 <= len(text) <= 40):
        return None
    if _numbers(text) - _fact_numbers(card):
        return None  # 카드에 없는 숫자는 지어내기다
    return text


def validate_patch(card: dict, variants: list, raw) -> dict:
    """LLM 조각을 안마다 검증한다. 틀린 칸은 버린다."""
    out = {}
    if not isinstance(raw, dict):
        return out
    arch = _arch_of(card)
    for var in variants or []:
        if not isinstance(var, dict) or not isinstance(var.get("id"), str):
            continue
        vid = var["id"]
        frag = raw.get(vid)
        cleaned = {}
        if isinstance(frag, dict) and isinstance(var.get("spec"), dict):
            ctx = _ctx(var["spec"])
            pal = _clean_palette(frag.get("palette"), arch)
            if pal is not None:
                cleaned["palette"] = pal
            tone = _clean_tone(frag.get("tone"))
            if tone is not None:
                cleaned["tone"] = tone
            order = _clean_order(frag.get("order"), ctx)
            if order is not None:
                cleaned["order"] = order
            hide = _clean_hide(frag.get("hide"), ctx)
            if hide:
                cleaned["hide"] = hide
            labels = _clean_labels(frag.get("labels"), ctx)
            if labels:
                cleaned["labels"] = labels
            subtitle = _clean_subtitle(frag.get("subtitle"), card)
            if subtitle is not None:
                cleaned["subtitle"] = subtitle
            if "inverse" in frag:
                inv = frag["inverse"]
                if inv is None:
                    cleaned["inverse"] = None
                elif isinstance(inv, str) and inv in ctx["by_id"]:
                    cleaned["inverse"] = inv
        out[vid] = cleaned
    return out


def _strip_inverse(spec: dict) -> None:
    for sec in _sections_of(spec):
        if sec.get("tone") == "inverse":
            sec.pop("tone", None)


def _apply_fragment(card: dict, spec: dict, frag: dict) -> None:
    """검증된 조각 하나를 명세 사본에 적용한다."""
    by_id = {s.get("id"): s for s in _sections_of(spec) if isinstance(s.get("id"), str)}
    if "palette" in frag and isinstance(spec.get("tokens"), dict):
        spec["tokens"]["palette"] = frag["palette"]
    if "inverse" in frag:
        _strip_inverse(spec)
        if frag["inverse"] in by_id:
            by_id[frag["inverse"]]["tone"] = "inverse"
    if frag.get("tone") == "calm":
        _strip_inverse(spec)
    elif frag.get("tone") == "rich":
        has = any(s.get("tone") == "inverse" for s in _sections_of(spec))
        if not has:
            rest = [s for s in _sections_of(spec) if s.get("type") != "hero"]
            if rest:
                rest[0]["tone"] = "inverse"
    if "order" in frag:
        heroes = [s for s in _sections_of(spec) if s.get("type") == "hero"]
        pos = {sid: i for i, sid in enumerate(frag["order"])}
        rest = sorted((s for s in _sections_of(spec) if s.get("type") != "hero"),
                      key=lambda s: pos.get(s.get("id"), len(pos)))
        spec["sections"] = heroes + rest
    if frag.get("hide"):
        gone = set(frag["hide"])
        spec["sections"] = [s for s in _sections_of(spec) if s.get("id") not in gone]
        by_id = {s.get("id"): s for s in _sections_of(spec) if isinstance(s.get("id"), str)}
    for sid, text in (frag.get("labels") or {}).items():
        sec = by_id.get(sid)
        if sec is None:
            continue
        if "label" in sec:
            sec["label"] = text
        content = sec.get("content")
        if isinstance(content, dict) and "label" in content:
            content["label"] = text
    if "subtitle" in frag:
        hero = next((s for s in _sections_of(spec) if s.get("type") == "hero"), None)
        if hero is not None and isinstance(hero.get("content"), dict):
            hero["content"]["subtitle"] = frag["subtitle"]


def _apply_cleaned(card: dict, variants: list, cleaned: dict) -> list:
    out = []
    for var in variants or []:
        try:
            spec = copy.deepcopy(var["spec"])
            _apply_fragment(card, spec, cleaned.get(var.get("id"), {}))
            item = {k: v for k, v in var.items() if k != "spec"}
            item["spec"] = spec
            out.append(item)
        except Exception:
            log.exception("시안 조각 적용 실패(원본 유지)")
            item = {k: copy.deepcopy(v) for k, v in var.items()}
            out.append(item)
    return out


def apply(card: dict, variants: list) -> list:
    """card["design_patch"]를 검증해 맞는 칸만 적용한 사본. 틀린 칸은 버리고 예외는 없다."""
    try:
        cleaned = validate_patch(card, variants, (card or {}).get("design_patch"))
        return _apply_cleaned(card, variants, cleaned)
    except Exception:
        log.exception("시안 조각 적용 실패(전체 원본 유지)")
        return copy.deepcopy(variants)


def _slot_text(card: dict, key: str) -> str:
    from app.services import prd_schema as S
    slot = ((card or {}).get("slots") or {}).get(key) or {}
    if slot.get("status") not in (S.FILLED, S.ASSUMED):
        return ""
    value = slot.get("value")
    items = value if isinstance(value, list) else [value]
    return ", ".join(str(v) for v in items if v)


def _card_summary(card: dict) -> str:
    """LLM에 주는 카드 요약. 전화·주소는 넣지 않는다(D39)."""
    mood = ""
    concept = (card or {}).get("concept")
    if isinstance(concept, dict) and isinstance(concept.get("mood"), list):
        mood = ", ".join(str(m) for m in concept["mood"] if m)
    return (f"업종: {_slot_text(card, 'business_type')}\n"
            f"상품: {_slot_text(card, 'offerings')}\n"
            f"분위기: {mood}")


def _variant_summary(var: dict) -> str:
    spec = var.get("spec") or {}
    tokens = spec.get("tokens") or {}
    rich = any(s.get("tone") == "inverse" for s in _sections_of(spec) if isinstance(s, dict))
    lines = [f"안 {var.get('id')}({var.get('name', '')}): "
             f"palette={tokens.get('palette')}, tone={'rich' if rich else 'calm'}"]
    for sec in _sections_of(spec):
        label = sec.get("label") or ((sec.get("content") or {}).get("label") if isinstance(sec.get("content"), dict) else "") or ""
        lines.append(f"  - {sec.get('id')}(종류 {sec.get('type')}, 제목 {label})")
    hero = next((s for s in _sections_of(spec) if s.get("type") == "hero"), None)
    if hero is not None and isinstance(hero.get("content"), dict):
        lines.append(f"  첫 화면 부제: {hero['content'].get('subtitle', '')}")
    return "\n".join(lines)


def _improve_user(card: dict, variants: list, reason: str) -> str:
    from app.services import palette
    arch = _arch_of(card)
    cands = palette.ARCHETYPE_PALETTES.get(arch, palette.ARCHETYPE_PALETTES["A"])
    parts = [_card_summary(card), f"원형: {arch}", f"허용 팔레트: {', '.join(cands)}",
             f"숨길 수 있는 종류: {', '.join(sorted(HIDABLE_TYPES))}"]
    for var in variants or []:
        if isinstance(var, dict):
            parts.append(_variant_summary(var))
    if reason:
        parts.append(f"지난 조각이 탈락한 사유(고쳐서 다시 내주세요): {reason}")
    return "\n".join(parts)


def _parse_json(raw) -> dict | None:
    if not isinstance(raw, str):
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        found = re.search(r"\{.*\}", raw, re.S)
        try:
            data = json.loads(found.group(0)) if found else None
        except ValueError:
            return None
    return data if isinstance(data, dict) else None


def _dump(spec: dict) -> str:
    return json.dumps(spec or {}, ensure_ascii=False)


def _chrome_hrefs(spec: dict) -> set:
    """주 행동 버튼 주소(첫 화면·상단 내비·하단 바)."""
    out = set()

    def _href(node) -> None:
        if isinstance(node, dict) and isinstance(node.get("href"), str):
            out.add(node["href"])

    hero = next((s for s in _sections_of(spec) if s.get("type") == "hero"), None)
    content = (hero or {}).get("content") or {}
    _href(content.get("cta"))
    _href(content.get("cta2"))
    nav = (spec or {}).get("navbar") or {}
    _href(nav.get("cta"))
    for link in nav.get("links") or []:
        _href(link)
    bar = (spec or {}).get("actionbar") or {}
    _href(bar.get("primary"))
    _href(bar.get("secondary"))
    return {h for h in out if h}


def _dead_anchors(html_text: str) -> set:
    hrefs = re.findall(r'href="(#[^"]+)"', html_text or "")
    ids = set(re.findall(r'id="([^"]+)"', html_text or ""))
    return {h[1:] for h in hrefs if h != "#" and h[1:] not in ids}


def _safety_reason(card: dict, variants: list, patched: list) -> str | None:
    """원래 안 대비 안전 검사. 통과면 None, 탈락이면 사유."""
    facts = [f for f in _facts(card) if f]
    fact_nums = _fact_numbers(card)
    orig = {v["id"]: _dump(v.get("spec")) for v in variants if isinstance(v, dict)}
    new = {p["id"]: _dump(p.get("spec")) for p in patched if isinstance(p, dict)}
    for var in variants:
        if not isinstance(var, dict):
            continue
        vid = var.get("id")
        for fact in facts:
            if fact in orig.get(vid, "") and fact not in new.get(vid, ""):
                return f"{vid}: 카드 사실 '{fact}'이 원래 안에서 보였는데 개선 안에서 사라졌습니다"
        gone = _chrome_hrefs(var.get("spec")) - _chrome_hrefs(
            next((p for p in patched if isinstance(p, dict) and p.get("id") == vid), {}).get("spec"))
        if gone:
            return f"{vid}: 주 행동 버튼({', '.join(sorted(gone))})이 사라졌습니다"
        added = _numbers(new.get(vid, "")) - _numbers(orig.get(vid, "")) - fact_nums
        if added:
            return f"{vid}: 카드에 없는 새 숫자({', '.join(sorted(added))})가 생겼습니다"
    try:
        from app.services import design_variants as DV
        from app.services import site_render
        kind = DV.kind_for(card)
        title = DV.title_for(card)
    except Exception:
        kind, title = "other", ""
    old_dead = set()
    try:
        for var in variants:
            if isinstance(var, dict):
                old_dead |= _dead_anchors(site_render.render_site(
                    var.get("spec"), site_key="ui-agent", title=title, kind=kind))
    except Exception:
        pass
    for item in patched:
        if not isinstance(item, dict):
            continue
        try:
            page = site_render.render_site(item.get("spec"), site_key="ui-agent", title=title, kind=kind)
        except Exception as e:
            return f"{item.get('id')}: 다시 그리기가 실패했습니다({e})"
        fresh = _dead_anchors(page) - old_dead
        if fresh:
            return f"{item.get('id')}: 눌러도 가지 않는 버튼이 생겼습니다(#{', #'.join(sorted(fresh))})"
    return None


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def improve(card: dict, variants: list, *, timeout_sec: float = 20.0) -> dict | None:
    """LLM 조각 → 검증 → 적용 → 안전 검사. 실패하면 사유를 붙여 한 번 더(최대 2회).

    전체 시간 초과·예외면 None(규칙 안 유지).
    """
    try:
        budget = max(0.0, float(timeout_sec))
        if not variants:
            return None
        deadline = time.monotonic() + budget
    except Exception:
        return None
    reason = ""
    for _attempt in (1, 2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            raw = llm.chat_json(_IMPROVE_SYSTEM, _improve_user(card, variants, reason),
                                timeout_sec=max(1.0, min(remaining, budget or 20.0)),
                                max_tokens=700)
        except Exception:
            log.exception("시안 개선 호출 실패")
            return None
        data = _parse_json(raw)
        if data is None:
            reason = "JSON 조각이 아닙니다. 형식에 맞게 다시 내주세요."
            continue
        if time.monotonic() >= deadline:
            return None  # 전체 시간 초과
        cleaned = validate_patch(card, variants, data)
        patched = _apply_cleaned(card, variants, cleaned)
        bad = _safety_reason(card, variants, patched)
        if bad is None:
            ids = [v["id"] for v in variants if isinstance(v, dict) and isinstance(v.get("id"), str)]
            patch = {vid: cleaned.get(vid, {}) for vid in ids}
            patch["made_at"] = _now_iso()
            patch["model"] = settings.nim_chat_model
            return patch
        reason = bad
        log.info("시안 개선 %d회 탈락: %s", _attempt, bad)
    return None
