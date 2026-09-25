"""내 프로젝트 목록: 참여자인 방만, 제목·단계·공개 주소, 최근순."""


def _create_room(client):
    return client.post("/room").json()["room_id"]


def _post(client, room_id, member_id, message):
    return client.post(f"/room/{room_id}/chat", json={"member_id": member_id, "nickname": "사장님", "message": message})


def _summary(client, member_id, room_ids):
    return client.post("/api/projects/summary", json={"room_ids": room_ids}, headers={"X-Member-Id": member_id})


def test_lists_only_rooms_where_member_joined(client):
    mine, other = _create_room(client), _create_room(client)
    _post(client, mine, "me", "")
    _post(client, other, "someone", "")
    r = _summary(client, "me", [mine, other, "nope123"])
    assert r.status_code == 200
    assert [p["room_id"] for p in r.json()["projects"]] == [mine]


def test_summary_has_state_title_and_deploy(client):
    room = _create_room(client)
    _post(client, room, "me", "카페 예약 서비스 만들어줘")
    _post(client, room, "me", "나머지는 알아서, 시안 먼저 볼게요")
    p = _summary(client, "me", [room]).json()["projects"][0]
    assert p["state"] == "AWAIT_APPROVAL" and p["state_label"] == "확인 대기"
    assert p["title"] and p["last_message"]
    assert p["deploy_url"] is None


def test_requires_member_and_caps_list(client):
    assert client.post("/api/projects/summary", json={"room_ids": []}).status_code == 400
    assert _summary(client, "me", ["x"] * 200).json() == {"projects": []}
