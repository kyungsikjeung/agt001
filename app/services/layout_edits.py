"""구역 순서·숨기기·추가 편집 (EDIT_WAVE2_CONTRACT §3.1).

순수 함수만 둔다. DB·파일 접근 없음.
"""
import copy

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


def normalize(edits: dict | None, blueprint: dict, pos: int) -> dict | None:
    """{order, hidden, added}를 이 청사진·안 기준으로 정리. 아무 효과 없으면 None."""
    if not isinstance(edits, dict):
        return None
    base = _base_ids(blueprint, pos)
    if not base:
        return None
    base_set = set(base)
    pool_ids = set(pool(blueprint))

    # added: pool에 있고 이 안에 없는 id만, 최대 3
    added = [i for i in _str_list(edits.get("added")) if i in pool_ids and i not in base_set][:MAX_ADDED]

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

    if not added and not hidden and order == effective:
        return None
    return {"order": order, "hidden": hidden, "added": added}


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
    ordered = []
    for sid in cleaned["order"]:
        if sid in hidden:
            continue
        sec = by_id.get(sid)
        if sec is not None:
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
    out = []
    for sid in order:
        if sid == "hero":
            node = {"id": "hero", "bind": "hero"}
            bind = "hero"
        else:
            node = nodes.get(sid) or {}
            bind = node.get("bind", "none") if isinstance(node, dict) else "none"
        out.append({"id": sid, "bind": bind, "locked": sid in LOCKED,
                    "hidden": sid in hidden, "node": copy.deepcopy(node) if isinstance(node, dict) else {}})
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
