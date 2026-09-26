from typing import Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel

from app.services import photos, rooms

router = APIRouter()


class RoomMessageIn(BaseModel):
    member_id: Optional[str] = None
    nickname: Optional[str] = None
    message: Optional[str] = None
    invite: Optional[str] = None  # 처음 들어오는 사람만 (contracts/ROOM_FEATURES_API.md §3)


class OwnerIn(BaseModel):
    to: str


class InviteIn(BaseModel):
    days: int = 7


class RoomCreateIn(BaseModel):
    template_id: Optional[str] = None


@router.post("/room")
def create_room(body: Optional[RoomCreateIn] = None):
    # 본문 없이 불러도 된다(예전 방식). 템플릿을 넘기면 그 업종 카드로 시작한다(B-15).
    return {"room_id": rooms.create_room(body.template_id if body else None)}


@router.post("/room/{room_id}/chat")
def room_chat(room_id: str, body: RoomMessageIn, request: Request):
    try:
        return rooms.post_message(room_id, body.member_id, body.nickname, body.message, str(request.base_url),
                                  invite_raw=body.invite)
    except rooms.InviteRequired:
        raise HTTPException(status_code=403, detail="invite required")
    except rooms.InviteInvalid:
        raise HTTPException(status_code=403, detail="invite invalid")
    except rooms.RoomNotFound:
        raise HTTPException(status_code=404, detail="room not found")
    except rooms.InvalidRequest as e:
        raise HTTPException(status_code=400, detail=str(e))
    except rooms.RoomFull:
        raise HTTPException(status_code=403, detail="room full")  # D8: 10명
    except rooms.RoomClosed:
        raise HTTPException(status_code=423, detail="room closed")  # T4: 방장만 다시 열 수 있다


@router.get("/room/{room_id}/messages")
def room_messages(room_id: str, request: Request, since: int = 0,
                  x_member_id: Optional[str] = Header(default=None)):
    # 본인 확인 값은 URL이 아니라 헤더로 받는다 (접근 로그에 남지 않게).
    try:
        return rooms.get_messages(room_id, max(since, 0), str(request.base_url), x_member_id)
    except rooms.RoomNotFound:
        raise HTTPException(status_code=404, detail="room not found")


def _guard(fn):
    """방장·참여자 확인 오류를 HTTP로."""
    try:
        return fn()
    except rooms.RoomNotFound:
        raise HTTPException(status_code=404, detail="room not found")
    except rooms.NotOwner:
        raise HTTPException(status_code=403, detail="owner only")
    except rooms.InvalidRequest as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/room/{room_id}/owner")
def room_owner(room_id: str, body: OwnerIn, x_member_id: Optional[str] = Header(default=None)):
    return {"owner": _guard(lambda: rooms.transfer_owner(room_id, x_member_id, body.to))}


@router.post("/room/{room_id}/leave", status_code=204)
def room_leave(room_id: str, x_member_id: Optional[str] = Header(default=None)):
    _guard(lambda: rooms.leave(room_id, x_member_id))
    return Response(status_code=204)


@router.post("/room/{room_id}/invites", status_code=201)
def room_invite_create(room_id: str, body: InviteIn, x_member_id: Optional[str] = Header(default=None)):
    return _guard(lambda: rooms.create_invite(room_id, x_member_id, body.days))


@router.get("/room/{room_id}/invites")
def room_invite_list(room_id: str, x_member_id: Optional[str] = Header(default=None)):
    return {"invites": _guard(lambda: rooms.list_invites(room_id, x_member_id))}


@router.delete("/room/{room_id}/invites/{invite_id}", status_code=204)
def room_invite_revoke(room_id: str, invite_id: str, x_member_id: Optional[str] = Header(default=None)):
    _guard(lambda: rooms.revoke_invite(room_id, x_member_id, invite_id))
    return Response(status_code=204)


@router.post("/room/{room_id}/photos", status_code=201)
async def room_photo_upload(room_id: str, file: UploadFile = File(...), caption: Optional[str] = Form(default=None),
                            x_member_id: Optional[str] = Header(default=None)):
    data = await file.read(photos.MAX_BYTES + 1)
    try:
        return _guard(lambda: photos.add(room_id, x_member_id, data, caption))
    except photos.PhotoError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/room/{room_id}/photos/{photo_id}", status_code=204)
def room_photo_delete(room_id: str, photo_id: str, x_member_id: Optional[str] = Header(default=None)):
    _guard(lambda: photos.remove(room_id, x_member_id, photo_id))
    return Response(status_code=204)
