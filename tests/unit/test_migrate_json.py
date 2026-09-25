"""JSON → PostgreSQL 이전 스크립트: 멱등성, 재시작 복구 규칙, 모르는 키 처리."""
import importlib.util
import json
import sys

from app import store
from app.config import PROJECT_ROOT, settings

_spec = importlib.util.spec_from_file_location("migrate_json_to_pg", PROJECT_ROOT / "scripts" / "migrate_json_to_pg.py")
migrate_script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_script)


def _write_fixture():
    sessions = {
        "s-room": {"state": "AWAIT_APPROVAL", "requirement_id": "rq1", "last_request": "펜션 홈페이지", "old_key": 1},
        "s-gen": {"state": "GENERATING", "requirement_id": "rq2", "codegen": {"status": "done"}},
        "s-bad": {"state": "GREETING"},
    }
    rooms = {
        "room1": {
            "room_id": "room1", "session_id": "s-room", "created_at": "2026-09-20T01:00:00+00:00",
            "ai_status": "QUOTING",
            "members": [
                {"member_id": "a", "nickname": "철수", "joined_at": "2026-09-20T01:00:00+00:00", "last_seen": "2026-09-20T01:05:00+00:00"},
                {"member_id": "b", "nickname": "영희", "joined_at": "2026-09-20T01:01:00+00:00", "last_seen": "2026-09-20T01:05:00+00:00"},
            ],
            "messages": [
                {"seq": 0, "member_id": "system", "nickname": "시스템", "text": "철수님이 입장했습니다.", "ts": "2026-09-20T01:00:00+00:00", "kind": "system"},
                {"seq": 1, "member_id": "a", "nickname": "철수", "text": "펜션 홈페이지", "ts": "2026-09-20T01:02:00+00:00", "kind": "chat"},
            ],
            "votes": {"a": "approve"},
        },
        "orphan": {"room_id": "orphan", "session_id": "missing", "members": [], "messages": [], "votes": {}},
    }
    (settings.generated_dir / "sessions.json").write_text(json.dumps(sessions, ensure_ascii=False), encoding="utf-8")
    (settings.generated_dir / "rooms.json").write_text(json.dumps(rooms, ensure_ascii=False), encoding="utf-8")


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["migrate_json_to_pg.py", *argv])
    assert migrate_script.main() == 0


def test_migrate_is_idempotent_and_applies_recovery(client, monkeypatch, capsys):
    _write_fixture()
    _run(monkeypatch, "--dry-run")
    out = capsys.readouterr().out
    assert "old_key" in out
    assert store.read_session("s-room") is None  # dry-run은 쓰지 않는다

    _run(monkeypatch)
    _run(monkeypatch)  # 두 번째는 전부 건너뜀

    assert store.read_session("s-room")["last_request"] == "펜션 홈페이지"
    gen = store.read_session("s-gen")
    assert gen["state"] == "QUOTED" and "codegen" not in gen
    assert store.read_session("s-bad") is None
    room = store.read_room("room1")
    assert room["ai_status"] == "IDLE"
    assert [m["nickname"] for m in room["members"]] == ["철수", "영희"]
    assert room["votes"] == {"a": "approve"}
    assert [m["seq"] for m in store.read_messages("room1", 0)] == [0, 1]
    assert store.read_room("orphan") is None

    # 이전된 방에 이어서 쓰면 seq가 이어진다.
    from app.services import rooms as rooms_svc
    rooms_svc.post_message("room1", "c", "민수", "", "http://t/")
    assert [m["seq"] for m in store.read_messages("room1", 0)] == [0, 1, 2]


def test_archive_moves_json(client, monkeypatch):
    _write_fixture()
    _run(monkeypatch, "--archive")
    assert not (settings.generated_dir / "sessions.json").exists()
    assert (settings.generated_dir / "legacy" / "rooms.json").exists()
