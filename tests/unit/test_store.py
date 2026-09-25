"""저장소: 왕복, 기동 복구, 트랜잭션 원자성, 동시성 (STAGE0_DESIGN.md §6.3, §6.6)."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from app import store
from app.services import rooms as rooms_svc


def _new(req_id: str, state: str = "GREETING") -> dict:
    return {"state": state, "requirement_id": req_id}


def test_session_roundtrip_omits_empty_fields(client):
    with store.session_tx("s1", default=lambda: _new("r1")) as s:
        s["state"] = "QUOTED"
        s["quote"] = {"ok": True, "options": [{"id": "A", "amount": 1}]}
    got = store.read_session("s1")
    assert got == {"state": "QUOTED", "requirement_id": "r1", "quote": {"ok": True, "options": [{"id": "A", "amount": 1}]}}
    # 없는 값은 키 자체가 없어야 상태머신의 session.get(key, 기본값)이 기본값을 쓴다.
    assert "design_url" not in got


def test_session_tx_missing_without_default_yields_none(client):
    with store.session_tx("nope") as s:
        assert s is None
    assert store.read_session("nope") is None


def test_exception_rolls_back_and_skips_after_commit(client):
    ran = []
    with pytest.raises(RuntimeError):
        with store.session_tx("s2", default=lambda: _new("r2")) as s:
            s["state"] = "QUOTED"
            store.after_commit(lambda: ran.append(1))
            raise RuntimeError("boom")
    assert store.read_session("s2") is None
    assert ran == []


def test_unknown_session_field_is_rejected(client):
    with pytest.raises(ValueError):
        with store.session_tx("s3", default=lambda: _new("r3")) as s:
            s["typo_field"] = 1


def test_set_codegen_only_while_generating(client):
    with store.session_tx("s4", default=lambda: _new("r4", "QUOTED")):
        pass
    store.set_codegen("s4", {"status": "done"})
    assert "codegen" not in store.read_session("s4")
    with store.session_tx("s4") as s:
        s["state"] = "GENERATING"
    store.set_codegen("s4", {"status": "done"})
    assert store.read_session("s4")["codegen"] == {"status": "done"}


def test_recover_on_startup(client):
    room_id = rooms_svc.create_room()
    room = store.read_room(room_id)
    with store.session_tx(room["session_id"]) as s:
        s["state"] = "GENERATING"
        s["codegen"] = {"status": "done"}
    store.set_room_ai_status(room_id, "GENERATING")
    store.recover_on_startup()
    s = store.read_session(room["session_id"])
    assert s["state"] == "QUOTED"
    assert "codegen" not in s
    assert store.read_room(room_id)["ai_status"] == "IDLE"


def test_parallel_posts_get_gapless_unique_seq(client):
    """같은 방에 20명이 동시에 입장(빈 메시지) → 입장 메시지 seq가 0..19로 빈틈·중복 없음."""
    room_id = rooms_svc.create_room()

    def join(i):
        rooms_svc.post_message(room_id, f"m{i}", f"n{i}", "", "http://t/")

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(join, range(20)))
    msgs = store.read_messages(room_id, 0)
    assert [m["seq"] for m in msgs] == list(range(20))
    assert len(store.read_room(room_id)["members"]) == 20


def test_ai_status_side_write_visible_during_room_tx(client):
    """긴 NIM 호출 중 ai_status는 요청 트랜잭션과 별개로 바로 보여야 한다."""
    room_id = rooms_svc.create_room()
    with store.room_tx(room_id) as (room, _session):
        store.set_room_ai_status(room_id, "RAG_SEARCHING")
        assert store.read_room(room_id)["ai_status"] == "RAG_SEARCHING"
        room["ai_status"] = "IDLE"
    assert store.read_room(room_id)["ai_status"] == "IDLE"
