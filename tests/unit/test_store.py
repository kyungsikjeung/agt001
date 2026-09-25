"""저장소: 왕복·복구·손상 파일."""
from app import store
from app.config import settings


def test_save_load_roundtrip(client):
    store.sessions.set("s1", {"state": "QUOTED", "requirement_id": "r1"})
    store.rooms.set("room1", {"room_id": "room1", "ai_status": "IDLE"})
    store.sessions.save()
    store.rooms.save()
    store.sessions.clear()
    store.rooms.clear()
    store.sessions.load()
    store.rooms.load()
    assert store.sessions.get("s1")["state"] == "QUOTED"
    assert store.rooms.get("room1")["ai_status"] == "IDLE"


def test_load_recovers_generating_to_quoted(client):
    store.sessions.set("s2", {"state": "GENERATING", "requirement_id": "r2", "codegen": {"status": "done"}})
    store.sessions.save()
    store.sessions.clear()
    store.sessions.load()
    s = store.sessions.get("s2")
    assert s["state"] == "QUOTED"
    assert s["codegen"] is None


def test_load_recovers_room_ai_status_to_idle(client):
    store.rooms.set("room2", {"room_id": "room2", "ai_status": "GENERATING"})
    store.rooms.save()
    store.rooms.clear()
    store.rooms.load()
    assert store.rooms.get("room2")["ai_status"] == "IDLE"


def test_load_corrupt_json_starts_empty(client):
    path = settings.generated_dir / "sessions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken json", encoding="utf-8")
    store.sessions.clear()
    store.sessions.load()  # 예외 없이 빈 상태로 시작
    assert store.sessions.get("anything") is None

    rpath = settings.generated_dir / "rooms.json"
    rpath.write_text("[not dict", encoding="utf-8")
    store.rooms.clear()
    store.rooms.load()
    assert store.rooms.get("anything") is None
