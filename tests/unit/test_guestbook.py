"""청첩장 방명록 (EVENT_INVITE_PLAN 3단계): 남기기 → 공개 페이지에 최신순으로 끼워짐 → 사장님이 지움."""
import datetime

import pytest

from app import store
from app.api import inquiries as inquiries_api
from app.config import settings
from app.services import guestbook


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    inquiries_api._hits.clear()
    yield
    inquiries_api._hits.clear()


def _site(client):
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "신랑", "message": ""})
    key = store.read_session(store.read_room(rid)["session_id"])["requirement_id"]
    return rid, key


def _publish(key, body):
    web = settings.generated_dir / key / "web"
    web.mkdir(parents=True, exist_ok=True)
    (web / "index.html").write_text(f"<html><body>{body}</body></html>", encoding="utf-8")


def test_leave_message_redirects_back_and_notifies_owner(client):
    rid, key = _site(client)
    r = client.post(f"/api/guestbook/{key}", data={"name": "박하객", "message": "결혼 축하해요!"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/site/{key}/#guestbook-title-guestbook"
    assert [e["name"] for e in guestbook.latest(key)] == ["박하객"]
    assert any("방명록에 새 글" in m["text"] for m in store.read_messages(rid, 0))


def test_bad_words_empty_spam_and_unknown_site(client):
    _, key = _site(client)
    assert client.post(f"/api/guestbook/{key}", data={"name": "a", "message": "존나 축하"}).status_code == 400
    assert client.post(f"/api/guestbook/{key}", data={"name": "", "message": "축하"}).status_code == 400
    assert client.post("/api/guestbook/nope", data={"name": "a", "message": "축하"}).status_code == 400
    client.post(f"/api/guestbook/{key}", data={"name": "봇", "message": "광고", "website": "x"}, follow_redirects=False)
    assert guestbook.latest(key) == []


def test_public_page_shows_latest_first_and_escaped(client):
    _, key = _site(client)
    for name, msg in (("첫째", "먼저 남김"), ("<b>둘째</b>", "<script>x</script> 나중")):
        client.post(f"/api/guestbook/{key}", data={"name": name, "message": msg}, follow_redirects=False)
    _publish(key, f'<section>{guestbook.MARK}</section>')
    page = client.get(f"/site/{key}/").text
    assert page.index("둘째") < page.index("첫째")
    assert "<script>x" not in page and "&lt;b&gt;둘째" in page and guestbook.MARK not in page
    _publish(key, "<p>방명록 없는 사이트</p>")
    assert "방명록 없는 사이트" in client.get(f"/site/{key}/").text


def test_owner_lists_and_deletes_only_own(client):
    rid, key = _site(client)
    client.post(f"/api/guestbook/{key}", data={"name": "박하객", "message": "축하해요"}, follow_redirects=False)
    entries = client.get(f"/api/rooms/{rid}/guestbook", headers={"X-Member-Id": "owner"}).json()["entries"]
    assert [e["name"] for e in entries] == ["박하객"]
    assert client.get(f"/api/rooms/{rid}/guestbook", headers={"X-Member-Id": "guest"}).status_code in (403, 404)
    assert client.delete(f"/api/rooms/{rid}/guestbook/{entries[0]['id']}", headers={"X-Member-Id": "owner"}).status_code == 204
    assert guestbook.latest(key) == []
    assert client.delete(f"/api/rooms/{rid}/guestbook/{entries[0]['id']}", headers={"X-Member-Id": "owner"}).status_code == 404


def test_purge_after_a_year(client):
    _, key = _site(client)
    client.post(f"/api/guestbook/{key}", data={"name": "a", "message": "축하"}, follow_redirects=False)
    later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=guestbook.KEEP_DAYS + 1)
    assert guestbook.purge_expired(later) == 1 and guestbook.latest(key) == []


def test_draft_shows_example_and_public_keeps_mark():
    from app.services import site_render as SR
    sec = {"id": "guestbook", "type": "guestbook", "variant": "list", "content": {}}
    tokens = {"palette": "coffee", "font_pair": "sans-clean", "density": "comfortable", "radius": "soft", "image_style": "card"}
    draft = SR.render_site({"tokens": tokens, "sections": [sec]}, site_key="k")
    public = SR.render_site({"tokens": tokens, "sections": [sec]}, site_key="k", public=True)
    assert "방명록 예시" in draft and guestbook.MARK not in draft
    assert guestbook.MARK in public and 'action="/api/guestbook/k"' in public
