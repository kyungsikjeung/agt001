"""청첩장 방명록 (EVENT_INVITE_PLAN 3단계).

하객이 공개 사이트 폼(일반 HTML form, 스크립트 없음)으로 이름·글을 남긴다. 공개 페이지를 보낼 때
최신 글을 끼워 넣는다(inject). 사장님은 빌더에서 지운다. 욕설은 받지 않는다. 1년 지나면 지운다.
"""
import datetime
import html
import logging
import re
from typing import Optional

from sqlalchemy import delete, select

from app import store
from app.db.models import GuestbookRow, RoomRow, SessionRow
from app.db.session import get_sessionmaker
from app.security import sanitize_token
from app.services import inquiries, rooms

log = logging.getLogger(__name__)

KEEP_DAYS = 365
MAX_NAME, MAX_MESSAGE, SHOW = 20, 300, 30
MARK = "<!--agt-guestbook-->"  # 템플릿 guestbook--list 안의 자리. 공개 페이지를 보낼 때 글 목록으로 바뀐다
_KST = datetime.timezone(datetime.timedelta(hours=9))
# ponytail: 낱말 목록 거르기. 띄어 쓰거나 바꿔 쓰면 빠져나간다 → 사장님이 지운다. 늘면 LLM 판정으로
_BAD = re.compile(r"씨발|시발|ㅅㅂ|ㅆㅂ|씹|좆|존나|ㅈㄴ|병신|ㅂㅅ|개새|새끼|미친놈|미친년|닥쳐|꺼져|느금|니애미|엠창|fuck|shit", re.I)


class GuestbookError(Exception):
    """방문자에게 보여 줄 한 줄."""


def _clean(value: Optional[str], limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def add(site_key: str, name: Optional[str], message: Optional[str], website: Optional[str]) -> bool:
    """남겼으면 True, 스팸 칸이 차 있으면 조용히 False. 틀리면 GuestbookError."""
    key = sanitize_token(site_key or "")
    if not key or not inquiries.site_exists(key):
        raise GuestbookError("사이트를 찾을 수 없어요.")
    if website:
        return False
    name_c, text = _clean(name, MAX_NAME), str(message or "").strip()[:MAX_MESSAGE]
    if not name_c or not text:
        raise GuestbookError("이름과 남기실 말을 적어 주세요.")
    if _BAD.search(name_c + text):
        raise GuestbookError("축하의 말을 고운 말로 남겨 주세요.")
    with get_sessionmaker()() as db, db.begin():
        db.add(GuestbookRow(site_key=key, name=name_c, message=text))
        room_id = db.scalar(select(RoomRow.id).join(SessionRow, RoomRow.session_id == SessionRow.id)
                            .where(SessionRow.requirement_id == key))
    if room_id:
        try:
            with store.room_tx(room_id) as (room, _session):
                if room is not None:
                    rooms._append(room, "system", "방명록", f"방명록에 새 글이 올라왔어요.\n{name_c}: {text[:80]}",
                                  kind="system")
        except Exception:
            log.exception("방명록 알림 실패 room=%s", room_id)
    return True


def latest(site_key: str, limit: int = SHOW) -> list:
    """최신순 [{id, name, message, ts}]."""
    key = sanitize_token(site_key or "")
    if not key:
        return []
    with get_sessionmaker()() as db:
        rows = db.scalars(select(GuestbookRow).where(GuestbookRow.site_key == key)
                          .order_by(GuestbookRow.id.desc()).limit(limit)).all()
        return [{"id": r.id, "name": r.name, "message": r.message, "ts": r.ts} for r in rows]


def remove(site_key: str, entry_id: int) -> bool:
    key = sanitize_token(site_key or "")
    with get_sessionmaker()() as db, db.begin():
        return db.execute(delete(GuestbookRow).where(GuestbookRow.site_key == key,
                                                     GuestbookRow.id == entry_id)).rowcount > 0


def purge_expired(now: Optional[datetime.datetime] = None) -> int:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    with get_sessionmaker()() as db, db.begin():
        n = db.execute(delete(GuestbookRow).where(GuestbookRow.ts < now - datetime.timedelta(days=KEEP_DAYS))).rowcount
    if n:
        log.info("방명록 %d건 삭제 (%d일 경과)", n, KEEP_DAYS)
    return n


def entries_html(site_key: str) -> str:
    """공개 페이지에 끼울 글 목록(최신순, 이스케이프). 글이 없으면 첫 글 안내."""
    items = latest(site_key)
    if not items:
        return '<p class="s-guestbook__empty">아직 남긴 글이 없어요. 첫 축하를 남겨 주세요.</p>'
    out = []
    for e in items:
        when = e["ts"].astimezone(_KST).strftime("%-m월 %-d일") if e.get("ts") else ""
        out.append(f'<li class="s-guestbook__item"><p class="s-guestbook__who"><b>{html.escape(e["name"])}</b>'
                   f'<span class="s-guestbook__date">{when}</span></p><p class="s-guestbook__text">{html.escape(e["message"])}</p></li>')
    return '<ul class="s-guestbook__list">' + "".join(out) + "</ul>"


def inject(page: str, site_key: str) -> str:
    """공개 페이지에 방명록 자리가 있으면 최신 글로 바꾼다. 읽다 실패하면 자리만 지운다(페이지는 보인다)."""
    if MARK not in page:
        return page
    try:
        return page.replace(MARK, entries_html(site_key), 1)
    except Exception:
        log.exception("방명록 끼워 넣기 실패 %s", site_key)
        return page.replace(MARK, "", 1)
