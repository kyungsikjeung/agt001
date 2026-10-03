"""관리자 읽기 API (ADMIN_CONTRACT §2): 가게 목록·가게 상세·대화 문제 신호·지표.

모든 경로는 관리자만(require_admin)이고 응답은 저장 금지(no-store)다. 본 것은 기록한다(viewed).
내보내는 글은 전화·주소·이메일을 가린다(mask_pii): 카드 값, 채팅, 대화 턴과 엔진 판단(meta), 대화 지표.
"""
import datetime
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.auth import _check_origin

from app.db.models import (
    BookingRow,
    ChatTurnRow,
    FunnelEventRow,
    InquiryRow,
    RoomMessageRow,
    RoomRow,
    SessionRow,
    UserRoomRow,
)
from app.db.session import get_sessionmaker
from app.services import admin, prd_engine, takedown
from app.services import rooms as rooms_svc
from evals import live_metrics as M

router = APIRouter()

# 대화 문제 신호 기준 (ADMIN_CONTRACT §2-3)
STUCK_TURNS = 12
EXTRACT_MIN_TOTAL = 3
EXTRACT_FAIL_RATE = 0.3
SLOW_P50_MS = 8000
ENGLISH_RE = re.compile(r"[A-Za-z]{2,}(?: +[A-Za-z]{2,}){2,}")  # 영문 낱말 3개 이상 연속(R1 감시)

PAGE_MAX = 200
DETAIL_MAX = 200
SIGNAL_SESSIONS_MAX = 200


def _admin(request: Request, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return admin.require_admin(request)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(ts):
    return ts.isoformat() if ts else None


def _mask(value):
    """글·목록·dict 안의 글을 모두 가린다(엔진 판단 meta, 지표의 missed처럼 원문이 든 칸까지)."""
    if isinstance(value, dict):
        return {k: _mask(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask(v) for v in value]
    return M.mask_pii(value) if isinstance(value, str) else value


def _shop_name(card: dict) -> str:
    value = (((card or {}).get("slots") or {}).get("shop_name") or {}).get("value")
    return value.strip() if isinstance(value, str) else ""


def _industry(card: dict) -> str:
    try:
        return prd_engine.industry_of(card).key
    except Exception:
        return ""


def _turn_dicts(rows) -> list:
    return [{"user_text": r.user_text or "", "ai_text": r.ai_text or "", "state_before": r.state_before or "",
             "state_after": r.state_after or "", "meta": r.meta, "ts": r.ts} for r in rows]


def flags(metrics: dict, turns: list) -> list:
    """대화 문제 신호 (§2-3)."""
    out = []
    if metrics["n_turns"] >= STUCK_TURNS and not metrics["reached_summary"]:
        out.append("stuck")
    rate = metrics.get("extract_fail_rate")
    if (metrics.get("extract_total") or 0) >= EXTRACT_MIN_TOTAL and rate is not None and rate >= EXTRACT_FAIL_RATE:
        out.append("extract_fail")
    p50 = metrics.get("extract_p50_ms")
    if p50 is not None and p50 >= SLOW_P50_MS:
        out.append("slow")
    if metrics.get("repeat_count"):
        out.append("repeat")
    if any(ENGLISH_RE.search(t.get("ai_text") or "") for t in turns):
        out.append("english")
    return out


def _turns_by_session(session_ids: list, since=None) -> dict:
    """세션별 대화 턴(시간순 dict 목록)."""
    if not session_ids:
        return {}
    q = select(ChatTurnRow).where(ChatTurnRow.session_id.in_(session_ids))
    if since is not None:
        q = q.where(ChatTurnRow.ts >= since)
    out: dict = {}
    with get_sessionmaker()() as db:
        for r in db.scalars(q.order_by(ChatTurnRow.session_id, ChatTurnRow.id)).all():
            out.setdefault(r.session_id, []).append(r)
        return {sid: _turn_dicts(rows) for sid, rows in out.items()}


def _counts(model, site_keys: list) -> dict:
    if not site_keys:
        return {}
    with get_sessionmaker()() as db:
        return dict(db.execute(select(model.site_key, func.count()).where(model.site_key.in_(site_keys))
                               .group_by(model.site_key)).all())


def _item(room_id, created, session_id, state, site_key, card: dict) -> dict:
    """목록 한 줄의 가벼운 값 (카드만 본다)."""
    return {"room_id": room_id, "session_id": session_id, "site_key": site_key or "", "created_at": _iso(created),
            "shop_name": M.mask_pii(_shop_name(card)), "industry": _industry(card), "state": state or "",
            "published": bool(card.get("published")), "taken_down": takedown.info(site_key) if site_key else None}


def _fill(items: list) -> None:
    """보이는 줄에만 무거운 값을 채운다: 대화 수·문제 신호·문의·예약·사장님 로그인."""
    turns = _turns_by_session([it["session_id"] for it in items])
    keys = [it["site_key"] for it in items if it["site_key"]]
    inquiries, bookings = _counts(InquiryRow, keys), _counts(BookingRow, keys)
    for it in items:
        rows = turns.get(it["session_id"], [])
        it.update(turns=len(rows), flags=flags(M.session_metrics(it["session_id"], rows), rows),
                  inquiries=inquiries.get(it["site_key"], 0), bookings=bookings.get(it["site_key"], 0),
                  owner_logged_in=rooms_svc.owner_claimed(it["room_id"]))


@router.get("/api/admin/rooms")
def list_rooms(q: str = "", limit: int = 50, offset: int = 0, user: dict = Depends(_admin)):
    """가게(방) 목록, 최신순. q는 가게 이름·업종·사이트 키 부분 일치."""
    admin.viewed(user, "rooms")
    limit, offset = max(1, min(limit, PAGE_MAX)), max(0, offset)
    # ponytail: 모든 방의 카드를 읽어 거른다. 방이 수천 개가 되면 검색을 SQL(JSONB)로 옮긴다.
    with get_sessionmaker()() as db:
        rows = db.execute(select(RoomRow.id, RoomRow.created_at, SessionRow.id, SessionRow.state,
                                 SessionRow.requirement_id, SessionRow.prd)
                          .join(SessionRow, RoomRow.session_id == SessionRow.id)
                          .order_by(RoomRow.created_at.desc())).all()
    needle = q.strip().lower()
    found = []
    for room_id, created, session_id, state, site_key, prd in rows:
        card = prd if isinstance(prd, dict) else {}
        if needle and not any(needle in s.lower() for s in (_shop_name(card), _industry(card), site_key or "")):
            continue
        found.append(_item(room_id, created, session_id, state, site_key, card))
    page = found[offset:offset + limit]
    _fill(page)
    return {"rooms": page, "total": len(found)}


@router.get("/api/admin/rooms/{room_id}")
def room_detail(room_id: str, user: dict = Depends(_admin)):
    """가게 하나: 카드 칸, 채팅, 대화 턴(엔진 판단 포함), 대화 지표. 모두 가려서 내보낸다."""
    with get_sessionmaker()() as db:
        room = db.get(RoomRow, room_id)
        sess = db.get(SessionRow, room.session_id) if room is not None else None
        if room is None or sess is None:
            raise HTTPException(status_code=404)
        card = sess.prd if isinstance(sess.prd, dict) else {}
        item = _item(room.id, room.created_at, sess.id, sess.state, sess.requirement_id, card)
        messages = [{"ts": _iso(m.ts), "kind": m.kind, "text": M.mask_pii(m.text or ""),
                     "who": m.member_id if m.member_id in ("ai", "system") else "member"}
                    for m in reversed(db.scalars(select(RoomMessageRow).where(RoomMessageRow.room_id == room.id)
                                                 .order_by(RoomMessageRow.seq.desc()).limit(DETAIL_MAX)).all())]
        turns = _turn_dicts(reversed(db.scalars(select(ChatTurnRow).where(ChatTurnRow.session_id == sess.id)
                                                .order_by(ChatTurnRow.id.desc()).limit(DETAIL_MAX)).all()))
    admin.viewed(user, "room", room_id)
    _fill([item])
    slots = {key: {"status": slot.get("status"), "value": _mask(slot.get("value"))}
             for key, slot in (card.get("slots") or {}).items() if isinstance(slot, dict)}
    return {"room": item, "card": slots, "messages": messages,
            "turns": [{**_mask({k: t[k] for k in ("user_text", "ai_text", "meta")}), "ts": _iso(t["ts"]),
                       "state_before": t["state_before"], "state_after": t["state_after"]} for t in turns],
            "metrics": _mask(M.session_metrics(sess.id, turns))}


class TakedownIn(BaseModel):
    reason: str = Field(default="", max_length=takedown.REASON_MAX)


def _site_key_of(request: Request, room_id: str) -> str:
    """바꾸는 요청 공통(키 API와 같다): 우리 출처, 최근 로그인. 방의 사이트 키를 돌려준다."""
    _check_origin(request)
    admin.require_recent_login(request)
    with get_sessionmaker()() as db:
        room = db.get(RoomRow, room_id)
        sess = db.get(SessionRow, room.session_id) if room is not None else None
        if room is None or sess is None or not sess.requirement_id:
            raise HTTPException(status_code=404)
        return sess.requirement_id


@router.post("/api/admin/rooms/{room_id}/takedown")
def take_down_site(room_id: str, body: TakedownIn, request: Request, user: dict = Depends(_admin)):
    """공개 사이트 내리기(P2-4). 이유는 필수, 기록·운영 알림에 남는다."""
    key = _site_key_of(request, room_id)
    try:
        return {"taken_down": takedown.take_down(key, user["id"], body.reason)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/admin/rooms/{room_id}/restore")
def restore_site(room_id: str, request: Request, user: dict = Depends(_admin)):
    """내린 사이트 다시 열기."""
    key = _site_key_of(request, room_id)
    try:
        takedown.restore(key, user["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"taken_down": None}


@router.get("/api/admin/signals")
def list_signals(days: int = 7, user: dict = Depends(_admin)):
    """최근 days일 대화 중 문제 신호가 하나라도 있는 것, 최근 순."""
    admin.viewed(user, "signals")
    since = _now() - datetime.timedelta(days=max(1, min(days, 90)))
    with get_sessionmaker()() as db:
        sids = db.scalars(select(ChatTurnRow.session_id).where(ChatTurnRow.ts >= since)
                          .group_by(ChatTurnRow.session_id).order_by(func.max(ChatTurnRow.id).desc())
                          .limit(SIGNAL_SESSIONS_MAX)).all()
        room_of = dict(db.execute(select(RoomRow.session_id, RoomRow.id).where(RoomRow.session_id.in_(sids))).all())
        card_of = dict(db.execute(select(SessionRow.id, SessionRow.prd).where(SessionRow.id.in_(sids))).all())
    turns = _turns_by_session(list(sids), since)
    out = []
    for sid in sids:
        if sid not in room_of:
            continue
        rows = turns.get(sid, [])
        metrics = M.session_metrics(sid, rows)
        found = flags(metrics, rows)
        if found:
            card = card_of.get(sid) if isinstance(card_of.get(sid), dict) else {}
            out.append({"room_id": room_of[sid], "session_id": sid, "shop_name": M.mask_pii(_shop_name(card)),
                        "n_turns": metrics["n_turns"], "flags": found, "reached_summary": metrics["reached_summary"],
                        "extract_fail_rate": metrics["extract_fail_rate"], "extract_p50_ms": metrics["extract_p50_ms"]})
    return {"sessions": out}


@router.get("/api/admin/metrics")
def admin_metrics(days: int = 30, user: dict = Depends(_admin)):
    """시안 → 고르기 → 공개 → 문의(D45), 퍼널 수, 방·공개·사장님 로그인 수."""
    from app.services import design_log
    admin.viewed(user, "metrics")
    days = max(1, min(days, 365))
    since = _now() - datetime.timedelta(days=days)
    with get_sessionmaker()() as db:
        funnel = dict(db.execute(select(FunnelEventRow.event, func.count()).where(FunnelEventRow.ts >= since)
                                 .group_by(FunnelEventRow.event)).all())
        created = db.scalar(select(func.count()).select_from(RoomRow).where(RoomRow.created_at >= since))
        published = db.scalar(select(func.count()).select_from(SessionRow)
                              .where(SessionRow.prd["published"].astext.isnot(None)))
        claimed = db.scalars(select(UserRoomRow.room_id).distinct()).all()
    design = design_log.report(days)
    # 못 담은 요구 상위와 처음 보는 종류 상위는 사장님 말이 키에 들어 있다
    design["unmet_top"] = {M.mask_pii(k): n for k, n in (design.get("unmet_top") or {}).items()}
    design["new_kind_top"] = {M.mask_pii(k): n for k, n in (design.get("new_kind_top") or {}).items()}
    return {"days": days, "design": design, "funnel": funnel, "rooms_created": created or 0,
            "published": published or 0, "owners_logged_in": sum(1 for rid in claimed if rooms_svc.owner_claimed(rid))}
