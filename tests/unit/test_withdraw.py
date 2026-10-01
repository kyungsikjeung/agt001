"""회원 탈퇴 (로드맵 P2-6, L-5): 로그인 수단 삭제, 닉네임 익명화, 내 가게 사이트 내리기, 30일 뒤 삭제."""
import datetime

from sqlalchemy import select

from app import store
from app.config import settings
from app.db.models import (
    CustomerRow,
    LoginSessionRow,
    OAuthAccountRow,
    RoomMessageRow,
    UserRoomRow,
    UserRow,
)
from app.db.session import get_sessionmaker
from app.services import accounts, takedown
from app.services import auth as auth_svc

UID = "u_withdraw"
ORIGIN = {"Origin": "http://testserver"}


def _setup(client):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "김사장", "message": "카페예요"})
    client.post(f"/room/{room_id}/chat", json={"member_id": "friend", "nickname": "친구", "message": "좋아요"})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    pub = settings.generated_dir / key / "published"
    pub.mkdir(parents=True, exist_ok=True)
    (pub / "index.html").write_text("<h1>가게</h1>", encoding="utf-8")
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=UID, nickname="김사장", email="kim@example.com"))
    with get_sessionmaker()() as db, db.begin():
        db.add(OAuthAccountRow(provider="kakao", provider_user_id="k-1", user_id=UID))
        db.add(UserRoomRow(user_id=UID, room_id=room_id, member_id="owner"))
        db.add(CustomerRow(site_key="other-shop", phone="01012345678", user_id=UID))
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(UID))
    return room_id, key


def _nicknames(room_id):
    room = store.read_room(room_id)
    with get_sessionmaker()() as db:
        msgs = db.execute(select(RoomMessageRow.member_id, RoomMessageRow.nickname)
                          .where(RoomMessageRow.room_id == room_id)).all()
    return {m["member_id"]: m["nickname"] for m in room["members"]}, set(msgs)


def test_withdraw(client):
    room_id, key = _setup(client)
    assert client.post("/api/me/withdraw", json={"confirm": "탈퇴"}).status_code == 403  # 우리 출처가 아님
    assert client.post("/api/me/withdraw", json={"confirm": "네"}, headers=ORIGIN).status_code == 400
    r = client.post("/api/me/withdraw", json={"confirm": "탈퇴"}, headers=ORIGIN)
    assert r.status_code == 200 and r.json() == {"rooms": 1, "sites_taken_down": 1}
    assert client.get("/api/me").status_code == 401

    with get_sessionmaker()() as db:
        user = db.get(UserRow, UID)
        assert user.nickname == accounts.ANON and user.email is None and user.deleted_at is not None
        assert db.scalars(select(OAuthAccountRow).where(OAuthAccountRow.user_id == UID)).all() == []
        assert db.scalars(select(LoginSessionRow).where(LoginSessionRow.user_id == UID)).all() == []
        assert db.scalar(select(CustomerRow.user_id).where(CustomerRow.site_key == "other-shop")) is None
    members, msgs = _nicknames(room_id)
    assert members["owner"] == accounts.ANON and members["friend"] == "친구"
    assert ("owner", "김사장") not in msgs and ("friend", "친구") in msgs
    assert takedown.info(key)["reason"] == "사장님 탈퇴"
    assert client.get(f"/site/{key}/").status_code == 410


def test_purge_after_30_days(client):
    room_id, _ = _setup(client)
    accounts.withdraw(UID)
    assert accounts.purge() == 0  # 아직 30일 안
    later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=accounts.KEEP_DAYS + 1)
    assert accounts.purge(later) == 1
    with get_sessionmaker()() as db:
        assert db.get(UserRow, UID) is None
        assert db.scalars(select(UserRoomRow).where(UserRoomRow.user_id == UID)).all() == []
    assert store.read_room(room_id) is not None  # 방과 사이트 기록은 남는다


def test_withdraw_needs_login(client):
    assert client.post("/api/me/withdraw", json={"confirm": "탈퇴"}, headers=ORIGIN).status_code == 401
