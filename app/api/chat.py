import uuid
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import store
from app.services import chat_flow

router = APIRouter()


class ChatIn(BaseModel):
    session_id: Optional[str] = None
    message: Optional[str] = None


# 동기 def: FastAPI가 스레드풀에서 실행하므로 동기 NIM 호출이 이벤트 루프를 막지 않는다.
@router.post("/chat")
def chat(body: ChatIn, request: Request):
    session_id = body.session_id or str(uuid.uuid4())
    user_text = (body.message or "").strip()
    with store.session_tx(session_id, default=chat_flow.new_session) as session:
        reply = chat_flow.process_turn(session_id, session, user_text, str(request.base_url))

        payload = {"session_id": session_id, "state": session["state"], "reply": reply}
        if session["state"] == "DONE" and session.get("deploy_url"):
            payload["deploy_url"] = session["deploy_url"]
        if session.pop("design_url_unsent", False):
            # 시안 링크는 배포 링크보다 먼저 나가야 하므로 시안이 막 만들어진 응답에서 한 번만 내려준다.
            payload["design_url"] = session["design_url"]
            payload["design_preview_url"] = session.get("design_preview_url")
    return payload
