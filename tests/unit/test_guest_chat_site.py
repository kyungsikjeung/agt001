"""공개 사이트 "채팅하기" 단추 + 빌더 "채팅" 칩 (GUEST_CHAT_CONTRACT §5의 6)."""
import secrets

import pytest

from app import store
from app.db.models import UserRoomRow, UserRow
from app.db.session import get_sessionmaker
from app.services import auth as auth_svc
from app.services import publish_check, shops, site_render

ORIGIN = {"Origin": "http://testserver"}

TOKENS = {"palette": "coffee", "font_pair": "sans-clean", "density": "comfortable",
          "radius": "soft", "image_style": "card"}
VARIANTS = ("call-first", "booking-first", "chat-first", "form", "kakao-channel")


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    # /api/start의 IP 제한(10분 5번)을 테스트마다 따로 센다.
    from app.api import inquiries as inquiries_api
    with inquiries_api._lock:
        inquiries_api._hits.clear()


def _published_site(client, name="모퉁이 커피"):
    """공개된 가게(shops 행) + 로그인한 주인 (test_guest_chat과 같은 꼴)."""
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    shops.ensure(key, name, room_id)
    uid = f"u-{secrets.token_hex(4)}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=uid, nickname="사장님"))
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRoomRow(user_id=uid, room_id=room_id, member_id="owner"))
    return room_id, key, uid


def _spec(variant: str) -> dict:
    content = {"phone": "02-1234-5678", "hours": "매일 10:00~20:00"}
    if variant == "booking-first":
        content["booking_url"] = "https://booking.example.com/abc"
    elif variant == "chat-first":
        content["channel_url"] = "https://pf.kakao.com/_abcDEF"
    elif variant == "kakao-channel":
        content = {"kakao_channel_url": "https://pf.kakao.com/_abcDEF"}  # 빈 채널은 공개본에서 통째로 빠진다
    return {"tokens": TOKENS, "sections": [
        {"id": "contact", "type": "contact", "variant": variant, "content": content}]}


def _login(client, uid):
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(uid))


@pytest.mark.parametrize("variant", VARIANTS)
def test_6_on_shows_new_tab_button_and_passes_publish_check(client, variant):
    """켜짐(공개된 가게+기본 켜짐)이면 연락 부품마다 /chat/<key> 새 탭 링크가 있다."""
    _, key, _ = _published_site(client)
    html = site_render.render_site(_spec(variant), site_key=key, public=True, title="모퉁이 커피")
    assert (f'<a class="s-btn s-btn--ghost" href="/chat/{key}"'
            ' target="_blank" rel="noopener">채팅하기</a>') in html
    assert publish_check.check_html(html) == []


def test_6_off_or_unpublished_hides_button(client):
    """꺼짐(사장님이 끔)·공개 전(shops 행 없음)·site_key 없음에는 단추가 없다."""
    _, key, uid = _published_site(client)
    _login(client, uid)
    r = client.post(f"/api/owner/shops/{key}/chat-settings", json={"guest_chat_on": False}, headers=ORIGIN)
    assert r.status_code == 200 and r.json() == {"guest_chat_on": False}
    html = site_render.render_site(_spec("call-first"), site_key=key, public=True)
    assert "/chat/" not in html and "채팅하기" not in html
    room_id = client.post("/room").json()["room_id"]
    draft_key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    assert "채팅하기" not in site_render.render_site(_spec("call-first"), site_key=draft_key, public=True)
    assert "채팅하기" not in site_render.render_site(_spec("call-first"), public=True)


def test_6_builder_chat_chip_and_put_400(client):
    """칩은 stamps 다음, 공개 전엔 꺼짐. PUT chat은 stamps·order와 같은 400 안내."""
    body = client.post("/api/start", json={"template": "cafe"}).json()
    rid, headers = body["room_id"], {"X-Member-Id": body["member_id"]}
    feats = client.get(f"/api/rooms/{rid}/features", headers=headers).json()["features"]
    keys = [f["key"] for f in feats]
    assert keys.index("chat") == keys.index("stamps") + 1
    assert {f["key"]: f for f in feats}["chat"] == {"key": "chat", "label": "채팅", "kind": "shop",
                                                    "on": False, "after_publish": True}
    r = client.put(f"/api/rooms/{rid}/features", json={"key": "chat", "on": True}, headers=headers)
    assert r.status_code == 400
    assert r.json()["detail"] == "공개한 뒤 사장님 화면에서 켤 수 있어요"
    req = store.read_session(store.read_room(rid)["session_id"])["requirement_id"]
    shops.ensure(req, "모퉁이 커피", rid)
    feats = client.get(f"/api/rooms/{rid}/features", headers=headers).json()["features"]
    assert {f["key"]: f for f in feats}["chat"]["on"] is True


def test_first_publish_already_has_chat_button(client, monkeypatch):
    """첫 공개본부터 '채팅하기'가 붙는다(가게 행을 공개 페이지보다 먼저 만든다)."""
    from app import store
    from app.config import settings
    from app.api import inquiries as inquiries_api
    monkeypatch.setattr(settings, "publish_login_required", False)
    with inquiries_api._lock:
        inquiries_api._hits.clear()
    body = client.post("/api/start", json={"template": "cafe"}).json()
    rid, headers = body["room_id"], {"X-Member-Id": body["member_id"]}
    client.put(f"/api/rooms/{rid}/card", json={"fields": {"shop_name": "모퉁이 커피", "phone": "010-1234-5678"}},
               headers=headers)
    feats = client.get(f"/api/rooms/{rid}/features", headers=headers).json()["features"]
    contact = next((f["key"] for f in feats if f["key"].startswith("section:") and "문의" in f["label"]), None)
    if contact:
        client.put(f"/api/rooms/{rid}/features", json={"key": contact, "on": True}, headers=headers)
    assert client.post(f"/api/rooms/{rid}/publish", json={"force": True}, headers=headers).json().get("ok")
    key = store.read_session(store.read_room(rid)["session_id"])["requirement_id"]
    page = (settings.generated_dir / key / "published" / "index.html").read_text(encoding="utf-8")
    assert f'href="/chat/{key}"' in page and "채팅하기" in page
