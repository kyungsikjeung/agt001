"""공유방: 입장·투표·폴링 전이. 원본 backend.py와 동일해야 한다."""
import pytest

from app import store


def _create_room(client):
    r = client.post("/room")
    assert r.status_code == 200
    return r.json()["room_id"]


def _post(client, room_id, member_id, nickname, message):
    return client.post(f"/room/{room_id}/chat", json={"member_id": member_id, "nickname": nickname, "message": message})


def _get(client, room_id, since=None, member_id="m1"):
    url = f"/room/{room_id}/messages"
    if since is not None:
        url += f"?since={since}"
    r = client.get(url, headers={"X-Member-Id": member_id})
    assert r.status_code == 200
    return r.json()


def _drive_to_await_approval(client, room_id):
    r = _post(client, room_id, "m1", "철수", "카페 예약 서비스 만들어줘")
    assert r.status_code == 200
    # 요구사항 엔진이 질문하므로 건너뛰기 문구로 승인 단계까지 간다 (D20).
    _post(client, room_id, "m1", "철수", "나머지는 알아서, 시안 먼저 볼게요")
    data = _get(client, room_id)
    assert data["state"] == "AWAIT_APPROVAL"
    return data


def _drive_to_quoted(client, room_id):
    _drive_to_await_approval(client, room_id)
    _post(client, room_id, "m2", "영희", "")  # 2명째 입장
    _post(client, room_id, "m1", "철수", "승인")  # 1표 → 대기
    r = _post(client, room_id, "m2", "영희", "승인")  # 과반 → QUOTED
    assert r.status_code == 200
    data = _get(client, room_id)
    assert data["state"] == "QUOTED"
    return data


def test_room_create_and_join_system_message_once(client):
    room_id = _create_room(client)
    r = _post(client, room_id, "m1", "철수", "")
    assert r.status_code == 200
    data = _get(client, room_id)
    systems = [m for m in data["messages"] if m["kind"] == "system"]
    assert len(systems) == 1
    assert "입장" in systems[0]["text"]


def test_room_rejoin_no_duplicate_system_message(client):
    room_id = _create_room(client)
    _post(client, room_id, "m1", "철수", "")
    _post(client, room_id, "m1", "철수", "")
    data = _get(client, room_id)
    systems = [m for m in data["messages"] if m["kind"] == "system"]
    assert len(systems) == 1


def test_room_missing_member_id_400(client):
    room_id = _create_room(client)
    r = client.post(f"/room/{room_id}/chat", json={"nickname": "철수", "message": "hi"})
    assert r.status_code == 400


def test_room_not_found_404(client):
    assert client.post("/room/nope123/chat", json={"member_id": "m", "message": "hi"}).status_code == 404
    assert client.get("/room/nope123/messages", headers={"X-Member-Id": "m1"}).status_code == 404


def test_room_nickname_html_escaped(client):
    room_id = _create_room(client)
    _post(client, room_id, "m1", "<b>악의</b>", "hello")
    data = _get(client, room_id)
    chat = [m for m in data["messages"] if m["kind"] == "chat"][0]
    assert "<b>" not in chat["nickname"]
    assert "&lt;b&gt;" in chat["nickname"]


def test_room_message_truncated_2000(client):
    room_id = _create_room(client)
    _post(client, room_id, "m1", "철수", "a" * 2500)
    data = _get(client, room_id)
    chat = [m for m in data["messages"] if m["kind"] == "chat"][0]
    assert len(chat["text"]) == 2000


def test_room_majority_approve_flow(client):
    room_id = _create_room(client)
    _drive_to_await_approval(client, room_id)
    _post(client, room_id, "m2", "영희", "")  # 2명 입장 완료
    # 1명 승인 → 대기 (AWAIT_APPROVAL 유지 + vote 메시지)
    _post(client, room_id, "m1", "철수", "승인")
    mid = _get(client, room_id)
    assert mid["state"] == "AWAIT_APPROVAL"
    votes_msgs = [m for m in mid["messages"] if m["kind"] == "vote"]
    assert len(votes_msgs) == 1
    assert "찬성 1/2" in votes_msgs[0]["text"]
    # 2번째 승인 → QUOTED + votes 초기화
    _post(client, room_id, "m2", "영희", "승인")
    done = _get(client, room_id)
    assert done["state"] == "QUOTED"
    assert done["votes"] == {}
    ai = [m for m in done["messages"] if m["kind"] == "ai_reply"]
    assert any("견적" in m["text"] or "추천" in m["text"] for m in ai)


def test_room_majority_reject_to_gathering(client):
    room_id = _create_room(client)
    _drive_to_await_approval(client, room_id)
    _post(client, room_id, "m2", "영희", "")
    _post(client, room_id, "m1", "철수", "거절")
    mid = _get(client, room_id)
    assert mid["state"] == "AWAIT_APPROVAL"
    _post(client, room_id, "m2", "영희", "거절")
    done = _get(client, room_id)
    assert done["state"] == "GATHERING"
    assert done["votes"] == {}


def test_room_polling_generating_to_done_exactly_once(client):
    room_id = _create_room(client)
    _drive_to_quoted(client, room_id)
    _post(client, room_id, "m1", "철수", "진행")
    mid = _get(client, room_id)
    # 진행 직후 폴링 1회로 GENERATING→DONE 전이가 끝나 있어야 함
    first = _get(client, room_id)
    assert first["state"] == "DONE"

    def completions(data):
        return [m for m in data["messages"] if m["kind"] == "ai_reply" and "코드 생성이 완료됐습니다" in m["text"]]

    assert len(completions(first)) == 1
    # 여러 번 폴링해도 완료 ai_reply가 중복 추가되지 않음
    for _ in range(3):
        again = _get(client, room_id)
        assert again["state"] == "DONE"
        assert len(completions(again)) == 1


def test_room_messages_since_incremental(client):
    room_id = _create_room(client)
    _post(client, room_id, "m1", "철수", "")
    _post(client, room_id, "m1", "철수", "hello")
    all_msgs = _get(client, room_id, since=0)["messages"]
    assert len(all_msgs) >= 2
    tail = _get(client, room_id, since=1)["messages"]
    assert tail == all_msgs[1:]


def test_room_messages_negative_since_is_clamped_to_zero(client):
    # 원본 Flask는 since=-1이면 음수 슬라이스로 마지막 1개를 줬다(의도치 않은 동작).
    # FastAPI는 음수를 0으로 고정해 전체를 준다 — 의도된 변경 (STAGE0_DESIGN §4).
    room_id = _create_room(client)
    _post(client, room_id, "m1", "철수", "")
    _post(client, room_id, "m1", "철수", "hello")
    everything = _get(client, room_id, since=0)["messages"]
    assert _get(client, room_id, since=-1)["messages"] == everything


# ── R-0: 본인 확인 값 비노출, 참여자만 조회 (ROOM_POLICY.md §1) ──

def test_member_ids_are_never_exposed(client):
    room_id = _create_room(client)
    _drive_to_await_approval(client, room_id)
    _post(client, room_id, "secret-m2", "영희", "")
    _post(client, room_id, "secret-m2", "영희", "승인")
    body = client.get(f"/room/{room_id}/messages", headers={"X-Member-Id": "m1"}).text
    assert "secret-m2" not in body
    data = _get(client, room_id)
    assert all("member_id" not in m for m in data["messages"])
    assert all("member_id" not in m for m in data["members"])
    handles = {m["member_handle"] for m in data["members"]}
    assert set(data["votes"]) <= handles and len(data["votes"]) == 1


def test_non_member_cannot_read_messages(client):
    room_id = _create_room(client)
    _drive_to_await_approval(client, room_id)
    assert client.get(f"/room/{room_id}/messages").status_code == 404
    assert client.get(f"/room/{room_id}/messages", headers={"X-Member-Id": "stranger"}).status_code == 404


def test_join_reports_fresh_room_only_once(client):
    room_id = _create_room(client)
    assert _post(client, room_id, "m1", "철수", "").json()["fresh"] is True
    assert _post(client, room_id, "m2", "영희", "").json()["fresh"] is False


def test_messages_include_pending_question_choices(client):
    room_id = _create_room(client)
    _post(client, room_id, "m1", "철수", "카페 예약 서비스 만들어줘")
    q = _get(client, room_id)["question"]
    assert q["kind"] == "single" and q["options"][-1] == "알아서 해주세요" and q["owner_only"] is False
    # 버튼으로 답하면(선택지 그대로) 질문 횟수가 늘고 다음 질문이 나온다
    before = store.read_session(store.read_room(room_id)["session_id"])["prd"]["asked"]
    _post(client, room_id, "m1", "철수", q["options"][0])
    after = store.read_session(store.read_room(room_id)["session_id"])["prd"]["asked"]
    assert after == before + 1 and _get(client, room_id)["question"] is not None
    _post(client, room_id, "m1", "철수", "나머지는 알아서, 시안 먼저 볼게요")
    assert _get(client, room_id)["question"] is None
