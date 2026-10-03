"""회원 탈퇴 (로드맵 P2-6, 백로그 L-5, USER_DB_PLAN §A-2 "회원 탈퇴 시", UQ-3 추천 답).

바로 하는 것:
- 로그인 수단 삭제: 카카오·구글 연결(oauth_accounts, 카카오 알림 토큰 포함)과 로그인 세션 전부.
- 익명화: 계정 닉네임·이메일, 이 계정이 쓰던 방의 참여자 닉네임과 채팅 닉네임 → "탈퇴한 회원".
  채팅 글·가게 카드·시안은 남긴다(같은 방의 다른 사람과 만든 사이트를 위해, §A-2).
- 손님으로 남긴 연결(customers.user_id)을 끊는다.
- 이 계정이 주인인 가게의 공개 사이트를 내린다(takedown). 주인이 없는 사이트가 손님 문의·예약을
  계속 받지 않게 한다. 관리자가 되돌릴 수 있다.
30일 뒤(purge): users 행을 지운다. 방·가게 연결(user_rooms·shop_members)은 cascade로 함께 지워진다.
결제 기록(subscriptions.payer_user_id)은 FK가 SET NULL이라 거래 기록만 남는다.
"""
import datetime
import logging
from typing import Optional

from sqlalchemy import delete, select, update

from app.db.models import (
    CustomerRow,
    LoginSessionRow,
    OAuthAccountRow,
    RoomMemberRow,
    RoomMessageRow,
    UserRoomRow,
    UserRow,
)
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)

ANON = "탈퇴한 회원"
KEEP_DAYS = 30


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def withdraw(user_id: str) -> dict:
    """탈퇴 처리. 이미 탈퇴했거나 없는 계정이면 LookupError. {rooms, sites_taken_down} 수를 돌려준다."""
    from app.services import shops, takedown
    # 예전 방식(방장 user_rooms)으로만 주인인 가게도 shop_members로 옮겨 센다
    owned = [s["site_key"] for s in shops.member_sites(user_id) if s["role"] == "owner"]
    with get_sessionmaker()() as db, db.begin():
        user = db.get(UserRow, user_id)
        if user is None or user.deleted_at is not None:
            raise LookupError("계정을 찾을 수 없어요.")
        links = db.execute(select(UserRoomRow.room_id, UserRoomRow.member_id)
                           .where(UserRoomRow.user_id == user_id)).all()
        for room_id, member_id in links:
            db.execute(update(RoomMemberRow).where(RoomMemberRow.room_id == room_id,
                                                   RoomMemberRow.member_id == member_id).values(nickname=ANON))
            db.execute(update(RoomMessageRow).where(RoomMessageRow.room_id == room_id,
                                                    RoomMessageRow.member_id == member_id).values(nickname=ANON))
        db.execute(delete(OAuthAccountRow).where(OAuthAccountRow.user_id == user_id))
        db.execute(delete(LoginSessionRow).where(LoginSessionRow.user_id == user_id))
        db.execute(update(CustomerRow).where(CustomerRow.user_id == user_id).values(user_id=None))
        user.nickname, user.email, user.deleted_at = ANON, None, _now()
    down = 0
    for key in owned:
        if takedown.is_down(key):
            continue
        try:
            takedown.take_down(key, f"withdraw:{user_id}", "사장님 탈퇴")
            down += 1
        except Exception:
            log.exception("탈퇴한 사장님 사이트 내리기 실패 %s", key)
    return {"rooms": len(links), "sites_taken_down": down}


def purge(now: Optional[datetime.datetime] = None) -> int:
    """탈퇴 뒤 KEEP_DAYS일 지난 계정을 지운다."""
    cutoff = (now or _now()) - datetime.timedelta(days=KEEP_DAYS)
    with get_sessionmaker()() as db, db.begin():
        return db.execute(delete(UserRow).where(UserRow.deleted_at.isnot(None),
                                                UserRow.deleted_at < cutoff)).rowcount
