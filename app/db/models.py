"""테이블 정의 (STAGE0_DESIGN.md §6.2).

상태머신은 계속 dict를 다루고, dict ↔ 행 변환은 app/store.py가 트랜잭션 경계에서 한다.
"""
import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now_col() -> Mapped[datetime.datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    last_request: Mapped[Optional[str]] = mapped_column(Text)
    quote: Mapped[Optional[dict]] = mapped_column(JSONB)
    codegen: Mapped[Optional[dict]] = mapped_column(JSONB)
    # 요구사항 카드 (app/services/prd_engine.py). 확정본 판 관리는 prd_versions(P-1g)에서.
    prd: Mapped[Optional[dict]] = mapped_column(JSONB)
    design_url: Mapped[Optional[str]] = mapped_column(Text)
    design_preview_url: Mapped[Optional[str]] = mapped_column(Text)
    design_url_unsent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    deploy_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = _now_col()
    updated_at: Mapped[datetime.datetime] = _now_col()


class RoomRow(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False, unique=True)
    ai_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="IDLE")
    created_at: Mapped[datetime.datetime] = _now_col()


class RoomMemberRow(Base):
    __tablename__ = "room_members"

    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True)
    member_id: Mapped[str] = mapped_column(Text, primary_key=True)
    nickname: Mapped[str] = mapped_column(Text, nullable=False)
    joined_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 입장 순서를 보존한다 (과반 계산에는 무관하지만 목록 표시 순서가 바뀌지 않게).
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class RoomMessageRow(Base):
    __tablename__ = "room_messages"
    __table_args__ = (
        UniqueConstraint("room_id", "seq", name="uq_room_messages_room_seq"),
        Index("ix_room_messages_room_seq", "room_id", "seq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    member_id: Mapped[str] = mapped_column(Text, nullable=False)
    nickname: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RoomVoteRow(Base):
    __tablename__ = "room_votes"

    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True)
    member_id: Mapped[str] = mapped_column(Text, primary_key=True)
    vote: Mapped[str] = mapped_column(Text, nullable=False)


class FunnelEventRow(Base):
    """유입·전환 단계 이벤트 (DECISIONS.md D16). 개인정보 없음, 90일 보관."""

    __tablename__ = "funnel_events"
    __table_args__ = (
        Index("ix_funnel_events_event_ts", "event", "ts"),
        Index("ix_funnel_events_visitor", "visitor_id"),
        Index("ix_funnel_events_ts", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime.datetime] = _now_col()
    event: Mapped[str] = mapped_column(Text, nullable=False)
    # 브라우저가 만든 무작위 ID. 사람을 식별하지 않고 한 방문자의 단계만 잇는다.
    visitor_id: Mapped[Optional[str]] = mapped_column(Text)
    session_id: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[Optional[str]] = mapped_column(Text)
    campaign: Mapped[Optional[str]] = mapped_column(Text)
    template_id: Mapped[Optional[str]] = mapped_column(Text)


class ChatTurnRow(Base):
    """대화 한 턴의 원문과 엔진 판단. AI 성능 평가의 재료 (1:1·공유방 모두). 90일 보관."""

    __tablename__ = "chat_turns"
    __table_args__ = (
        Index("ix_chat_turns_session", "session_id", "id"),
        Index("ix_chat_turns_ts", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime.datetime] = _now_col()
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    room_id: Mapped[Optional[str]] = mapped_column(Text)
    author: Mapped[Optional[str]] = mapped_column(Text)  # 공개 식별자(member_handle). 비밀값이 아니다
    user_text: Mapped[str] = mapped_column(Text, nullable=False)
    ai_text: Mapped[str] = mapped_column(Text, nullable=False)
    state_before: Mapped[str] = mapped_column(Text, nullable=False)
    state_after: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB)


# ── 계정 (1-1, DECISIONS.md D9·UQ-2: users + oauth_accounts 분리형, 제공자 토큰은 저장하지 않음) ──

class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    nickname: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = _now_col()
    last_login_at: Mapped[datetime.datetime] = _now_col()
    deleted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))


class OAuthAccountRow(Base):
    __tablename__ = "oauth_accounts"

    provider: Mapped[str] = mapped_column(Text, primary_key=True)          # kakao | google
    provider_user_id: Mapped[str] = mapped_column(Text, primary_key=True)  # 카카오 회원번호 / 구글 sub
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime.datetime] = _now_col()


class LoginSessionRow(Base):
    """쿠키에는 무작위 토큰, DB에는 그 해시만 둔다(유출돼도 세션을 만들 수 없게)."""

    __tablename__ = "login_sessions"

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime.datetime] = _now_col()
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OAuthStateRow(Base):
    """로그인 도중의 state(로그인 CSRF 방지)와 PKCE 검증값. 10분 뒤 무효."""

    __tablename__ = "oauth_states"

    state_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    code_verifier: Mapped[str] = mapped_column(Text, nullable=False)
    next_path: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserRoomRow(Base):
    """로그인 전에 이 기기로 쓰던 방을 계정으로 옮긴 기록(1-3). 다른 기기에서도 목록에 보인다."""

    __tablename__ = "user_rooms"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True)
    member_id: Mapped[str] = mapped_column(Text, nullable=False)
    claimed_at: Mapped[datetime.datetime] = _now_col()


class InquiryRow(Base):
    """생성 사이트의 "문의하기" 폼으로 들어온 문의 (플랫폼 공용 ①, D31·D32). 30일 보관."""

    __tablename__ = "inquiries"
    __table_args__ = (
        Index("ix_inquiries_site", "site_key", "id"),
        Index("ix_inquiries_ts", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime.datetime] = _now_col()
    site_key: Mapped[str] = mapped_column(Text, nullable=False)  # sessions.requirement_id (/site/<id>/)
    name: Mapped[Optional[str]] = mapped_column(Text)
    contact: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
