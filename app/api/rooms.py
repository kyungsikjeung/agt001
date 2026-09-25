from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.services import rooms

router = APIRouter()


class RoomMessageIn(BaseModel):
    member_id: Optional[str] = None
    nickname: Optional[str] = None
    message: Optional[str] = None


@router.post("/room")
def create_room():
    return {"room_id": rooms.create_room()}


@router.post("/room/{room_id}/chat")
def room_chat(room_id: str, body: RoomMessageIn, request: Request):
    try:
        return rooms.post_message(room_id, body.member_id, body.nickname, body.message, str(request.base_url))
    except rooms.RoomNotFound:
        raise HTTPException(status_code=404, detail="room not found")
    except rooms.InvalidRequest as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/room/{room_id}/messages")
def room_messages(room_id: str, request: Request, since: int = 0,
                  x_member_id: Optional[str] = Header(default=None)):
    # 본인 확인 값은 URL이 아니라 헤더로 받는다 (접근 로그에 남지 않게).
    try:
        return rooms.get_messages(room_id, max(since, 0), str(request.base_url), x_member_id)
    except rooms.RoomNotFound:
        raise HTTPException(status_code=404, detail="room not found")
