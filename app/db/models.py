"""테이블 정의 (STAGE0_DESIGN.md §6.2).

상태머신은 계속 dict를 다루고, dict ↔ 행 변환은 app/store.py가 트랜잭션 경계에서 한다.
"""
import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, func, text
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
    # 새 방은 초대 링크로만 들어온다(ROOM_POLICY §3). 이 기능 전에 만든 방은 예전처럼 주소로 들어온다.
    invite_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


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
    meta: Mapped[Optional[dict]] = mapped_column(JSONB)  # 예: 사진 메시지 {"photo": {"id", "url"}}


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
    # 디자인 학습 기록(D44·D45): 명세 값(목록 키)·사이트 키만. 가게 사실·대화 원문은 넣지 않는다.
    props: Mapped[Optional[dict]] = mapped_column(JSONB)


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
    # 카카오 "나에게 보내기" 알림용 리프레시 토큰(암호화). 사장님이 알림을 켰을 때만 저장한다(UQ-1 예외, D32).
    talk_refresh_enc: Mapped[Optional[str]] = mapped_column(Text)
    talk_refresh_expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))


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
    customer_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("customers.id", ondelete="SET NULL"),
                                                      index=True)


class BookingRow(Base):
    """생성 사이트의 "예약 신청" 폼으로 들어온 신청 (플랫폼 공용 ②, D31·D32, BOOKING_PLAN.md). 방문일 + 30일 보관."""

    __tablename__ = "bookings"
    __table_args__ = (
        Index("ix_bookings_site", "site_key", "id"),
        Index("ix_bookings_visit", "visit_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime.datetime] = _now_col()
    site_key: Mapped[str] = mapped_column(Text, nullable=False)  # sessions.requirement_id (/site/<id>/)
    visit_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    visit_time: Mapped[str] = mapped_column(Text, nullable=False)  # "HH:MM"
    service: Mapped[Optional[str]] = mapped_column(Text)
    party: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    memo: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="requested")  # requested·confirmed·declined
    decided_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))
    customer_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("customers.id", ondelete="SET NULL"),
                                                      index=True)


class CustomerRow(Base):
    """가게별 손님 명단 (CUSTOMER_PLAN §1.1). 번호는 정규화한 숫자만 평문으로 둔다."""

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("site_key", "phone", name="uq_customers_site_phone"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_key: Mapped[str] = mapped_column(Text, nullable=False)  # sessions.requirement_id (/site/<id>/)
    phone: Mapped[str] = mapped_column(Text, nullable=False)  # 정규화한 번호(숫자만, +82 → 0)
    name: Mapped[Optional[str]] = mapped_column(Text)  # 마지막으로 적은 이름
    first_seen: Mapped[datetime.datetime] = _now_col()
    last_seen: Mapped[datetime.datetime] = _now_col()
    phone_verified_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))


class PhoneVerificationRow(Base):
    """문자 인증 요청 보관 (CUSTOMER_PLAN §4.2). 인증에 성공하면 지운다."""

    __tablename__ = "phone_verifications"
    __table_args__ = (
        Index("ix_phone_verifications_site_phone", "site_key", "phone"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    site_key: Mapped[str] = mapped_column(Text, nullable=False)  # sessions.requirement_id
    phone: Mapped[str] = mapped_column(Text, nullable=False)  # 정규화한 번호(숫자만)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)  # sha256(token + code)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)  # 인증 뒤 저장할 폼 내용
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime.datetime] = _now_col()


class RoomInviteRow(Base):
    """초대 링크(ROOM_POLICY §3). 토큰 원문은 저장하지 않는다."""

    __tablename__ = "room_invites"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = _now_col()
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    uses: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class AttachmentRow(Base):
    """채팅방에 올린 사진. 위치 정보를 지우고 줄인 JPEG만 보관한다(원본 없음, S-6)."""

    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[Optional[str]] = mapped_column(Text)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = _now_col()


class SecretRow(Base):
    """관리자 화면에서 바꾼 API 키(D50). 값은 암호화해 두고 화면에는 뒤 4자리만 보인다."""

    __tablename__ = "secrets"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    value_enc: Mapped[str] = mapped_column(Text, nullable=False)
    last4: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime.datetime] = _now_col()
    updated_by: Mapped[str] = mapped_column(Text, nullable=False)


class SecretVersionRow(Base):
    """바뀌기 전 키(7일 되돌리기용, 암호화). 7일이 지나면 지운다."""

    __tablename__ = "secret_versions"
    __table_args__ = (Index("ix_secret_versions_name", "name", "replaced_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    value_enc: Mapped[str] = mapped_column(Text, nullable=False)
    last4: Mapped[str] = mapped_column(Text, nullable=False)
    replaced_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    replaced_by: Mapped[str] = mapped_column(Text, nullable=False)


class AdminAuditRow(Base):
    """관리자가 무엇을 봤고 바꿨는지(D49·D50). 키 값·개인정보는 넣지 않는다."""

    __tablename__ = "admin_audit"
    __table_args__ = (Index("ix_admin_audit_ts", "ts"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime.datetime] = _now_col()
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[Optional[str]] = mapped_column(Text)
    detail: Mapped[Optional[dict]] = mapped_column(JSONB)


class ShopSettingsRow(Base):
    """가게별 설정 (OWNER_SETTINGS_PLAN §1.2). 솔라피 키는 암호화해서 둔다."""

    __tablename__ = "shop_settings"

    site_key: Mapped[str] = mapped_column(Text, primary_key=True)  # sessions.requirement_id
    phone_verify: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    solapi_key_enc: Mapped[Optional[str]] = mapped_column(Text)
    solapi_secret_enc: Mapped[Optional[str]] = mapped_column(Text)
    sms_sender: Mapped[Optional[str]] = mapped_column(Text)  # 숫자만
    key_last4: Mapped[Optional[str]] = mapped_column(Text)  # 화면 표시용 키 뒤 4자리
    updated_by: Mapped[Optional[str]] = mapped_column(Text)  # users.id
    updated_at: Mapped[datetime.datetime] = _now_col()


class ShopRow(Base):
    """가게 (BOOKING_BOT_IMPL_PLAN OWN-1). site_key = sessions.requirement_id."""

    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = _now_col()
    closed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))
    phone_verified_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))
    biz_no: Mapped[Optional[str]] = mapped_column(Text)
    biz_verified_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[Optional[str]] = mapped_column(Text)


class ShopMemberRow(Base):
    """가게 권한. 가게당 owner 한 명(부분 유니크 인덱스)."""

    __tablename__ = "shop_members"
    __table_args__ = (
        CheckConstraint("role IN ('owner', 'staff')", name="ck_shop_members_role"),
        Index("ix_shop_members_user", "user_id"),
        Index("uq_shop_members_owner", "shop_id", unique=True, postgresql_where=text("role = 'owner'")),
    )

    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = _now_col()
