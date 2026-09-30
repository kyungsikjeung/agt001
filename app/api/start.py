"""빌더 시작·기능·공개 (BUILDER_CONTRACT §2, B1).

W2 보며 고치기(카드 미리보기·구역 편집)를 재사용한다. 카드 쪽 공통 로직
(_apply_layout·_section_label·notice 저장·바뀐 뒤 후속)은 app/api/card.py에서 꺼내 함께 쓴다.
"""
import copy
import logging
import secrets
import threading
from typing import Optional
from urllib.parse import quote as _quote

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import store
from app.api import card as card_api
from app.api import inquiries as inquiries_api
from app.security import sanitize_token
from app.services import chat_flow, design, funnel, prd_engine, rooms

router = APIRouter()
S = prd_engine.S

VARIANTS = ("v1", "v2", "v3")
_NO_STORE = {"Cache-Control": "no-store"}


class StartIn(BaseModel):
    template: str = Field(default="", max_length=64)


class FeaturesIn(BaseModel):
    key: str = Field(default="", max_length=64)
    on: bool = False
    text: Optional[str] = Field(default=None, max_length=500)


class PublishIn(BaseModel):
    force: bool = False


log = logging.getLogger(__name__)


def _render_drafts(req: str, card: dict) -> None:
    try:
        design.render_variants(req, card, log_shown=False)
    except Exception:
        log.exception("빌더 시안 파일 만들기 실패 %s", req)


def _mark_empty_required(card: dict) -> None:
    """못 정한 필수 칸을 입력 필요로 둔다. _publish가 빈칸 확인(confirm)을 묻도록."""
    ind = prd_engine.industry_of(card)
    for key in ind.required:
        slot = (card.get("slots") or {}).get(key)
        if slot is None or slot.get("status") not in (S.FILLED, S.ASSUMED):
            prd_engine._put(card, key, None, S.PLACEHOLDER, None, "builder")


def _init_layout(card: dict) -> None:
    """처음 레이아웃 (§2.4): 안마다 hero·첫 구역·inquiry만 남기고 나머지를 숨긴다."""
    from app.services import archetype as AT
    from app.services import layout_edits as LE
    try:
        blueprint = AT.blueprint(card)
    except Exception:
        blueprint = None
    if blueprint is None:
        return
    strategies = blueprint.get("strategies") if isinstance(blueprint, dict) else None
    if not isinstance(strategies, list):
        return
    edits = {}
    for pos in range(min(3, len(strategies))):
        strategy = strategies[pos] if isinstance(strategies[pos], dict) else {}
        vid = strategy.get("id") or f"v{pos + 1}"
        secs = LE.sections(blueprint, pos, None)
        if not secs:
            continue
        first = next((s["id"] for s in secs if s["id"] not in LE.LOCKED), None)
        keep = {"hero", "inquiry"} | ({first} if first else set())
        hidden = [s["id"] for s in secs if s["id"] not in keep]
        cleaned = LE.normalize({"hidden": hidden}, blueprint, pos)
        if cleaned is not None:
            edits[vid] = cleaned
    if edits:
        card["layout_edits"] = edits


def _variant_of(card: dict) -> str:
    """지금 안 (design_choice 또는 v1)."""
    choice = card.get("design_choice")
    return choice if choice in VARIANTS else "v1"


def _is_pickup(card: dict) -> bool:
    """포장 주문 청사진(A-pickup)인지. order 칩은 이때만 목록에 넣는다."""
    try:
        from app.services import archetype as AT
        arch, mode = AT.of(card)
        return arch == "A" and mode == "pickup"
    except Exception:
        return False


def _features(session: dict, card: dict, variant: str) -> list:
    """기능 칩 목록 (§2.2). 구역 칩 + 가게 칩(공지·스탬프·온라인 주문)."""
    from app.services import archetype as AT
    from app.services import layout_edits as LE
    try:
        blueprint = AT.blueprint(card)
    except Exception:
        blueprint = None
    ind = prd_engine.industry_of(card)
    offer_label = S.label_for(ind, "offerings")
    out = []
    if blueprint is not None:
        pos = VARIANTS.index(variant)
        edits = (card.get("layout_edits") or {}).get(variant)
        for s in LE.sections(blueprint, pos, edits):
            if s["id"] in ("hero", "inquiry"):  # 항상 켜짐이라 칩에서 뺀다
                continue
            node = s.get("node") or {"id": s["id"]}
            out.append({"key": f"section:{s['id']}", "label": card_api._section_label(node, offer_label),
                        "kind": "section", "on": not s["hidden"], "locked": s["locked"]})
        for node in LE.addable(blueprint, pos, edits):
            if not isinstance(node, dict) or not node.get("id"):
                continue
            out.append({"key": f"section:{node['id']}", "label": card_api._section_label(node, offer_label),
                        "kind": "section", "on": False, "locked": node["id"] in LE.LOCKED})
    req = session.get("requirement_id") or ""
    out.append({"key": "notice", "label": "공지", "kind": "shop",
                "on": bool((card.get("notice") or {}).get("text")), "needs_text": True})
    from app.services import stamps
    out.append({"key": "stamps", "label": "스탬프", "kind": "shop",
                "on": stamps.rule(req) is not None, "after_publish": True})
    if _is_pickup(card):
        from app.services import shop_settings
        out.append({"key": "order", "label": "온라인 주문", "kind": "shop",
                    "on": bool(shop_settings.get(req).get("order_on")), "after_publish": True})
    return out


def _toggle_section(card: dict, variant: str, sid: str, on: bool) -> tuple[str, bool]:
    """구역 칩 켜기·끄기 (§2.3). (구역 이름, 바뀜)을 돌린다. 모르는 id·잠긴 구역은 400."""
    from app.services import archetype as AT
    from app.services import layout_edits as LE
    if sid in LE.LOCKED:
        raise HTTPException(status_code=400, detail="잠긴 구역은 바꿀 수 없어요")
    try:
        blueprint = AT.blueprint(card)
    except Exception:
        blueprint = None
    if blueprint is None:
        raise HTTPException(status_code=400, detail="이 시안은 구역 편집이 안 돼요")
    pos = VARIANTS.index(variant)
    edits = (card.get("layout_edits") or {}).get(variant) or {}
    known = {s["id"] for s in LE.sections(blueprint, pos, edits)}
    known |= {n.get("id") for n in LE.addable(blueprint, pos, edits) if isinstance(n, dict)}
    if sid not in known:
        raise HTTPException(status_code=400, detail="없는 구역이에요")
    cur_hidden = [i for i in (edits.get("hidden") or []) if isinstance(i, str)]
    cur_added = [i for i in (edits.get("added") or []) if isinstance(i, str)]
    cur_order = [i for i in (edits.get("order") or []) if isinstance(i, str)]
    base = {s["id"] for s in LE.sections(blueprint, pos, None)}
    pool = set(LE.pool(blueprint))
    if on:
        new_hidden = [i for i in cur_hidden if i != sid]
        new_added = cur_added
        if sid in pool and sid not in base and sid not in new_added:
            new_added = [*new_added, sid]
    else:
        new_hidden = cur_hidden if sid in cur_hidden else [*cur_hidden, sid]
        new_added = cur_added
    ind = prd_engine.industry_of(card)
    node = LE.pool(blueprint).get(sid) or {"id": sid}
    label = card_api._section_label(node, S.label_for(ind, "offerings"))
    changed = card_api._apply_layout(
        card, card_api.LayoutIn(variant=variant, order=cur_order, hidden=new_hidden, added=new_added))
    return label, changed


def _classify_publish(reply: str, base_url: str, room_id: str) -> dict:
    """_publish 답 글을 빌더 응답으로 바꾼다 (_publish 동작·문구는 그대로)."""
    if "/auth/kakao/start" in (reply or ""):
        first = (reply or "").strip().split("\n", 1)[0]
        base = (base_url or "").rstrip("/")
        back = _quote(f"/start?room={room_id}", safe="")  # 로그인 뒤 빌더로
        return {"need": "login", "message": first,
                "login_urls": [f"{base}/auth/kakao/start?next={back}",
                               f"{base}/auth/google/start?next={back}"]}
    if (reply or "").startswith("공개 전에 확인해 주세요"):
        return {"need": "confirm", "message": reply}
    return {"need": "blocked", "message": reply}


@router.post("/api/start")
def post_start(body: StartIn, request: Request):
    """빌더 방 만들기 (§2.1). 시안 있음 + 1안 고름 상태로 시작한다."""
    template = (body.template or "").strip()
    if template not in S.INDUSTRIES or template == "other":
        raise HTTPException(status_code=400, detail="unknown template")
    ip = request.client.host if request.client else "unknown"
    if not inquiries_api._allow(ip):  # IP당 10분 5번 (문의 접수와 같은 규칙)
        raise HTTPException(status_code=429, detail="잠시 후 다시 시도해 주세요")
    rid = rooms.create_room(template)
    member_id = sanitize_token(secrets.token_urlsafe(16))
    base_url = str(request.base_url)
    rooms.post_message(rid, member_id, "사장님", "", base_url)  # 빈 말 = 입장, 첫 입장자가 방장
    with store.room_tx(rid) as (_room, session):
        card = session.get("prd") or prd_engine.new_card(template)
        session["prd"] = card
        card["builder"] = True
        card["design_choice"] = "v1"
        session["state"] = "DONE"
        req = session["requirement_id"]
        session["design_url"] = f"/design/{req}"
        _mark_empty_required(card)
        _init_layout(card)
        # 시안 파일(채팅방 컨셉 보드·스크린샷용)은 뒤 스레드에서: 스크린샷이 몇 초라
        # 이 요청 안에서 그리면 템플릿을 누른 사장님이 그만큼 기다린다. 미리보기는 카드를 바로 그린다.
        snapshot = copy.deepcopy(card)
        store.after_commit(lambda: threading.Thread(
            target=_render_drafts, args=(req, snapshot), daemon=True).start())
    funnel.record("builder_start", props={"industry": template})
    return JSONResponse(content={"room_id": rid, "member_id": member_id,
                                 "builder_url": f"/start?room={rid}"}, headers=_NO_STORE)


@router.get("/api/rooms/{room_id}/features")
def get_features(room_id: str, request: Request, x_member_id: Optional[str] = Header(default=None)):
    """기능 칩 목록 (§2.2). 방장만."""
    safe, member_id = card_api._member_room(room_id, x_member_id, request)
    room = store.read_room(safe)
    if rooms.owner_id(room) != member_id:
        raise HTTPException(status_code=403, detail="owner only")
    session = store.read_session(room["session_id"]) or {}
    card = session.get("prd") or {}
    variant = _variant_of(card)
    return {"variant": variant, "features": _features(session, card, variant)}


@router.put("/api/rooms/{room_id}/features")
def put_features(room_id: str, body: FeaturesIn, request: Request,
                 x_member_id: Optional[str] = Header(default=None)):
    """기능 칩 켜기·끄기 (§2.3). 방장만."""
    safe, member_id = card_api._member_room(room_id, x_member_id, request)
    with store.room_tx(safe) as (room, session):
        if rooms.owner_id(room) != member_id:
            raise HTTPException(status_code=403, detail="owner only")
        card = session.get("prd")
        if card is None:
            card = session["prd"] = prd_engine.new_card()
        variant = _variant_of(card)
        key = (body.key or "").strip()
        focus = None
        if key.startswith("section:"):
            label, changed = _toggle_section(card, variant, key[len("section:"):], bool(body.on))
            if changed:
                card_api.post_change_followup(
                    room, session, safe, ["layout"], f"빌더에서 바꿨어요: {label} {'켬' if body.on else '끔'}")
                funnel.record("builder_feature",
                              props={"kind": "section", "choice": "on" if body.on else "off"})
            if body.on:
                focus = key[len("section:"):]
        elif key == "notice":
            if body.on:
                text = (body.text or "").strip()
                if not text:
                    raise HTTPException(status_code=400, detail="공지 글을 적어 주세요")
                changed = card_api.save_notice(card, text)
            else:
                changed = card_api.save_notice(card, "")
            if changed:
                card_api.post_change_followup(
                    room, session, safe, ["notice"], f"빌더에서 바꿨어요: 공지 {'켬' if body.on else '끔'}")
                funnel.record("builder_feature",
                              props={"kind": "notice", "choice": "on" if body.on else "off"})
        elif key in ("stamps", "order"):
            raise HTTPException(status_code=400, detail="공개한 뒤 사장님 화면에서 켤 수 있어요")
        else:
            raise HTTPException(status_code=400, detail="없는 기능이에요")
        return {"features": _features(session, card, variant), "focus": focus}


@router.post("/api/rooms/{room_id}/publish")
def post_publish(room_id: str, body: PublishIn, request: Request,
                 x_member_id: Optional[str] = Header(default=None)):
    """빌더 공개하기 (§2.5). 채팅의 _publish를 그대로 탄다. 방장만."""
    safe, member_id = card_api._member_room(room_id, x_member_id, request)
    base_url = str(request.base_url)
    with store.room_tx(safe) as (room, session):
        if rooms.owner_id(room) != member_id:
            raise HTTPException(status_code=403, detail="owner only")
        reply = chat_flow._publish(session, base_url, bool(body.force))
        card = session.get("prd") or {}
        rooms._append(room, "system", "시스템", reply, kind="system")
        if card.get("published"):
            return {"ok": True, "site_url": session.get("deploy_url")}
        return _classify_publish(reply, base_url, safe)
