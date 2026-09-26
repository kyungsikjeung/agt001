"""직접 편집 (contracts/ROOM_FEATURES_API.md §5, D27: 내용은 직접, 구조는 채팅)."""
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app import store
from app.security import sanitize_token
from app.services import design, prd_engine, rooms

router = APIRouter()
S = prd_engine.S

EDITABLE = ("shop_name", "phone", "hours", "location", "price", "offerings", "detail", "target", "contact_method")


class CardIn(BaseModel):
    fields: dict[str, str] = {}


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
    return {
        "title": DV.title_for(card) if card.get("slots") else "새 프로젝트", "industry": ind.name,
        "fields": fields, "photos": card.get("photos") or [], "choice": card.get("design_choice"),
        "published": card.get("published"), "site_url": session.get("deploy_url") if card.get("published") else None,
        "can_edit": rooms.owner_id(room) == member_id,
    }


def _member_room(room_id: str, x_member_id: Optional[str]):
    safe = sanitize_token(room_id or "")
    member_id = sanitize_token(x_member_id or "")
    room = store.read_room(safe) if safe else None
    if room is None or not any(m["member_id"] == member_id for m in room["members"]):
        raise HTTPException(status_code=404, detail="room not found")
    return safe, member_id


@router.get("/api/rooms/{room_id}/card")
def get_card(room_id: str, x_member_id: Optional[str] = Header(default=None)):
    safe, member_id = _member_room(room_id, x_member_id)
    room = store.read_room(safe)
    return _view(room, store.read_session(room["session_id"]) or {}, member_id)


@router.put("/api/rooms/{room_id}/card")
def put_card(room_id: str, body: CardIn, request: Request, x_member_id: Optional[str] = Header(default=None)):
    safe, member_id = _member_room(room_id, x_member_id)
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
        if changed and card.get("published"):
            from app.services.publish_check import PublishBlockedError
            try:
                design.publish_choice(session["requirement_id"], card, card["published"])
            except PublishBlockedError as e:
                raise HTTPException(status_code=400, detail="; ".join(e.reasons))
        if changed:
            ind = prd_engine.industry_of(card)
            labels = ", ".join(S.label_for(ind, k) for k in changed)
            rooms._append(room, "system", "시스템", f"직접 편집으로 고쳤어요: {labels}", kind="system")
        return _view(room, session, member_id)


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
    kakao_talk.forget(me["id"])
    return Response(status_code=204)
