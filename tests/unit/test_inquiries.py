"""생성 사이트 문의 폼 (플랫폼 공용 ①): 저장 + 채팅방 알림, 스팸·검증·빈도 제한."""
import pytest

from app import store
from app.api import inquiries as inquiries_api
from app.services import inquiries


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    inquiries_api._hits.clear()


def _site(client):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    session = store.read_session(store.read_room(room_id)["session_id"])
    return room_id, session["requirement_id"]


def _send(client, key, **over):
    form = {"name": "김손님", "contact": "010-1234-5678", "message": "주말 레슨 가능한가요?", "agree": "yes", "website": ""}
    form.update(over)
    return client.post(f"/api/inquiries/{key}", data=form, follow_redirects=False)


def test_submit_saves_and_notifies_room(client):
    room_id, key = _site(client)
    r = _send(client, key)
    assert r.status_code == 303 and r.headers["location"] == f"/api/inquiries/{key}/done"
    msgs = store.read_messages(room_id, 0)
    last = msgs[-1]
    assert last["kind"] == "inquiry"
    assert "010-1234-5678" in last["text"] and "주말 레슨" in last["text"]
    done = client.get(r.headers["location"])
    assert done.status_code == 200 and f"/site/{key}/" in done.text


def test_honeypot_looks_ok_but_not_saved(client):
    room_id, key = _site(client)
    before = len(store.read_messages(room_id, 0))
    r = _send(client, key, website="http://spam")
    assert r.status_code == 303
    assert len(store.read_messages(room_id, 0)) == before


@pytest.mark.parametrize("over", [{"contact": ""}, {"contact": "abc"}, {"message": "  "}, {"agree": ""}])
def test_invalid_input_400(client, over):
    _, key = _site(client)
    r = _send(client, key, **over)
    assert r.status_code == 400
    assert "<script" not in r.text


def test_unknown_site_400(client):
    assert _send(client, "nope-site").status_code == 400


def test_rate_limit(client):
    _, key = _site(client)
    codes = [_send(client, key).status_code for _ in range(inquiries_api.RATE_LIMIT + 1)]
    assert codes[-1] == 429 and codes[0] == 303


def test_message_html_is_escaped_in_error_page(client):
    r = _send(client, "<script>x</script>")
    assert "<script>x" not in r.text


def test_phone_inquiry_links_customer_and_shows_line(client):
    from app.db.models import InquiryRow
    from app.db.session import get_sessionmaker
    room_id, key = _site(client)
    assert _send(client, key, contact="010-5555-6666").status_code == 303
    with get_sessionmaker()() as db:
        row = db.query(InquiryRow).filter(InquiryRow.site_key == key).one()
        assert row.customer_id is not None
    assert "처음 오신 손님이에요." in store.read_messages(room_id, 0)[-1]["text"]


def test_email_inquiry_has_no_customer_and_no_line(client):
    from app.db.models import InquiryRow
    from app.db.session import get_sessionmaker
    room_id, key = _site(client)
    assert _send(client, key, contact="sonnim@example.com").status_code == 303
    with get_sessionmaker()() as db:
        row = db.query(InquiryRow).filter(InquiryRow.site_key == key).one()
        assert row.customer_id is None
    last = store.read_messages(room_id, 0)[-1]["text"]
    assert "처음 오신 손님이에요." not in last and "이 번호로" not in last


def test_purge_expired(client):
    import datetime
    _, key = _site(client)
    _send(client, key)
    later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=inquiries.RETENTION_DAYS + 1)
    assert inquiries.purge_expired(later) == 1
