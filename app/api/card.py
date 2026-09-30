"""직접 편집 (contracts/ROOM_FEATURES_API.md §5, D27: 내용은 직접, 구조는 채팅)."""
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app import store
from app.api.auth import _check_origin
from app.security import sanitize_token
from app.services import design, prd_engine, rooms

router = APIRouter()
S = prd_engine.S

EDITABLE = ("shop_name", "phone", "hours", "location", "price", "offerings", "detail", "target", "contact_method")

# 미리보기 안 id (EDIT_WAVE2_CONTRACT §2.1)
VARIANTS = ("v1", "v2", "v3")


class NoticeIn(BaseModel):
    text: str = ""
    popup: bool = False


class ItemIn(BaseModel):
    """항목 한 줄 (메뉴·반·객실·시술, EDIT_WAVE2_CONTRACT §2.2)."""
    name: str = Field(default="", max_length=30)
    rename: Optional[str] = Field(default=None, max_length=30)
    price: Optional[str] = Field(default=None, max_length=20)
    note: Optional[str] = Field(default=None, max_length=80)
    remove: bool = False
    add: bool = False


class LayoutIn(BaseModel):
    """구역 편집 (안별, EDIT_WAVE2_CONTRACT §2.2)."""
    variant: str = "v1"
    order: list[str] = Field(default=[], max_length=30)
    hidden: list[str] = Field(default=[], max_length=30)
    added: list[str] = Field(default=[], max_length=30)
    reset: bool = False


class CardIn(BaseModel):
    fields: dict[str, str] = {}
    notice: Optional[NoticeIn] = None  # 공지 띠·팝업 (D56). 빈 글이면 공지를 끈다
    items: list[ItemIn] = Field(default=[], max_length=30)  # 한 요청에 최대 30줄
    layout: Optional[LayoutIn] = None
    choice: Optional[Literal["v1", "v2", "v3"]] = None  # 빌더 모양 바꾸기 (B1)


def _view(room: dict, session: dict, member_id: str) -> dict:
    card = session.get("prd") or prd_engine.new_card()
    ind = prd_engine.industry_of(card)
    fields = []
    for key in EDITABLE:
        slot = card["slots"].get(key) or {}
        value = slot.get("value")
        fields.append({
            "key": key, "label": S.label_for(ind, key),
            "value": ", ".join(value) if isinstance(value, list) else (value or ""),
            "status": slot.get("status", S.EMPTY), "fact": S.SLOTS[key].fact,
            "placeholder": slot.get("status") in (S.PLACEHOLDER, S.EMPTY, None),
        })
    from app.services import design_variants as DV
    try:
        from app.services import photo_needs
        photo_tags = photo_needs.photo_tags(card)
    except Exception:
        photo_tags = []
    return {
        "title": DV.title_for(card) if card.get("slots") else "새 프로젝트", "industry": ind.name,
        "fields": fields, "photos": card.get("photos") or [], "photo_tags": photo_tags,
        "choice": card.get("design_choice"),
        "notice": card.get("notice") or {"text": "", "popup": False},
        "layout": card.get("layout_edits") or {},
        "published": card.get("published"), "site_url": session.get("deploy_url") if card.get("published") else None,
        "can_edit": rooms.owner_id(room) == member_id,
    }


def _section_label(node: dict, offerings_label: str) -> str:
    """미리보기 구역 이름. 청사진 label → nav → design._section_name → id."""
    if isinstance(node, dict) and node.get("id") == "hero":
        return "첫 화면"
    # 청사진 이름(사이트에 보이는 제목)이 먼저: 종류 이름만 쓰면 메뉴·시그니처가 둘 다 '대표 메뉴'로 겹친다
    for key in ("label", "nav"):
        value = node.get(key) if isinstance(node, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    from app.services import design as D
    try:
        name = D._section_name(node, offerings_label) if isinstance(node, dict) else ""
        if isinstance(name, str) and name.strip():
            return name
    except Exception:
        pass
    return node.get("id", "") if isinstance(node, dict) else ""


def _apply_items(card: dict, items: list, turn) -> bool:
    """항목 고치기 (§2.2). 바뀐 게 있으면 True. 마지막 1개 빼기는 400."""
    slot = (card.get("slots") or {}).get("offerings") or {}
    raw = slot.get("value")
    names = [v for v in raw if isinstance(v, str) and v] if isinstance(raw, list) else []
    pairs = card.setdefault("price_pairs", {})
    if not isinstance(pairs, dict):
        pairs = card["price_pairs"] = {}
    notes = card.setdefault("item_notes", {})
    if not isinstance(notes, dict):
        notes = card["item_notes"] = {}
    dirty = False
    listed = False

    def _set(key: dict, name: str, text: str) -> None:
        nonlocal dirty
        old = key.get(name) or ""
        if text != old:
            if text:
                key[name] = text
            else:
                key.pop(name, None)
            dirty = True

    for line in items or []:
        name = (line.name or "").strip()
        if not name:
            continue
        if line.add:
            if name in names or len(names) >= 20:
                continue
            names.append(name)
            listed = True
            if line.price is not None:
                _set(pairs, name, (line.price or "").strip())
            if line.note is not None:
                _set(notes, name, (line.note or "").strip())
            continue
        if line.remove:
            if name not in names:
                continue
            if len(names) <= 1:
                raise HTTPException(status_code=400, detail="마지막 항목은 뺄 수 없어요")
            names.remove(name)
            pairs.pop(name, None)
            notes.pop(name, None)
            listed = True
            dirty = True
            continue
        if name not in names:
            continue
        target = name
        new = (line.rename or "").strip()
        if new and new != name and new not in names:
            names[names.index(name)] = new
            for key in (pairs, notes):
                if name in key:
                    key[new] = key.pop(name)
            for photo in card.get("photos") or []:
                if isinstance(photo, dict) and photo.get("tag") == "item:" + name:
                    photo["tag"] = "item:" + new
            target = new
            listed = True
            dirty = True
        if line.price is not None:
            _set(pairs, target, (line.price or "").strip())
        if line.note is not None:
            _set(notes, target, (line.note or "").strip())
    if listed:
        prd_engine._put(card, "offerings", names, S.FILLED, turn, "editor")
        dirty = True
    return dirty


def _apply_layout(card: dict, layout: LayoutIn) -> bool:
    """구역 고치기 (안별, §2.2). 바뀌면 True, 그대로면 False. 안 id가 이상하면 400."""
    variant = (layout.variant or "").strip()
    if variant not in VARIANTS:
        raise HTTPException(status_code=400, detail="unknown variant")
    current = card.get("layout_edits") or {}
    if layout.reset:
        if variant in current:
            current.pop(variant)
            if not current:
                card.pop("layout_edits", None)
            return True
        return False
    from app.services import archetype as AT
    from app.services import layout_edits as LE
    try:
        blueprint = AT.blueprint(card)
    except Exception:
        blueprint = None
    if blueprint is None:
        return False  # 청사진 없는 옛 경로는 편집 무시
    pos = VARIANTS.index(variant)
    cleaned = LE.normalize(
        {"order": list(layout.order or []), "hidden": list(layout.hidden or []),
         "added": list(layout.added or [])}, blueprint, pos)
    if cleaned == current.get(variant):
        return False
    edits = card.setdefault("layout_edits", {})
    if cleaned is None:
        edits.pop(variant, None)
        if not edits:
            card.pop("layout_edits", None)
    else:
        edits[variant] = cleaned
    return True


def _member_room(room_id: str, x_member_id: Optional[str], request: Optional[Request] = None):
    from sqlalchemy import select

    safe = sanitize_token(room_id or "")
    member_id = sanitize_token(x_member_id or "")
    room = store.read_room(safe) if safe else None
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    if any(m["member_id"] == member_id for m in room["members"]):
        return safe, member_id
    # 다른 기기: 로그인한 방장은 계정에 붙은 본인 확인 값으로 본다.
    if request is not None:
        from app.db.models import UserRoomRow
        from app.db.session import get_sessionmaker
        from app.services import auth
        user = auth.user_for_session(request.cookies.get(auth.SESSION_COOKIE))
        if user is not None:
            if request.method not in ("GET", "HEAD"):
                _check_origin(request)  # 쿠키로 바꾸는 요청은 우리 출처만 (보안 S-3)
            with get_sessionmaker()() as db:
                row_mid = db.scalar(select(UserRoomRow.member_id).where(
                    UserRoomRow.room_id == safe, UserRoomRow.user_id == user["id"]))
            if row_mid:
                return safe, row_mid
    raise HTTPException(status_code=404, detail="room not found")


@router.get("/api/rooms/{room_id}/card")
def get_card(room_id: str, request: Request, x_member_id: Optional[str] = Header(default=None)):
    safe, member_id = _member_room(room_id, x_member_id, request)
    room = store.read_room(safe)
    return _view(room, store.read_session(room["session_id"]) or {}, member_id)


@router.put("/api/rooms/{room_id}/card")
def put_card(room_id: str, body: CardIn, request: Request, x_member_id: Optional[str] = Header(default=None)):
    safe, member_id = _member_room(room_id, x_member_id, request)
    with store.room_tx(safe) as (room, session):
        if rooms.owner_id(room) != member_id:
            raise HTTPException(status_code=403, detail="owner only")
        card = session.get("prd")
        if card is None:
            card = session["prd"] = prd_engine.new_card()
        turn = card.get("turn", 0)
        changed = []
        for key, raw in (body.fields or {}).items():
            if key not in EDITABLE:
                continue
            value = str(raw or "").strip()[:200]
            if not value:
                # 빈 값은 "입력 필요"로 되돌린다(D23: 공개 전 채워야 하는 자리 표시)
                prd_engine._put(card, key, None, S.PLACEHOLDER, turn, "editor")
            elif S.SLOTS[key].multi:
                prd_engine._put(card, key, [v.strip() for v in value.split(",") if v.strip()], S.FILLED, turn, "editor")
            else:
                if key == "phone":
                    value = prd_engine._spoken_phone(value)
                prd_engine._put(card, key, value, S.FILLED, turn, "editor")
            changed.append(key)
        if body.notice is not None:
            if save_notice(card, body.notice.text, body.notice.popup):
                changed.append("notice")
        if body.items:
            if _apply_items(card, body.items, turn):
                changed.append("items")
        if body.layout is not None:
            if _apply_layout(card, body.layout):
                changed.append("layout")
        if body.choice is not None:
            if card.get("design_choice") != body.choice:
                card["design_choice"] = body.choice
                changed.append("choice")
        if changed:
            ind = prd_engine.industry_of(card)
            labels = ", ".join(_changed_label(ind, k) for k in changed)
            post_change_followup(room, session, safe, changed, f"직접 편집으로 고쳤어요: {labels}")
        return _view(room, session, member_id)


def _changed_label(ind, key: str) -> str:
    """바뀐 칸 이름 (items → 상품 칸 이름, layout → 구역, choice → 모양)."""
    if key == "notice":
        return "공지"
    if key == "layout":
        return "구역"
    if key == "choice":
        return "모양"
    if key == "items":
        return S.label_for(ind, "offerings")
    return S.label_for(ind, key)


def save_notice(card: dict, text: str, popup: bool = False) -> bool:
    """공지 저장 (W2 PUT /card와 빌더 PUT /features가 함께 쓴다). 바뀌면 True."""
    clean = (text or "").strip()[:200]
    new = {"text": clean, "popup": bool(popup and clean)} if clean else None
    if new != card.get("notice"):
        if new:
            card["notice"] = new
        else:
            card.pop("notice", None)
        return True
    return False


def post_change_followup(room: dict, session: dict, safe: str, changed: list, message: str) -> None:
    """바뀐 뒤 후속 (W2 PUT /card와 빌더 PUT /features가 함께 쓴다).

    공개본이 있으면 다시 공개하고, 없으면 시안 파일 뒤에서 갱신한 뒤 시스템 메시지 한 줄."""
    card = session.get("prd") or {}
    if changed and card.get("published"):
        from app.services.publish_check import PublishBlockedError
        try:
            design.publish_choice(session["requirement_id"], card, card["published"])
        except PublishBlockedError as e:
            raise HTTPException(status_code=400, detail="; ".join(e.reasons))
    elif changed and session.get("design_url"):
        # 공개 전 직접 고치기도 시안 그림에 넣는다 (EDIT_PUBLISH_PLAN §4-5, 전엔 카드만 바뀌었다)
        from app.services import photos
        rid, req = safe, session["requirement_id"]
        store.after_commit(lambda: photos._refresh_designs_async(rid, req, "고친 내용을 시안에 넣었어요."))
    if changed:
        rooms._append(room, "system", "시스템", message, kind="system")


@router.get("/api/rooms/{room_id}/card/preview")
def preview_card(room_id: str, request: Request, x_member_id: Optional[str] = Header(default=None),
                 variant: Optional[str] = None):
    """보며 고치기 미리보기 (§2.1). 방장만, 시안 전이면 409. 지금 카드로 바로 그린다."""
    from fastapi.responses import JSONResponse

    safe, member_id = _member_room(room_id, x_member_id, request)
    room = store.read_room(safe)
    if rooms.owner_id(room) != member_id:
        raise HTTPException(status_code=403, detail="owner only")
    session = store.read_session(room["session_id"]) or {}
    card = session.get("prd")
    if card is None or not session.get("design_url"):
        raise HTTPException(status_code=409, detail="no design yet")
    vid = variant if variant in VARIANTS else None
    if vid is None:
        choice = card.get("design_choice")
        vid = choice if choice in VARIANTS else "v1"
    from app.services import archetype as AT
    from app.services import design_variants as DV
    from app.services import layout_edits as LE
    from app.services import site_render as SR
    found = DV.pick(card, vid)
    if found is None:
        raise HTTPException(status_code=409, detail="no design yet")
    page = SR.render_site(found["spec"], site_key=session.get("requirement_id") or "",
                          title=DV.title_for(card), kind=DV.kind_for(card), edit=True)
    try:
        blueprint = AT.blueprint(card)
    except Exception:
        blueprint = None
    edits = (card.get("layout_edits") or {}).get(vid) or {}
    raw = ((card.get("slots") or {}).get("offerings") or {}).get("value")
    pairs, notes = card.get("price_pairs") or {}, card.get("item_notes") or {}
    # 편집기가 지금 값에서 시작하게: 항목 가격·설명과 이 안의 구역 편집(더한 구역이 다음 저장에서 빠지지 않게)
    items = [{"name": n, "price": pairs.get(n) or "", "note": notes.get(n) or ""}
             for n in (raw if isinstance(raw, list) else []) if isinstance(n, str) and n]
    if blueprint is None:
        sections, addable = [], []
    else:
        pos = VARIANTS.index(vid)
        ind = prd_engine.industry_of(card)
        offer_label = S.label_for(ind, "offerings")
        sections = [{"id": s["id"], "label": _section_label(s.get("node") or {"id": s["id"]}, offer_label),
                     "bind": s.get("bind", "none"), "locked": s["locked"], "hidden": s["hidden"]}
                    for s in LE.sections(blueprint, pos, edits)]
        addable = [{"id": n.get("id"), "label": _section_label(n, offer_label),
                    "bind": n.get("bind", "none")}
                   for n in LE.addable(blueprint, pos, edits) if isinstance(n, dict)]
    return JSONResponse(content={"variant": vid, "html": page, "sections": sections, "addable": addable,
                                 "layout": edits, "items": items},
                        headers={"Cache-Control": "no-store"})


@router.get("/api/rooms/{room_id}/notify")
def notify_state(room_id: str, request: Request, x_member_id: Optional[str] = Header(default=None)):
    from app.services import auth, kakao_talk
    safe, _member = _member_room(room_id, x_member_id)
    me = auth.user_for_session(request.cookies.get(auth.SESSION_COOKIE))
    owner_uid = kakao_talk.owner_user_id(safe)
    return {"kakao": {"linked": bool(me and kakao_talk.is_linked(me["id"])),
                      "owner_linked": bool(owner_uid and kakao_talk.is_linked(owner_uid))}}


@router.delete("/api/me/notify/kakao", status_code=204)
def notify_off(request: Request):
    from fastapi import Response
    from app.services import auth, kakao_talk
    me = auth.user_for_session(request.cookies.get(auth.SESSION_COOKIE))
    if me is None:
        raise HTTPException(status_code=401)
    _check_origin(request)
    kakao_talk.forget(me["id"])
    return Response(status_code=204)
