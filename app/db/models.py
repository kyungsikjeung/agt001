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
