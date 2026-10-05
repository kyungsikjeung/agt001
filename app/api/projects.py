"""내 프로젝트 목록 (ROOM_POLICY.md §3.2). 로그인 전에는 이 기기에서 들어간 방 목록으로 동작한다.

브라우저가 기억한 방 ID와 본인 확인 값(X-Member-Id)을 보내면, 그 사람이 실제 참여자인 방만 요약해 돌려준다.
참여자가 아닌 방은 조용히 빠진다(방이 있는지도 알려주지 않음).
로그인하면 계정에 옮긴 방(user_rooms, 다른 기기에서 연 방 포함)도 함께 보여준다.
"""
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app import store
from app.security import sanitize_token
from app.services import auth, prd_schema, project_delete, rooms as rooms_svc

router = APIRouter()

MAX_ROOMS = 50

STATE_LABELS = {
    "GREETING": "시작 전",
    "GATHERING": "요구사항 정리 중",
    "AWAIT_APPROVAL": "확인 대기",
    "QUOTED": "견적 확인",
    "GENERATING": "제작 중",
    "DONE": "완료",
}


class ProjectsIn(BaseModel):
    room_ids: list[str] = []


def _title(session: dict) -> str:
    slots = ((session.get("prd") or {}).get("slots") or {})
    name = (slots.get("shop_name") or {}).get("value")
    kind = (slots.get("business_type") or {}).get("value")
    if name:
        return name
    if kind:
        return f"{kind} 사이트"
    return "새 프로젝트"


@router.post("/api/projects/summary")
def projects_summary(body: ProjectsIn, request: Request, x_member_id: Optional[str] = Header(default=None)):
    member_id = sanitize_token(x_member_id or "")
    user = auth.user_for_session(request.cookies.get(auth.SESSION_COOKIE))
    if not member_id and user is None:
        raise HTTPException(status_code=400, detail="member required")
    # (방 ID, 그 방에서의 본인 확인 값): 이 기기의 방 + 계정에 옮긴 방
    pairs = [(sanitize_token(raw), member_id) for raw in body.room_ids[:MAX_ROOMS]] if member_id else []
    if user is not None:
        pairs += auth.rooms_for_user(user["id"])[:MAX_ROOMS]
    out = []
    seen = set()
    for room_id, mid in pairs:
        if not room_id or not mid or room_id in seen:
            continue
        room = store.read_room(room_id)
        if room is None or not any(m["member_id"] == mid for m in room["members"]):
            continue
        seen.add(room_id)
        session = store.read_session(room["session_id"]) or {}
        prd = session.get("prd") or {}
        industry = prd_schema.INDUSTRIES.get(prd.get("industry") or "")
        messages = store.read_messages(room_id, 0)
        last = messages[-1] if messages else None
        deleted = project_delete.deleted_at(room_id)
        out.append({
            "room_id": room_id,
            "title": _title(session),
            "industry": industry.name if industry else None,
            "state": session.get("state"),
            "state_label": STATE_LABELS.get(session.get("state"), "진행 중"),
            "created_at": room.get("created_at"),
            "updated_at": last["ts"] if last else room.get("created_at"),
            "last_message": (last["text"][:80] if last else None),
            "members": len(room["members"]),
            "deploy_url": session.get("deploy_url"),
            "design_url": session.get("design_url"),
            # 지운 프로젝트는 목록에 비활성으로 남는다(대표 10/5). 30일 뒤 영구 삭제(방침 3항).
            "deleted_at": deleted.isoformat() if deleted else None,
            "purge_at": project_delete.purge_at(deleted).isoformat() if deleted else None,
            "is_owner": rooms_svc.owner_id(room) == mid,
        })
    out.sort(key=lambda p: p["updated_at"] or "", reverse=True)
    return {"projects": out}


def _owner_room(room_id: str, member_id_raw, request: Request) -> tuple:
    """방장만 지우고 되살릴 수 있다. 참여자가 아니면 방이 있는지도 알려주지 않는다(404)."""
    safe = sanitize_token(room_id or "")
    member_id = sanitize_token(member_id_raw or "")
    room = store.read_room(safe) if safe else None
    if room is None:
        raise HTTPException(status_code=404, detail="없는 프로젝트예요")
    if not member_id:
        # 다른 기기에서 로그인했으면 계정에 옮긴 방의 본인 확인 값을 쓴다.
        user = auth.user_for_session(request.cookies.get(auth.SESSION_COOKIE))
        if user is not None:
            member_id = dict(auth.rooms_for_user(user["id"])).get(safe, "")
    if not member_id or not any(m["member_id"] == member_id for m in room["members"]):
        raise HTTPException(status_code=404, detail="없는 프로젝트예요")
    if rooms_svc.owner_id(room) != member_id:
        raise HTTPException(status_code=403, detail="방장만 지울 수 있어요")
    return safe, room


@router.post("/api/projects/{room_id}/delete")
def delete_project(room_id: str, request: Request, x_member_id: Optional[str] = Header(default=None)):
    """프로젝트 지우기 (대표 10/5). 공개 사이트·주문·결제가 바로 닫히고 구독도 해지된다. 30일 뒤 영구 삭제."""
    safe, _room = _owner_room(room_id, x_member_id, request)
    when = project_delete.soft_delete(safe)
    return {"deleted_at": when.isoformat(), "purge_at": project_delete.purge_at(when).isoformat(),
            "grace_days": project_delete.GRACE_DAYS}


@router.post("/api/projects/{room_id}/restore")
def restore_project(room_id: str, request: Request, x_member_id: Optional[str] = Header(default=None)):
    """되살리기. 30일이 지나 영구 삭제됐으면 방이 없으므로 404. 구독은 되살아나지 않는다."""
    safe, _room = _owner_room(room_id, x_member_id, request)
    project_delete.restore(safe)
    return {"deleted_at": None}
