"""공개 사이트 내리기 (P2-4): 관리자만, 출처·최근 로그인, 내리면 /site/ 410·문의 막힘, 되돌리면 다시 열림."""
import datetime

import pytest
from sqlalchemy import select

from app import store
from app.api import inquiries as inquiries_api
from app.config import settings
from app.db.models import AdminAuditRow, LoginSessionRow, UserRow
from app.db.session import get_sessionmaker
from app.services import auth as auth_svc
from app.services import guest_chat, takedown

ADMIN, OWNER = "u_admin_td", "u_owner_td"
ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture
def site(client, monkeypatch):
    inquiries_api._hits.clear()
    with get_sessionmaker()() as db, db.begin():
        db.add_all([UserRow(id=ADMIN, nickname="관리자"), UserRow(id=OWNER, nickname="사장님")])
    monkeypatch.setattr(settings, "admin_user_ids", ADMIN)
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    pub = settings.generated_dir / key / "published"
    pub.mkdir(parents=True, exist_ok=True)
    (pub / "index.html").write_text("<h1>우리 가게</h1>", encoding="utf-8")
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(ADMIN))
    return room_id, key


def _inquire(client, key):
    form = {"name": "김손님", "contact": "010-1234-5678", "message": "문의요", "agree": "yes", "website": ""}
    return client.post(f"/api/inquiries/{key}", data=form, follow_redirects=False)


def test_take_down_and_restore(client, site):
    room_id, key = site
    assert client.get(f"/site/{key}/").status_code == 200

    r = client.post(f"/api/admin/rooms/{room_id}/takedown", json={"reason": "사칭 신고"}, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["taken_down"]["reason"] == "사칭 신고"
    page = client.get(f"/site/{key}/")
    assert page.status_code == 410 and "우리 가게" not in page.text and page.headers["x-robots-tag"] == "noindex"
    assert client.get(f"/site/{key}/index.html").status_code == 410
    assert _inquire(client, key).status_code == 400  # 문의도 막힌다
    assert guest_chat.enabled(key) is False
    detail = client.get(f"/api/admin/rooms/{room_id}").json()["room"]
    assert detail["taken_down"]["reason"] == "사칭 신고"
    assert (settings.generated_dir / key / "published" / "index.html").is_file()  # 파일은 지우지 않는다

    assert client.post(f"/api/admin/rooms/{room_id}/restore", headers=ORIGIN).status_code == 200
    assert client.get(f"/site/{key}/").status_code == 200
    assert _inquire(client, key).status_code == 303
    assert client.get(f"/api/admin/rooms/{room_id}").json()["room"]["taken_down"] is None
    with get_sessionmaker()() as db:
        actions = set(db.scalars(select(AdminAuditRow.action).where(AdminAuditRow.target == key)).all())
    assert {"site_takedown", "site_restore"} <= actions


def test_guards(client, site):
    room_id, key = site
    path = f"/api/admin/rooms/{room_id}/takedown"
    assert client.post(path, json={"reason": "x"}).status_code == 403  # 우리 출처가 아님
    assert client.post(path, json={"reason": "  "}, headers=ORIGIN).status_code == 400  # 이유 필수
    assert client.post(f"/api/admin/rooms/{room_id}/restore", headers=ORIGIN).status_code == 400  # 내린 적 없음
    assert client.post("/api/admin/rooms/nope/takedown", json={"reason": "x"}, headers=ORIGIN).status_code == 404
    token = client.cookies.get(auth_svc.SESSION_COOKIE)
    with get_sessionmaker()() as db, db.begin():
        row = db.get(LoginSessionRow, auth_svc._hash(token))
        row.created_at = row.created_at - datetime.timedelta(minutes=settings.admin_reauth_minutes + 1)
    r = client.post(path, json={"reason": "x"}, headers=ORIGIN)
    assert r.status_code == 403 and r.json()["detail"] == "reauth"
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(OWNER))
    assert client.post(path, json={"reason": "x"}, headers=ORIGIN).status_code == 404  # 사장님은 못 한다
    assert not takedown.is_down(key)


def test_broken_marker_counts_as_down(client, site):
    _, key = site
    (settings.generated_dir / key / takedown.MARKER).write_text("{깨짐", encoding="utf-8")
    assert takedown.is_down(key)
    assert client.get(f"/site/{key}/").status_code == 410
