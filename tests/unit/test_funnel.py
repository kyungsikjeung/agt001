"""유입 측정 (DECISIONS.md D16): 허용 목록, 개인정보 없음, 상태 전이 기록, 롤백, 90일 정리, 빈도 제한."""
import datetime

import pytest
from sqlalchemy import select, update

from app import store
from app.db.models import FunnelEventRow
from app.db.session import get_sessionmaker
from app.services import funnel


def _events():
    with get_sessionmaker()() as db:
        return db.scalars(select(FunnelEventRow).order_by(FunnelEventRow.id)).all()


def _chat(client, message, session_id):
    return client.post("/chat", json={"session_id": session_id, "message": message}).json()


def test_client_event_is_recorded_and_sanitized(client):
    r = client.post("/events", json={"event": "template_click", "visitor_id": "v-1<script>", "template_id": "pension", "source": "kakao"})
    assert r.status_code == 204
    [e] = _events()
    assert (e.event, e.visitor_id, e.template_id, e.source) == ("template_click", "v-1script", "pension", "kakao")


def test_unknown_and_server_only_events_are_rejected(client):
    assert client.post("/events", json={"event": "drop_table"}).status_code == 400
    # 서버 단계 이벤트를 브라우저가 위조하지 못한다.
    assert client.post("/events", json={"event": "generate_done"}).status_code == 400
    assert _events() == []


def test_state_transitions_record_server_events(client):
    s = "sess-funnel"
    for m in ("", "카페 홈페이지 만들어줘", "시안 먼저 볼게요", "승인", "진행", "poll"):
        _chat(client, m, s)
    assert [e.event for e in _events()] == ["request_submitted", "requirement_approved", "generate_start", "generate_done"]
    assert {e.session_id for e in _events()} == {s}


def test_event_rolls_back_with_failed_transaction(client):
    with pytest.raises(RuntimeError):
        with store.session_tx("s-rb", default=lambda: {"state": "GREETING", "requirement_id": "rb"}):
            funnel.record("request_submitted", session_id="s-rb")
            raise RuntimeError("boom")
    assert _events() == []


def test_purge_removes_only_expired(client):
    funnel.record("landing_view", visitor_id="old")
    funnel.record("landing_view", visitor_id="new")
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(FunnelEventRow).where(FunnelEventRow.visitor_id == "old")
                   .values(ts=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=91)))
    assert funnel.purge_expired() == 1
    assert [e.visitor_id for e in _events()] == ["new"]


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(funnel, "RATE_LIMIT_PER_MIN", 3)
    funnel._hits.clear()
    codes = [client.post("/events", json={"event": "landing_view"}).status_code for _ in range(4)]
    assert codes == [204, 204, 204, 429]
    funnel._hits.clear()
