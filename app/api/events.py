from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services import funnel

router = APIRouter()


class EventIn(BaseModel):
    event: str
    visitor_id: Optional[str] = None
    session_id: Optional[str] = None
    source: Optional[str] = None
    campaign: Optional[str] = None
    template_id: Optional[str] = None


@router.post("/events", status_code=204)
def post_event(body: EventIn, request: Request):
    # 브라우저 단계 기록. 서버 단계(요구사항 확정, 제작)는 chat_flow가 직접 남긴다.
    client_key = request.client.host if request.client else "unknown"
    if not funnel.allow(client_key):
        raise HTTPException(status_code=429, detail="too many events")
    if body.event not in funnel.CLIENT_EVENTS:
        raise HTTPException(status_code=400, detail="unknown event")
    funnel.record(body.event, visitor_id=body.visitor_id, session_id=body.session_id,
                  source=body.source, campaign=body.campaign, template_id=body.template_id)
