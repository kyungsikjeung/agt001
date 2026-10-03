"""구역 순서·숨기기·추가·모양 편집 (EDIT_WAVE2_CONTRACT §3.1, COMPONENT_ENGINE_PLAN §6).

순수 함수만 둔다. DB 접근 없음(모양 묶음은 컴포넌트 등록표 components.json을 읽는다).
"""
import copy

from app.services import components as COMP

# 옮기기·숨기기 불가 구역
LOCKED = ("hero", "inquiry")
# 한 안에 더할 수 있는 구역 상한
MAX_ADDED = 3


def _strategies(blueprint: dict) -> list:
    """청사진 전략 목록. 없으면 빈 목록."""
    if not isinstance(blueprint, dict):
        return []
    strategies = blueprint.get("strategies")
    return strategies if isinstance(strategies, list) else []


def _strategy_nodes(blueprint: dict, pos: int) -> list:
    """pos번 전략의 구역 노드 목록. 이상하면 빈 목록."""
    strategies = _strategies(blueprint)
    if not isinstance(pos, int) or not 0 <= pos < len(strategies):
        return []
    strategy = strategies[pos]
    if not isinstance(strategy, dict):
        return []
    sections = strategy.get("sections")
    return [n for n in sections if isinstance(n, dict) and isinstance(n.get("id"), str)] if isinstance(sections, list) else []


def _base_ids(blueprint: dict, pos: int) -> list:
    """이 안의 기본 순서 (hero + 전략 구역 id)."""
    return ["hero"] + [n["id"] for n in _strategy_nodes(blueprint, pos)]


def pool(blueprint: dict) -> dict:
    """청사진 3개 전략의 구역 노드를 id별로 (처음 나온 것). hero는 없음."""
    out = {}
    for strategy in _strategies(blueprint):
        if not isinstance(strategy, dict):
            continue
        sections = strategy.get("sections")
        if not isinstance(sections, list):
            continue
        for node in sections:
            if not isinstance(node, dict):
                continue
            nid = node.get("id")
            if not isinstance(nid, str) or not nid or nid == "hero":
                continue
            if nid not in out:
                out[nid] = node
    return out


def _str_list(value) -> list:
    """문자열 목록만 남긴다 (중복 제거, 순서 유지)."""
    out = []
    if not isinstance(value, list):
        return out
    for item in value:
        if isinstance(item, str) and item and item not in out:
            out.append(item)
    return out


def _node_for(blueprint: dict, pos: int, sid: str) -> dict:
    """이 안의 구역 노드(없으면 다른 안에서 더한 노드). hero는 전략의 hero 변형으로 만든다."""
    if sid == "hero":
        strategies = _strategies(blueprint)
        strategy = strategies[pos] if isinstance(pos, int) and 0 <= pos < len(strategies) else {}
        hero = strategy.get("hero") if isinstance(strategy, dict) else None
        return {"id": "hero", "type": "hero", "bind": "hero", "variant": hero if isinstance(hero, str) else ""}
    for node in _strategy_nodes(blueprint, pos):
        if node.get("id") == sid:
            return node
    node = pool(blueprint).get(sid)
    return node if isinstance(node, dict) else {}


def _clean_variants(raw, blueprint: dict, pos: int, ids: set) -> dict:
    """{구역 id: 모양} 중 이 안에 있고 같은 데이터로 바꿀 수 있는 것만 (기본 모양과 같으면 뺀다)."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for sid, variant in raw.items():
        if not isinstance(sid, str) or sid not in ids or not isinstance(variant, str):
            continue
        node = _node_for(blueprint, pos, sid)
        stype, bind = node.get("type"), node.get("bind", "none")
        if not isinstance(stype, str) or variant == node.get("variant"):
            continue
        if COMP.can_switch(stype, bind, variant):
            out[sid] = variant
    return out


def normalize(edits: dict | None, blueprint: dict, pos: int) -> dict | None:
    """{order, hidden, added, variants}를 이 청사진·안 기준으로 정리. 아무 효과 없으면 None.

    variants(구역별 모양)는 바꾼 것이 있을 때만 키를 둔다(예전 편집 모양 그대로)."""
    if not isinstance(edits, dict):
        return None
    base = _base_ids(blueprint, pos)
    if not base:
        return None
    base_set = set(base)
    pool_ids = set(pool(blueprint))

    # added: pool에 있고 이 안에 없는 id만, 최대 3
    added = [i for i in _str_list(edits.get("added")) if i in pool_ids and i not in base_set][:MAX_ADDED]

    # 더한 구역은 inquiry 바로 앞에 (없으면 맨 뒤)
    if "inquiry" in base:
        idx = base.index("inquiry")
        effective = base[:idx] + added + base[idx:]
    else:
        effective = base + added
    effective_set = set(effective)

    # hidden: 이 안(+added)에 있는 id만, LOCKED 제외
    hidden = [i for i in _str_list(edits.get("hidden")) if i in effective_set and i not in LOCKED]

    # order: 아는 id만, LOCKED는 원래 자리 유지
    want = [i for i in _str_list(edits.get("order")) if i in effective_set and i not in LOCKED]
    rest = [i for i in effective if i not in LOCKED and i not in want]
    movable = want + rest
    order = []
    cursor = 0
    for i in effective:
        if i in LOCKED:
            order.append(i)
        else:
            order.append(movable[cursor])
            cursor += 1

    variants = _clean_variants(edits.get("variants"), blueprint, pos, effective_set)
    if not added and not hidden and order == effective and not variants:
        return None
    out = {"order": order, "hidden": hidden, "added": added}
    if variants:
        out["variants"] = variants
    return out


def _skeleton_shape(node: dict) -> dict:
    """added 노드를 skeleton 모양으로 ({id,type,variant,bind,content:{}, label/nav/tone/order/optional})."""
    sec = {"id": node.get("id"), "type": node.get("type"), "variant": node.get("variant"),
           "bind": node.get("bind", "none"), "content": {}}
    for key in ("label", "nav", "tone"):
        if node.get(key):
            sec[key] = node[key]
    if node.get("order") is True:
        sec["order"] = True
    if node.get("optional") is True:
        sec["optional"] = True
    return sec


def apply(skeleton: dict, blueprint: dict, pos: int, edits: dict | None) -> dict:
    """SD.skeleton 결과(hero가 0번)에 적용한 새 명세. hero는 항상 0번."""
    out = copy.deepcopy(skeleton) if isinstance(skeleton, dict) else {"sections": []}
    sections = out.get("sections")
    if not isinstance(sections, list):
        out["sections"] = sections = []
    if not isinstance(edits, dict):
        return out
    try:
        cleaned = normalize(edits, blueprint, pos)
    except Exception:
        return out
    if cleaned is None:
        return out
    by_id = {}
    for sec in sections:
        if isinstance(sec, dict) and isinstance(sec.get("id"), str):
            by_id.setdefault(sec["id"], sec)
    nodes = {i: n for i, n in pool(blueprint).items()}
    for aid in cleaned["added"]:
        if aid not in by_id and aid in nodes:
            sec = _skeleton_shape(nodes[aid])
            by_id[aid] = sec
    hidden = set(cleaned["hidden"])
    shapes = cleaned.get("variants") or {}
    ordered = []
    for sid in cleaned["order"]:
        if sid in hidden:
            continue
        sec = by_id.get(sid)
        if sec is not None:
            if sid in shapes:
                # 모양만 바꾼다. 데이터 채우기(site_data.resolve)가 이 모양을 보고 내용 모양을 맞춘다.
                sec["variant"] = shapes[sid]
            ordered.append(sec)
    # hero는 항상 0번
    hero = [s for s in ordered if s.get("id") == "hero"]
    rest = [s for s in ordered if s.get("id") != "hero"]
    out["sections"] = hero + rest
    return out


def sections(blueprint: dict, pos: int, edits: dict | None) -> list[dict]:
    """GET preview의 sections(숨긴 것 포함, 순서대로) — [{id, bind, locked, hidden, node}]."""
    base = _base_ids(blueprint, pos)
    if not base:
        return []
    nodes = pool(blueprint)
    cleaned = normalize(edits, blueprint, pos) if isinstance(edits, dict) else None
    order = cleaned["order"] if cleaned else base
    hidden = set(cleaned["hidden"]) if cleaned else set()
    shapes = (cleaned or {}).get("variants") or {}
    out = []
    for sid in order:
        if sid == "hero":
            node = {"id": "hero", "bind": "hero"}
            bind = "hero"
        else:
            node = nodes.get(sid) or {}
            bind = node.get("bind", "none") if isinstance(node, dict) else "none"
        base_node = _node_for(blueprint, pos, sid)
        stype = base_node.get("type") if isinstance(base_node.get("type"), str) else ""
        out.append({"id": sid, "bind": bind, "locked": sid in LOCKED,
                    "hidden": sid in hidden, "node": copy.deepcopy(node) if isinstance(node, dict) else {},
                    # 구역 모양 바꾸기 (COMPONENT_ENGINE_PLAN §6): 지금 모양·기본 모양·바꿀 수 있는 모양
                    "type": stype, "variant": shapes.get(sid) or base_node.get("variant") or "",
                    "base_variant": base_node.get("variant") or "",
                    "shapes": COMP.shapes(stype, bind) if stype else []})
    return out


def addable(blueprint: dict, pos: int, edits: dict | None) -> list[dict]:
    """pool 중 이 안(+added)에 없는 것."""
    base = _base_ids(blueprint, pos)
    if not base:
        return []
    nodes = pool(blueprint)
    cleaned = normalize(edits, blueprint, pos) if isinstance(edits, dict) else None
    has = set(base) | set(cleaned["added"] if cleaned else [])
    return [copy.deepcopy(nodes[i]) for i in nodes if i not in has]
